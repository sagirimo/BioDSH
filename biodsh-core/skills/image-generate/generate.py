"""Text-to-image for scientific illustration via any OpenAI-compatible Images API.

Provider comes from environment variables set by the BioDSH app (更多 → 图像生成):
  BIODSH_IMAGE_BASE_URL   e.g. https://open.bigmodel.cn/api/paas/v4, https://api.openai.com/v1
  BIODSH_IMAGE_API_KEY
  BIODSH_IMAGE_MODEL      e.g. cogview-4-250304, gpt-image-1, Kwai-Kolors/Kolors, wan2.2-t2i-flash

Prints a JSON summary to stdout; on failure prints {"error": ...} and exits 1.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

TIMEOUT = 180
ENV_BASE = "BIODSH_IMAGE_BASE_URL"
ENV_KEY = "BIODSH_IMAGE_API_KEY"
ENV_MODEL = "BIODSH_IMAGE_MODEL"

STYLE_TEMPLATES = {
    "scientific": (
        "Clean scientific illustration in the style of a journal graphical abstract: "
        "vector-like flat colors, crisp outlines, plain white background, clear spatial "
        "layout with unambiguous arrows, no text, no letters, no watermark, no artifacts. "
        "Subject: "
    ),
    "flat": (
        "Flat design illustration: simple geometric shapes, limited pastel palette, "
        "solid colors without gradients, white background, no text, no watermark. "
        "Subject: "
    ),
    "photo": (
        "Photorealistic scientific render: soft studio lighting, high detail, shallow depth "
        "of field, neutral background, no text, no watermark. Subject: "
    ),
    "none": "",
}

# Hosts known to accept `response_format: "b64_json"` (OpenAI-style). 智谱 rejects unknown fields.
B64_HOSTS = {"api.openai.com", "api.siliconflow.cn", "api.siliconflow.com"}
# Hosts whose /images/edits endpoint accepts a multipart reference image.
EDITS_HOSTS = {"api.openai.com"}
# Hosts that accept a dedicated negative_prompt field.
NEGATIVE_FIELD_HOSTS = {"api.siliconflow.cn", "api.siliconflow.com"}

ZHIPU_HOSTS = {"open.bigmodel.cn"}
ZHIPU_SIZES = ["1024x1024", "768x1344", "864x1152", "1344x768", "1152x864", "1440x720", "720x1440"]
OPENAI_MODEL_SIZES = {
    "gpt-image-1": ["1024x1024", "1536x1024", "1024x1536"],
    "dall-e-3": ["1024x1024", "1792x1024", "1024x1792"],
    "dall-e-2": ["256x256", "512x512", "1024x1024"],
}


def fail(message: str, **extra) -> None:
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(1)


def parse_size(size: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*", size)
    if not m:
        raise ValueError(f"invalid --size {size!r}; expected WIDTHxHEIGHT such as 1024x1024")
    return int(m.group(1)), int(m.group(2))


def normalize_size(size: str, host: str, model: str) -> tuple[str, str | None]:
    """Return (size accepted by the provider, note if it was changed)."""
    w, h = parse_size(size)
    requested = f"{w}x{h}"
    allowed: list[str] | None = None
    if host in ZHIPU_HOSTS:
        allowed = ZHIPU_SIZES
    elif host == "api.openai.com":
        allowed = OPENAI_MODEL_SIZES.get(model.lower())
    if not allowed or requested in allowed:
        return requested, None
    # pick the allowed size whose aspect ratio is closest, ties broken by area
    ratio = w / h

    def score(s: str) -> tuple[float, float]:
        aw, ah = parse_size(s)
        return (abs((aw / ah) - ratio), abs(aw * ah - w * h))

    best = min(allowed, key=score)
    return best, f"size {requested} not supported by {host}; using {best}"


def slugify(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "image"
    return "-".join(w.lower() for w in words[:5])[:60]


def looks_like_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def detect_format(data: bytes) -> str:
    if looks_like_png(data):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def http_error(prefix: str, resp: requests.Response) -> None:
    body = resp.text[:300]
    fail(f"{prefix}: HTTP {resp.status_code}: {body}", status=resp.status_code)


def request_images(base: str, key: str, payload: dict, reference: Path | None, host: str) -> dict:
    headers = {"Authorization": f"Bearer {key}"}
    try:
        if reference is None:
            resp = requests.post(
                f"{base}/images/generations",
                json=payload,
                headers={**headers, "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
        else:
            data = {k: str(v) for k, v in payload.items()}
            with reference.open("rb") as fh:
                files = {"image": (reference.name, fh, "image/png")}
                resp = requests.post(f"{base}/images/edits", data=data, files=files, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.Timeout:
        fail(f"request to {host} timed out after {TIMEOUT}s")
    except requests.exceptions.RequestException as exc:  # connection errors etc.
        fail(f"request to {host} failed: {type(exc).__name__}: {exc}")
    if resp.status_code >= 400:
        http_error("image API error", resp)
    try:
        body = resp.json()
    except ValueError:
        fail(f"image API returned non-JSON response: {resp.text[:300]}")
    if not isinstance(body, dict) or not isinstance(body.get("data"), list) or not body["data"]:
        fail(f"image API response has no data[]: {json.dumps(body, ensure_ascii=False)[:300]}")
    return body


def fetch_image_bytes(item: dict, host: str) -> bytes:
    if item.get("b64_json"):
        try:
            return base64.b64decode(item["b64_json"])
        except (ValueError, TypeError) as exc:
            fail(f"could not decode b64_json from {host}: {exc}")
    url = item.get("url")
    if not url:
        fail(f"image API item has neither b64_json nor url: {json.dumps(item, ensure_ascii=False)[:300]}")
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.exceptions.RequestException as exc:
        fail(f"download of generated image failed: {type(exc).__name__}: {exc}")
    if resp.status_code >= 400:
        http_error("image download error", resp)
    return resp.content


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scientific illustrations from a text prompt.")
    parser.add_argument("--prompt", required=True, help="What to draw.")
    parser.add_argument("--out", default="generated_images", help="Output directory (default ./generated_images).")
    parser.add_argument("--name", default=None, help="File stem; default is a slug of the prompt plus timestamp.")
    parser.add_argument("--size", default="1024x1024", help="WIDTHxHEIGHT; normalized to what the provider accepts.")
    parser.add_argument("--n", type=int, default=1, help="Number of images (1-4).")
    parser.add_argument("--style", choices=sorted(STYLE_TEMPLATES), default="scientific")
    parser.add_argument("--negative", default="", help="Things to avoid in the image.")
    parser.add_argument("--reference", default=None, help="Reference image (OpenAI-style providers only).")
    args = parser.parse_args()

    base = (os.environ.get(ENV_BASE) or "").strip().rstrip("/")
    key = (os.environ.get(ENV_KEY) or "").strip()
    model = (os.environ.get(ENV_MODEL) or "").strip()
    missing = [name for name, value in ((ENV_BASE, base), (ENV_KEY, key), (ENV_MODEL, model)) if not value]
    if missing:
        fail(
            "image provider is not configured (missing " + ", ".join(missing) + "). "
            "Ask the user to open the BioDSH app and fill in 「更多 → 图像生成」 (base URL, API key, model). "
            "Do not guess a provider or ask for the key in chat.",
            missing=missing,
        )
    if not base.startswith(("http://", "https://")):
        fail(f"{ENV_BASE} must start with http:// or https://")
    host = (urlparse(base).hostname or "").lower()

    if not args.prompt.strip():
        fail("--prompt is empty")
    if not 1 <= args.n <= 4:
        fail("--n must be between 1 and 4")

    reference: Path | None = None
    if args.reference:
        reference = Path(args.reference).expanduser()
        if not reference.is_file():
            fail(f"reference image not found: {reference}")
        if host not in EDITS_HOSTS:
            fail(f"provider {host} does not support reference images; run again without --reference")

    try:
        size, size_note = normalize_size(args.size, host, model)
    except ValueError as exc:
        fail(str(exc))

    final_prompt = STYLE_TEMPLATES[args.style] + args.prompt.strip()
    negative = args.negative.strip()
    payload: dict = {"model": model, "prompt": final_prompt, "n": args.n, "size": size}
    if negative:
        if host in NEGATIVE_FIELD_HOSTS:
            payload["negative_prompt"] = negative
        else:
            final_prompt = f"{final_prompt}. Avoid: {negative}."
            payload["prompt"] = final_prompt
    if host in B64_HOSTS and reference is None:
        payload["response_format"] = "b64_json"

    out_dir = Path(args.out).expanduser()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail(f"cannot create output directory {out_dir}: {exc}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = re.sub(r"[^\w.-]+", "-", args.name.strip()) if args.name and args.name.strip() else f"{slugify(args.prompt)}-{stamp}"

    started = time.monotonic()
    body = request_images(base, key, payload, reference, host)

    files: list[str] = []
    warnings: list[str] = []
    if size_note:
        warnings.append(size_note)
    for i, item in enumerate(body["data"], start=1):
        if not isinstance(item, dict):
            continue
        data = fetch_image_bytes(item, host)
        fmt = detect_format(data)
        if fmt != "png":
            warnings.append(f"image {i}: provider returned {fmt} data; saved with .png extension")
        target = out_dir / f"{stem}-{i}.png"
        try:
            target.write_bytes(data)
        except OSError as exc:
            fail(f"cannot write {target}: {exc}")
        files.append(str(target.resolve()))
    if not files:
        fail("image API returned no usable images")

    elapsed = round(time.monotonic() - started, 2)
    summary = {
        "prompt": args.prompt,
        "final_prompt": final_prompt,
        "negative": negative or None,
        "style": args.style,
        "model": model,
        "provider_host": host,
        "size": size,
        "n": args.n,
        "reference": str(reference.resolve()) if reference else None,
        "files": files,
        "generation_json": str((out_dir / "generation.json").resolve()),
        "elapsed_seconds": elapsed,
        "warnings": warnings,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        (out_dir / "generation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        fail(f"cannot write generation.json: {exc}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
