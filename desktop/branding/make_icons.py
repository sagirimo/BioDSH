#!/usr/bin/env python3
"""BioDSH 图标导出脚本

用法:
    python3 make_icons.py

输出到 out/:
    icon-{16,32,48,64,128,256,512,1024}.png
    icon.ico   (Windows, 含 16/24/32/48/64/128/256)
    icon.icns  (macOS, icp4/icp5/icp6 + ic07/ic08/ic09/ic10/ic11/ic12/ic13/ic14)

SVG -> PNG 的渲染顺序:
    1. cairosvg
    2. Chrome/Chromium 无头模式截图
    3. librsvg (通过 ctypes, Linux 兜底)
"""

import os
import re
import struct
import subprocess
import shutil
import tempfile


ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
PNG_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024]


def source_svg_for(size):
    # 小尺寸(16/24/32)使用简化图标，其余使用主图标。
    name = "icon-small.svg" if size <= 32 else "icon.svg"
    return os.path.join(ROOT, name)


def render_cairosvg(svg_path, png_path, size):
    try:
        import cairosvg
    except ImportError:
        return False
    try:
        cairosvg.svg2png(
            url=svg_path, write_to=png_path,
            output_width=size, output_height=size,
        )
        return True
    except Exception:
        return False


def _chrome_candidates():
    cands = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def render_chrome(svg_path, png_path, size):
    chrome = _chrome_candidates()
    if not chrome:
        return False

    with open(svg_path, "r", encoding="utf-8") as f:
        svg = f.read()
    svg = re.sub(r'width="\d+"', f'width="{size}"', svg, count=1)
    svg = re.sub(r'height="\d+"', f'height="{size}"', svg, count=1)
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;width:%dpx;height:%dpx;overflow:hidden}</style>"
        "</head><body>%s</body></html>" % (size, size, svg)
    )

    fd, html_path = tempfile.mkstemp(suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    try:
        uri = "file://" + html_path
        if os.name == "nt":
            uri = "file:///" + html_path.replace("\\", "/")
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--force-device-scale-factor=1",
            "--hide-scrollbars",
            f"--window-size={size},{size}",
            f"--screenshot={png_path}",
            uri,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return os.path.exists(png_path)
    except Exception:
        return False
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass


def render_rsvg(svg_path, png_path, size):
    import ctypes
    import ctypes.util

    try:
        rsvg = ctypes.CDLL(ctypes.util.find_library("rsvg-2"))
        cairo = ctypes.CDLL(ctypes.util.find_library("cairo"))
    except (OSError, TypeError):
        return False

    class Dim(ctypes.Structure):
        _fields_ = [
            ("width", ctypes.c_int),
            ("height", ctypes.c_int),
            ("em", ctypes.c_double),
            ("ex", ctypes.c_double),
        ]

    rsvg.rsvg_handle_new_from_file.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    rsvg.rsvg_handle_new_from_file.restype = ctypes.c_void_p
    rsvg.rsvg_handle_get_dimensions.argtypes = [ctypes.c_void_p, ctypes.POINTER(Dim)]
    rsvg.rsvg_handle_render_cairo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    rsvg.rsvg_handle_render_cairo.restype = ctypes.c_int

    cairo.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    cairo.cairo_image_surface_create.restype = ctypes.c_void_p
    cairo.cairo_create.argtypes = [ctypes.c_void_p]
    cairo.cairo_create.restype = ctypes.c_void_p
    cairo.cairo_scale.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
    cairo.cairo_surface_write_to_png.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    cairo.cairo_surface_write_to_png.restype = ctypes.c_int
    cairo.cairo_destroy.argtypes = [ctypes.c_void_p]
    cairo.cairo_surface_destroy.argtypes = [ctypes.c_void_p]

    err = ctypes.c_void_p()
    handle = rsvg.rsvg_handle_new_from_file(svg_path.encode("utf-8"), ctypes.byref(err))
    if not handle:
        return False

    dim = Dim()
    rsvg.rsvg_handle_get_dimensions(handle, ctypes.byref(dim))
    if dim.width <= 0:
        return False

    # CAIRO_FORMAT_ARGB32 == 0
    surface = cairo.cairo_image_surface_create(0, size, size)
    cr = cairo.cairo_create(surface)
    scale = float(size) / dim.width
    cairo.cairo_scale(cr, scale, scale)
    ok = rsvg.rsvg_handle_render_cairo(handle, cr)
    cairo.cairo_destroy(cr)
    if ok:
        cairo.cairo_surface_write_to_png(surface, png_path.encode("utf-8"))
    cairo.cairo_surface_destroy(surface)
    return bool(ok) and os.path.exists(png_path)


def render(svg_path, png_path, size):
    for fn in (render_cairosvg, render_chrome, render_rsvg):
        if fn(svg_path, png_path, size):
            return fn.__name__
    raise RuntimeError(f"无法渲染 SVG: {svg_path} (size={size})")


def build_ico():
    try:
        from PIL import Image
    except ImportError:
        print("  提示: 未安装 Pillow，跳过 icon.ico（可 `pip install Pillow` 后重试）")
        return None

    sizes = [16, 24, 32, 48, 64, 128, 256]
    # 以最大尺寸作为基底，其余尺寸作为 append_images，避免被 ICO 写入逻辑跳过。
    base = Image.open(os.path.join(OUT, "icon-256.png")).convert("RGBA")
    rest = [
        Image.open(os.path.join(OUT, f"icon-{s}.png")).convert("RGBA")
        for s in sizes if s != 256
    ]
    ico_path = os.path.join(OUT, "icon.ico")
    base.save(ico_path, format="ICO", append_images=rest)
    return ico_path


def build_icns():
    # (type, 像素尺寸)
    blocks = [
        ("icp4", 16),
        ("icp5", 32),
        ("icp6", 64),
        ("ic07", 128),
        ("ic08", 256),
        ("ic09", 512),
        ("ic10", 1024),
        ("ic11", 32),
        ("ic12", 64),
        ("ic13", 256),
        ("ic14", 512),
    ]
    chunks = []
    total = 8
    for typ, size in blocks:
        with open(os.path.join(OUT, f"icon-{size}.png"), "rb") as f:
            png = f.read()
        chunks.append((typ.encode("ascii"), png))
        total += 8 + len(png)

    buf = bytearray()
    buf += b"icns"
    buf += struct.pack(">I", total)
    for typ, png in chunks:
        buf += typ
        buf += struct.pack(">I", 8 + len(png))
        buf += png

    icns_path = os.path.join(OUT, "icon.icns")
    with open(icns_path, "wb") as f:
        f.write(buf)
    return icns_path


def main():
    os.makedirs(OUT, exist_ok=True)
    methods = {}
    for size in PNG_SIZES:
        svg = source_svg_for(size)
        png = os.path.join(OUT, f"icon-{size}.png")
        methods[size] = render(svg, png, size)
        print(f"  icon-{size}.png  ({methods[size]})")

    # ICO 需要的 24px（顺带导出，便于单独使用）
    render(source_svg_for(24), os.path.join(OUT, "icon-24.png"), 24)

    ico = build_ico()
    if ico:
        print(f"  {os.path.basename(ico)}")
    icns = build_icns()
    print(f"  {os.path.basename(icns)}")
    print(f"\n完成，输出目录: {OUT}")


if __name__ == "__main__":
    main()
