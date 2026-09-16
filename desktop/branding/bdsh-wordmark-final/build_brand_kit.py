#!/usr/bin/env python3
"""Build the BioDSH wordmark and application-icon kit from the approved raster.

The source image is treated as geometry authority.  The script recovers clean
coverage alpha for the white, blue, and cyan objects, traces the resulting
masks into outlined SVG paths, and then exports desktop/web/mobile assets.
No runtime font is used by the final SVGs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.interpolate import splprep, splev
from skimage.measure import approximate_polygon, find_contours, label, regionprops
from skimage.transform import resize


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source" / "reference-wordmark.png"
SVG_DIR = ROOT / "svg"
DIST = ROOT / "dist"
PREVIEW = ROOT / "preview"

INK = "#0A1428"
WHITE = "#FFFFFF"
BLUE = "#2C58FC"
CYAN = "#00D8F7"
SOFT_WHITE = "#F7F9FC"

BG_RGB = np.array([10.0, 20.0, 39.5], dtype=np.float32)
WHITE_RGB = np.array([255.0, 255.0, 255.0], dtype=np.float32)
BLUE_RGB = np.array([44.0, 88.0, 252.0], dtype=np.float32)
CYAN_RGB = np.array([0.0, 216.0, 247.0], dtype=np.float32)

PNG_SIZES = [16, 20, 24, 32, 40, 44, 48, 64, 71, 89, 107, 128, 142, 150, 180, 192, 256, 284, 310, 512, 1024]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def ensure_dirs() -> None:
    for path in (SVG_DIR, DIST, PREVIEW):
        path.mkdir(parents=True, exist_ok=True)


def project_alpha(pixels: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    vector = foreground - BG_RGB
    delta = pixels.astype(np.float32) - BG_RGB
    alpha = np.sum(delta * vector, axis=2) / float(np.sum(vector * vector))
    alpha = np.clip(alpha, 0.0, 1.0)
    alpha[alpha < 0.02] = 0.0
    alpha[alpha > 0.98] = 1.0
    return alpha


def remove_small_components(alpha: np.ndarray, min_area: int = 3) -> np.ndarray:
    binary = alpha > 0.02
    components = label(binary, connectivity=2)
    keep = np.zeros_like(binary)
    for region in regionprops(components):
        if region.area >= min_area:
            keep[components == region.label] = True
    return np.where(keep, alpha, 0.0)


def extract_channels(image: Image.Image) -> dict[str, np.ndarray]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width, _ = rgb.shape

    white = project_alpha(rgb, WHITE_RGB)
    blue = project_alpha(rgb, BLUE_RGB)
    cyan = project_alpha(rgb, CYAN_RGB)

    # Object regions measured from the approved 238x66 source.
    white[:, 109:] = 0.0
    blue[:, :108] = 0.0

    cyan_region = np.zeros((height, width), dtype=bool)
    cyan_region[32:48, 138:171] = True
    cyan_signal = (rgb[:, :, 1] > 115) & (rgb[:, :, 2] > 145) & (rgb[:, :, 0] < 90)
    cyan = np.where(cyan_region & cyan_signal, cyan, 0.0)

    # The connector is the top layer.  Avoid a blue fringe under its core.
    blue = np.where(cyan > 0.28, 0.0, blue)

    white = remove_small_components(white)
    blue = remove_small_components(blue)
    cyan = remove_small_components(cyan, min_area=2)
    return {"white": white, "blue": blue, "cyan": cyan}


def content_bbox(channels: dict[str, np.ndarray], threshold: float = 0.02) -> tuple[int, int, int, int]:
    union = np.maximum.reduce(list(channels.values()))
    ys, xs = np.where(union > threshold)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def crop_channels(channels: dict[str, np.ndarray], bbox: tuple[int, int, int, int], padding: int = 4) -> dict[str, np.ndarray]:
    x0, y0, x1, y1 = bbox
    result: dict[str, np.ndarray] = {}
    for name, alpha in channels.items():
        crop = alpha[y0:y1, x0:x1]
        result[name] = np.pad(crop, ((padding, padding), (padding, padding)), mode="constant")
    return result


def rgba_from_channels(channels: dict[str, np.ndarray], mode: str) -> Image.Image:
    height, width = next(iter(channels.values())).shape
    out_rgb = np.zeros((height, width, 3), dtype=np.float32)
    out_alpha = np.zeros((height, width), dtype=np.float32)

    if mode == "on-dark":
        colors = {"white": np.array([255, 255, 255]), "blue": np.array([44, 88, 252]), "cyan": np.array([0, 216, 247])}
    elif mode == "on-light":
        colors = {"white": np.array([10, 20, 40]), "blue": np.array([44, 88, 252]), "cyan": np.array([0, 216, 247])}
    elif mode == "mono-white":
        colors = {key: np.array([255, 255, 255]) for key in channels}
    elif mode == "mono-black":
        colors = {key: np.array([10, 20, 40]) for key in channels}
    else:
        raise ValueError(mode)

    # Composite in the same order as the source: Bio/DSH, then cyan connector.
    for name in ("white", "blue", "cyan"):
        alpha = channels[name]
        color = colors[name].astype(np.float32)
        new_alpha = alpha + out_alpha * (1.0 - alpha)
        numerator = color[None, None, :] * alpha[:, :, None] + out_rgb * out_alpha[:, :, None] * (1.0 - alpha[:, :, None])
        out_rgb = np.where(new_alpha[:, :, None] > 0, numerator / np.maximum(new_alpha[:, :, None], 1e-8), 0)
        out_alpha = new_alpha

    rgba = np.dstack([np.clip(out_rgb, 0, 255), np.clip(out_alpha * 255.0, 0, 255)]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def save_exact_rasters(channels: dict[str, np.ndarray]) -> None:
    exact_dir = DIST / "wordmark-exact"
    exact_dir.mkdir(parents=True, exist_ok=True)
    for mode in ("on-dark", "on-light", "mono-white", "mono-black"):
        image = rgba_from_channels(channels, mode)
        image.save(exact_dir / f"wordmark-{mode}-native.png")
        for factor in (4, 8):
            scaled = image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
            scaled.save(exact_dir / f"wordmark-{mode}-{factor}x.png")


def _smooth_closed_contour(points: np.ndarray) -> str:
    """Convert a closed x/y contour to a smooth cubic SVG subpath."""
    if len(points) < 8:
        return ""
    # Remove a duplicated closing sample before fitting a periodic spline.
    if np.linalg.norm(points[0] - points[-1]) < 1e-6:
        points = points[:-1]
    if len(points) < 8:
        return ""
    x = points[:, 0]
    y = points[:, 1]
    try:
        tck, _ = splprep([x, y], s=len(points) * 0.08, per=True, k=3)
        closed = np.vstack([points, points[0]])
        perimeter = float(np.sum(np.linalg.norm(np.diff(closed, axis=0), axis=1)))
        samples = max(28, min(220, int(math.ceil(perimeter * 1.5))))
        u = np.linspace(0.0, 1.0, samples, endpoint=False)
        sx, sy = splev(u, tck)
        curve = np.column_stack([sx, sy])
    except (TypeError, ValueError):
        curve = points

    count = len(curve)
    if count < 4:
        return ""
    commands = [f"M {curve[0, 0]:.3f} {curve[0, 1]:.3f}"]
    for index in range(count):
        p0 = curve[(index - 1) % count]
        p1 = curve[index]
        p2 = curve[(index + 1) % count]
        p3 = curve[(index + 2) % count]
        c1 = p1 + (p2 - p0) / 6.0
        c2 = p2 - (p3 - p1) / 6.0
        commands.append(
            f"C {c1[0]:.3f} {c1[1]:.3f} {c2[0]:.3f} {c2[1]:.3f} {p2[0]:.3f} {p2[1]:.3f}"
        )
    commands.append("Z")
    return " ".join(commands)


def contour_path(alpha: np.ndarray, smooth: bool = True) -> str:
    scale = 8
    base = gaussian_filter(alpha, sigma=0.45) if smooth else alpha
    up = resize(base, (alpha.shape[0] * scale, alpha.shape[1] * scale), order=3, mode="constant", anti_aliasing=True, preserve_range=True)
    if smooth:
        up = gaussian_filter(up, sigma=1.25)
    padded = np.pad(up, 3, mode="constant")
    commands: list[str] = []
    for contour in find_contours(padded, 0.5, fully_connected="high"):
        contour[:, 0] -= 3.0
        contour[:, 1] -= 3.0
        simplified = approximate_polygon(contour, tolerance=0.22)
        if len(simplified) < 4:
            continue
        points = np.array([(float(col) / scale, float(row) / scale) for row, col in simplified], dtype=np.float64)
        subpath = _smooth_closed_contour(points)
        if subpath:
            commands.append(subpath)
    return " ".join(commands)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def svg_document(width: float, height: float, body: str, *, title: str, background: str | None = None, rx: float = 0) -> str:
    bg = ""
    if background:
        bg = f'<rect width="{width:g}" height="{height:g}" rx="{rx:g}" fill="{background}"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}">
  <title>{title}</title>
  {bg}
  {body}
</svg>
'''


def write_wordmark_svgs(channels: dict[str, np.ndarray]) -> dict[str, str]:
    height, width = next(iter(channels.values())).shape
    paths = {name: contour_path(alpha) for name, alpha in channels.items()}
    variants = {
        "wordmark-on-dark.svg": {"white": WHITE, "blue": BLUE, "cyan": CYAN},
        "wordmark-on-light.svg": {"white": INK, "blue": BLUE, "cyan": CYAN},
        "wordmark-mono-white.svg": {"white": WHITE, "blue": WHITE, "cyan": WHITE},
        "wordmark-mono-black.svg": {"white": INK, "blue": INK, "cyan": INK},
    }
    for filename, colors in variants.items():
        body = "\n  ".join(
            f'<path d="{paths[name]}" fill="{colors[name]}" fill-rule="evenodd"/>'
            for name in ("white", "blue", "cyan")
        )
        (SVG_DIR / filename).write_text(svg_document(width, height, body, title=filename.removesuffix(".svg")), encoding="utf-8")
    return paths


def split_logo_channels(full: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    # Coordinates relative to the padded, cropped wordmark: original x0=14, y0=14, pad=4.
    # Bio source bbox x=14..108, y=14..64. DSH source bbox x=110..227, y=16..63.
    bio = {key: value[0:58, 0:102] for key, value in full.items()}
    dsh = {key: value[2:57, 96:221] for key, value in full.items()}
    # Bio is white-only; DSH is blue plus cyan. Keep empty channels for a common API.
    bio["blue"] = np.zeros_like(bio["white"])
    bio["cyan"] = np.zeros_like(bio["white"])
    dsh["white"] = np.zeros_like(dsh["blue"])
    return bio, dsh


def paths_for_group(channels: dict[str, np.ndarray]) -> dict[str, str]:
    return {name: contour_path(alpha) for name, alpha in channels.items()}


def group_svg(paths: dict[str, str], colors: dict[str, str], x: float, y: float, scale: float) -> str:
    pieces = []
    for name in ("white", "blue", "cyan"):
        if paths[name]:
            pieces.append(f'<path d="{paths[name]}" fill="{colors[name]}" fill-rule="evenodd"/>')
    return f'<g transform="translate({x:.3f} {y:.3f}) scale({scale:.6f})">' + "".join(pieces) + "</g>"


def write_stacked_and_app_svgs(bio: dict[str, np.ndarray], dsh: dict[str, np.ndarray]) -> None:
    bio_paths = paths_for_group(bio)
    dsh_paths = paths_for_group(dsh)
    bio_h, bio_w = bio["white"].shape
    dsh_h, dsh_w = dsh["blue"].shape

    target_width = 664.0
    bio_scale = target_width / bio_w
    dsh_scale = target_width / dsh_w
    bio_height = bio_h * bio_scale
    dsh_height = dsh_h * dsh_scale
    x = 180.0
    bio_y = 178.0
    dsh_y = 575.0

    dark_colors = {"white": WHITE, "blue": BLUE, "cyan": CYAN}
    light_colors = {"white": INK, "blue": BLUE, "cyan": CYAN}

    stacked_height = bio_height + 45.0 + dsh_height
    stacked_width = target_width
    stack_bio_y = 0.0
    stack_dsh_y = bio_height + 45.0

    for name, colors in (("on-dark", dark_colors), ("on-light", light_colors)):
        body = group_svg(bio_paths, colors, 0, stack_bio_y, bio_scale) + "\n  " + group_svg(dsh_paths, colors, 0, stack_dsh_y, dsh_scale)
        (SVG_DIR / f"stacked-{name}.svg").write_text(
            svg_document(stacked_width, stacked_height, body, title=f"BioDSH stacked {name}"), encoding="utf-8"
        )

    for mode, colors, background in (
        ("dark", dark_colors, INK),
        ("light", light_colors, WHITE),
    ):
        body = group_svg(bio_paths, colors, x, bio_y, bio_scale) + "\n  " + group_svg(dsh_paths, colors, x, dsh_y, dsh_scale)
        square = svg_document(1024, 1024, body, title=f"BioDSH {mode} square application icon", background=background, rx=0)
        rounded = svg_document(1024, 1024, body, title=f"BioDSH {mode} rounded application icon", background=background, rx=224)
        (SVG_DIR / f"app-icon-{mode}-square.svg").write_text(square, encoding="utf-8")
        (SVG_DIR / f"app-icon-{mode}-rounded.svg").write_text(rounded, encoding="utf-8")

        # Small-size master: less margin, no cyan connector at 16px, otherwise identical geometry.
        small_colors = dict(colors)
        small_colors["cyan"] = colors["blue"]
        small_body = group_svg(bio_paths, small_colors, x, 185, bio_scale) + "\n  " + group_svg(dsh_paths, small_colors, x, 575, dsh_scale)
        (SVG_DIR / f"app-icon-{mode}-small.svg").write_text(
            svg_document(1024, 1024, small_body, title=f"BioDSH {mode} small application icon", background=background, rx=224),
            encoding="utf-8",
        )

    # Android adaptive foreground: only the two-line mark within the central 61% safe region.
    safe_width = 625.0
    bio_safe_scale = safe_width / bio_w
    dsh_safe_scale = safe_width / dsh_w
    safe_bio_h = bio_h * bio_safe_scale
    safe_dsh_h = dsh_h * dsh_safe_scale
    safe_total_h = safe_bio_h + 34 + safe_dsh_h
    safe_x = (1024 - safe_width) / 2
    safe_y = (1024 - safe_total_h) / 2
    adaptive_body = group_svg(bio_paths, dark_colors, safe_x, safe_y, bio_safe_scale) + "\n  " + group_svg(dsh_paths, dark_colors, safe_x, safe_y + safe_bio_h + 34, dsh_safe_scale)
    (SVG_DIR / "android-adaptive-foreground.svg").write_text(
        svg_document(1024, 1024, adaptive_body, title="BioDSH Android adaptive foreground"), encoding="utf-8"
    )


def chrome_path() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for name in ("google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise RuntimeError("Chrome/Edge not found; cannot rasterize SVG assets")


def render_svg(svg_path: Path, png_path: Path, width: int, height: int) -> None:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    chrome = chrome_path()
    svg_uri = svg_path.resolve().as_uri()
    html = f'''<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden;background:transparent}}
img{{display:block;width:{width}px;height:{height}px;object-fit:contain}}
</style><img src="{svg_uri}">'''
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False, dir=ROOT) as handle:
        handle.write(html)
        html_path = Path(handle.name)
    try:
        command = [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--default-background-color=00000000",
            f"--window-size={width},{height}",
            f"--screenshot={png_path.resolve()}",
            html_path.resolve().as_uri(),
        ]
        process = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if process.returncode != 0 or not png_path.exists():
            raise RuntimeError(process.stderr or process.stdout or f"Chrome render failed: {svg_path}")
    finally:
        html_path.unlink(missing_ok=True)


def render_icon_sets() -> None:
    for mode in ("dark", "light"):
        out_dir = DIST / f"app-{mode}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for size in PNG_SIZES:
            source = SVG_DIR / f"app-icon-{mode}-small.svg" if size <= 32 else SVG_DIR / f"app-icon-{mode}-rounded.svg"
            render_svg(source, out_dir / f"icon-{size}.png", size, size)

        square_dir = DIST / f"app-{mode}-square"
        square_dir.mkdir(parents=True, exist_ok=True)
        for size in (180, 192, 512, 1024):
            render_svg(SVG_DIR / f"app-icon-{mode}-square.svg", square_dir / f"icon-{size}.png", size, size)


def render_wordmarks() -> None:
    for mode in ("on-dark", "on-light", "mono-white", "mono-black"):
        source = SVG_DIR / f"wordmark-{mode}.svg"
        with Image.open(DIST / "wordmark-exact" / f"wordmark-{mode}-native.png") as reference:
            aspect = reference.height / reference.width
        out_dir = DIST / "wordmark"
        out_dir.mkdir(parents=True, exist_ok=True)
        for width in (220, 256, 440, 512, 880, 1024, 2048):
            height = max(1, int(round(width * aspect)))
            render_svg(source, out_dir / f"wordmark-{mode}-{width}.png", width, height)

    for mode in ("on-dark", "on-light"):
        source = SVG_DIR / f"stacked-{mode}.svg"
        with Image.open(DIST / "wordmark-exact" / f"wordmark-{mode}-native.png"):
            pass
        # The stacked SVG has a near-square viewBox; read dimensions from XML attributes indirectly.
        for size in (256, 512, 1024):
            render_svg(source, DIST / "stacked" / f"stacked-{mode}-{size}.png", size, size)


def build_ico(image_dir: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.open(image_dir / f"icon-{size}.png").convert("RGBA") for size in ICO_SIZES]
    base = images[-1]
    base.save(destination, format="ICO", append_images=images[:-1])
    for image in images:
        image.close()


def build_icns(image_dir: Path, destination: Path) -> None:
    blocks = [
        ("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128),
        ("ic08", 256), ("ic09", 512), ("ic10", 1024),
        ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic14", 512),
    ]
    chunks: list[tuple[bytes, bytes]] = []
    total = 8
    for kind, size in blocks:
        data = (image_dir / f"icon-{size}.png").read_bytes()
        chunks.append((kind.encode("ascii"), data))
        total += 8 + len(data)
    buffer = bytearray(b"icns")
    buffer.extend(struct.pack(">I", total))
    for kind, data in chunks:
        buffer.extend(kind)
        buffer.extend(struct.pack(">I", 8 + len(data)))
        buffer.extend(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(buffer)


def copy_resized(source: Path, destination: Path, size: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source).convert("RGBA") as image:
        image.resize((size, size), Image.Resampling.LANCZOS).save(destination)


def build_platform_assets() -> None:
    dark = DIST / "app-dark"
    light = DIST / "app-light"
    build_ico(dark, DIST / "windows" / "BioDSH.ico")
    build_ico(light, DIST / "windows" / "BioDSH-light.ico")
    build_icns(dark, DIST / "macos" / "BioDSH.icns")
    build_icns(light, DIST / "macos" / "BioDSH-light.icns")

    # Electron and current Tauri desktop build inputs (staging only; production is not overwritten).
    electron = DIST / "electron"
    electron.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DIST / "windows" / "BioDSH.ico", electron / "icon.ico")
    shutil.copy2(dark / "icon-1024.png", electron / "icon-1024.png")
    shutil.copy2(dark / "icon-512.png", electron / "icon.png")
    shutil.copy2(dark / "icon-256.png", electron / "icon-256.png")

    tauri = DIST / "tauri"
    tauri.mkdir(parents=True, exist_ok=True)
    for size, name in ((32, "32x32.png"), (64, "64x64.png"), (128, "128x128.png"), (256, "128x128@2x.png")):
        shutil.copy2(dark / f"icon-{size}.png", tauri / name)
    shutil.copy2(dark / "icon-1024.png", tauri / "icon.png")
    shutil.copy2(DIST / "windows" / "BioDSH.ico", tauri / "icon.ico")
    shutil.copy2(DIST / "macos" / "BioDSH.icns", tauri / "icon.icns")

    # Web/PWA assets.
    web = DIST / "web"
    web.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SVG_DIR / "app-icon-dark-small.svg", web / "favicon.svg")
    build_ico(dark, web / "favicon.ico")
    for size, name in (
        (16, "favicon-16.png"), (32, "favicon-32.png"), (48, "favicon-48.png"),
        (180, "apple-touch-icon.png"), (192, "android-chrome-192.png"),
        (512, "android-chrome-512.png"),
    ):
        shutil.copy2(dark / f"icon-{size}.png", web / name)
    (web / "site.webmanifest").write_text(json.dumps({
        "name": "BioDSH", "short_name": "BioDSH", "display": "standalone",
        "background_color": INK, "theme_color": INK,
        "icons": [
            {"src": "android-chrome-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "android-chrome-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Windows Store tile names with exact pixel dimensions.
    windows_store = DIST / "windows-store"
    for size in (30, 44, 71, 89, 107, 142, 150, 284, 310):
        nearest = min(PNG_SIZES, key=lambda candidate: abs(candidate - size))
        copy_resized(dark / f"icon-{nearest}.png", windows_store / f"Square{size}x{size}Logo.png", size)
    copy_resized(dark / "icon-64.png", windows_store / "StoreLogo.png", 50)

    # iOS opaque full-bleed square assets.
    ios = DIST / "ios"
    ios_sizes = {
        "AppIcon-20x20@1x.png": 20, "AppIcon-20x20@2x.png": 40, "AppIcon-20x20@3x.png": 60,
        "AppIcon-29x29@1x.png": 29, "AppIcon-29x29@2x.png": 58, "AppIcon-29x29@3x.png": 87,
        "AppIcon-40x40@1x.png": 40, "AppIcon-40x40@2x.png": 80, "AppIcon-40x40@3x.png": 120,
        "AppIcon-60x60@2x.png": 120, "AppIcon-60x60@3x.png": 180,
        "AppIcon-76x76@1x.png": 76, "AppIcon-76x76@2x.png": 152,
        "AppIcon-83.5x83.5@2x.png": 167, "AppIcon-512@2x.png": 1024,
    }
    square_master = DIST / "app-dark-square" / "icon-1024.png"
    for name, size in ios_sizes.items():
        copy_resized(square_master, ios / name, size)

    # Android legacy and adaptive assets.
    android = DIST / "android"
    densities = {
        "mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216),
        "xxhdpi": (144, 324), "xxxhdpi": (192, 432),
    }
    for density, (legacy_size, foreground_size) in densities.items():
        folder = android / f"mipmap-{density}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dark / f"icon-{legacy_size}.png", folder / "ic_launcher.png") if (dark / f"icon-{legacy_size}.png").exists() else copy_resized(dark / "icon-512.png", folder / "ic_launcher.png", legacy_size)
        copy_resized(dark / "icon-512.png", folder / "ic_launcher_round.png", legacy_size)
        render_svg(SVG_DIR / "android-adaptive-foreground.svg", folder / "ic_launcher_foreground.png", foreground_size, foreground_size)
    values = android / "values"
    values.mkdir(parents=True, exist_ok=True)
    (values / "ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#0A1428</color>\n</resources>\n',
        encoding="utf-8",
    )


def build_preview_html() -> None:
    html = f'''<!doctype html>
<meta charset="utf-8">
<title>BioDSH brand kit preview</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#eef2f7;color:{INK};font:16px/1.45 "Segoe UI",Arial,sans-serif}}
main{{width:1600px;margin:0 auto;padding:54px 64px 72px}} h1{{font-size:40px;margin:0 0 8px}} .lead{{color:#65748a;margin:0 0 32px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}} .card{{border:1px solid #d9e0ea;border-radius:24px;overflow:hidden;background:white}}
.stage{{height:260px;display:flex;align-items:center;justify-content:center;padding:44px}} .stage.dark{{background:{INK}}} .stage.light{{background:#fff}}
.wordmark{{width:82%;height:auto}} .meta{{padding:18px 22px;color:#65748a}} .meta b{{color:{INK}}}
.icons{{display:flex;gap:28px;align-items:center;justify-content:center}} .app{{width:190px;height:190px}} .small{{display:flex;gap:18px;align-items:end}}
.small img{{image-rendering:auto}} footer{{margin-top:28px;color:#65748a}}
</style>
<main>
  <h1>BioDSH 标志与应用图标</h1>
  <p class="lead">字形来自用户批准的 238×66 源图；最终 SVG 为描摹路径，不依赖字体。</p>
  <section class="grid">
    <article class="card"><div class="stage dark"><img class="wordmark" src="../svg/wordmark-on-dark.svg"></div><div class="meta"><b>深色模式</b> · Bio 白 / DSH 蓝 / 连接件青</div></article>
    <article class="card"><div class="stage light"><img class="wordmark" src="../svg/wordmark-on-light.svg"></div><div class="meta"><b>浅色模式</b> · Bio 品牌墨 / DSH 蓝 / 连接件青</div></article>
    <article class="card"><div class="stage dark"><div class="icons"><img class="app" src="../svg/app-icon-dark-rounded.svg"><img class="app" src="../svg/app-icon-dark-square.svg"></div></div><div class="meta"><b>应用图标</b> · 圆角展示版与系统裁切方形版</div></article>
    <article class="card"><div class="stage light"><div class="icons"><img class="app" src="../svg/app-icon-light-rounded.svg"><div class="small">
      <img src="../dist/app-dark/icon-16.png" width="16" height="16"><img src="../dist/app-dark/icon-24.png" width="24" height="24"><img src="../dist/app-dark/icon-32.png" width="32" height="32"><img src="../dist/app-dark/icon-48.png" width="48" height="48"><img src="../dist/app-dark/icon-64.png" width="64" height="64">
    </div></div></div><div class="meta"><b>浅色与小尺寸</b> · 16–32 px 使用独立简化母版</div></article>
  </section>
  <footer>规范色：{INK} · {WHITE} · {BLUE} · {CYAN}</footer>
</main>
'''
    (PREVIEW / "index.html").write_text(html, encoding="utf-8")


def render_preview() -> None:
    chrome = chrome_path()
    destination = PREVIEW / "brand-kit-preview.png"
    command = [
        str(chrome), "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--window-size=1600,1180",
        f"--screenshot={destination.resolve()}", (PREVIEW / "index.html").resolve().as_uri(),
    ]
    process = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if process.returncode != 0 or not destination.exists():
        raise RuntimeError(process.stderr or process.stdout or "Preview render failed")


def write_manifest() -> None:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.name == "MANIFEST.json" or path.name.startswith("tmp"):
            continue
        relative = path.relative_to(ROOT).as_posix()
        entry: dict[str, object] = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if path.suffix.lower() == ".png":
            with Image.open(path) as image:
                entry["width"] = image.width
                entry["height"] = image.height
                entry["mode"] = image.mode
        files.append(entry)
    manifest = {
        "brand": "BioDSH",
        "source": "source/reference-wordmark.png",
        "geometry_authority": "user-approved raster traced to outlined paths",
        "colors": {"ink": INK, "white": WHITE, "blue": BLUE, "cyan": CYAN},
        "files": files,
    }
    (ROOT / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true", help="Only refresh MANIFEST.json")
    parser.add_argument("--quick", action="store_true", help="Rebuild vectors and render only two large QA images")
    args = parser.parse_args()
    ensure_dirs()
    if args.manifest_only:
        write_manifest()
        return

    source = Image.open(SOURCE).convert("RGB")
    full_channels = extract_channels(source)
    bbox = content_bbox(full_channels)
    cropped = crop_channels(full_channels, bbox, padding=4)
    save_exact_rasters(cropped)
    write_wordmark_svgs(cropped)
    bio, dsh = split_logo_channels(cropped)
    write_stacked_and_app_svgs(bio, dsh)
    if args.quick:
        render_svg(SVG_DIR / "wordmark-on-dark.svg", PREVIEW / "quick-wordmark-dark.png", 1024, 269)
        render_svg(SVG_DIR / "app-icon-dark-rounded.svg", PREVIEW / "quick-app-dark.png", 1024, 1024)
        print(f"BioDSH quick vectors built at: {ROOT}")
        return
    render_icon_sets()
    render_wordmarks()
    build_platform_assets()
    build_preview_html()
    render_preview()
    write_manifest()
    print(f"BioDSH brand kit built at: {ROOT}")


if __name__ == "__main__":
    main()
