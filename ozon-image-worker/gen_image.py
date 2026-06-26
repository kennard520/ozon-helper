"""GPT Image 出图（OpenAI 兼容中转站）。独立模块，零项目依赖。"""

from __future__ import annotations

import base64
import json as _json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional, Sequence

DEFAULT_BASE_URL = "https://az.gptplus5.com/v1"
DEFAULT_MODEL = "gpt-image-2-2"
DEFAULT_SIZE = "1024x1536"
DEFAULT_IMAGE_FIELD = "image"
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

NON_PRODUCT_RULE = (
    "STRICT RULE — the image must show ONLY the product and product-relevant information; nothing else. "
    "REMOVE / do not render any non-product content: brand / manufacturer / shop / store names or logos; "
    "guarantees & warranties (e.g. '7-day free trial', money-back); "
    "free-trial / gift / giveaway offers, coupons; "
    "invoices / tax receipts; customization / made-to-order; "
    "service / shipping promises; "
    "sourcing / business claims; "
    "promotions, discounts, badges, awards, ratings, sales counts; "
    "price, contact info, phone, QR codes, links, watermarks. "
    "Keep ONLY content about the product itself: its appearance, features, specs, materials, dimensions and usage."
)

OZON_RU_RULE = (
    " TARGET PLATFORM: Ozon marketplace in RUSSIA. EVERY piece of visible text in the final image MUST be in "
    "correct, natural Russian. There must be ZERO Chinese characters anywhere — translate ALL Chinese text on the "
    "product, packaging, labels, stickers, buttons or graphics into Russian (keep its position, size and style); "
    "if some text cannot be translated cleanly, remove it entirely. Do not leave any Chinese, and add no English "
    "text other than the product's own brand mark."
    " Visual style for the Russian/Ozon market: clean, bright, high-contrast, trustworthy and practical — "
    "realistic and clear, not over-stylized or gaudy."
)

WHITE_MAIN_PROMPT = (
    "Place this exact product, unchanged, centered on a pure solid white (#FFFFFF) background. "
    "Professional e-commerce product photo for a marketplace, soft even studio lighting, sharp focus, "
    "product centered with comfortable margin on all sides. Keep the product shape, color, material, "
    "proportions and details identical to the input. No added text, no logo, no watermark, no price. "
    + NON_PRODUCT_RULE + OZON_RU_RULE
)

SCENE_PROMPT = (
    "Place this exact product (keep it visually identical — same shape, colors, material, proportions and "
    "details as the input) into a natural, appealing real-life usage scene with soft realistic lighting and a "
    "tasteful, uncluttered background. Photorealistic lifestyle product photo. "
    + NON_PRODUCT_RULE +
    " No text, no logo, no watermark, no price." + OZON_RU_RULE
)

LOCALIZE_PROMPT = (
    "Keep this product image's product, layout, background, colors, graphics and icons the same. "
    "Translate the Chinese **product-relevant** text into natural, correct Russian, keeping its position/size/style. "
    + NON_PRODUCT_RULE +
    " Add no new text, no watermark." + OZON_RU_RULE
)


def build_infographic_prompt(*, role: str = "", heading: str = "", bullets: list | None = None) -> str:
    bl = [str(b).strip() for b in (bullets or []) if str(b).strip()]
    parts = [
        "Use the uploaded product as the exact reference; keep its shape, color, material, "
        "proportions and visible details unchanged.",
        f"Create a clean Ozon marketplace {role or 'product'} image, vertical 1024x1536, "
        "white or light background, professional studio quality.",
    ]
    if heading or bl:
        t = "Render the following Russian text clearly and correctly, and render NO other text —"
        if heading:
            t += f' heading: "{heading}";'
        if bl:
            t += " bullets: " + "; ".join(f'"{b}"' for b in bl) + ";"
        parts.append(t)
    else:
        parts.append("No text on the image.")
    parts.append("No Chinese text, no watermark, no logo, no QR code, no price, no contact info. "
                 "Do not invent accessories or functions. " + NON_PRODUCT_RULE + OZON_RU_RULE)
    return " ".join(parts)


class GenImageConfig:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, image_field: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GPTPLUS5_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (base_url or os.environ.get("GPTPLUS5_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("GPTPLUS5_IMAGE_MODEL") or DEFAULT_MODEL
        self.image_field = image_field or os.environ.get("GPTPLUS5_IMAGE_FIELD") or DEFAULT_IMAGE_FIELD

    def auth_headers(self, content_type: str | None = None) -> dict[str, str]:
        h = {"Accept": "application/json", "Authorization": "Bearer " + self.api_key}
        if content_type:
            h["Content-Type"] = content_type
        return h


def _optional_fields(*, model, prompt, n, size, quality, output_format, background) -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = [("model", model), ("prompt", prompt), ("n", str(n))]
    for key, value in (("size", size), ("quality", quality),
                       ("output_format", output_format), ("background", background)):
        if value is not None:
            fields.append((key, value))
    return fields


def build_create_payload(cfg: GenImageConfig, prompt: str, *, n: int = 1, size: str | None = DEFAULT_SIZE,
                         quality: str | None = None, output_format: str | None = None,
                         background: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": cfg.model, "prompt": prompt, "n": n}
    for key, value in (("size", size), ("quality", quality),
                       ("output_format", output_format), ("background", background)):
        if value is not None:
            payload[key] = value
    return payload


def build_edit_request(cfg: GenImageConfig, prompt: str, image_paths: Sequence[str], *,
                       mask_path: str | None = None, n: int = 1, size: str | None = DEFAULT_SIZE,
                       quality: str | None = None, output_format: str | None = None,
                       background: str | None = None) -> tuple[str, list[tuple[str, Any]], list[tuple[str, str]]]:
    url = cfg.base_url + "/images/edits"
    fields = _optional_fields(model=cfg.model, prompt=prompt, n=n, size=size,
                              quality=quality, output_format=output_format, background=background)
    files: list[tuple[str, str]] = [(cfg.image_field, p) for p in image_paths]
    if mask_path:
        files.append(("mask", mask_path))
    return url, fields, files


def serialize_multipart(fields: Sequence[tuple[str, Any]],
                        files: Sequence[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----genimage" + str(int(time.time() * 1000))
    bb = boundary.encode("ascii")
    crlf = b"\r\n"
    chunks: list[bytes] = []
    for key, value in fields:
        if value is None:
            continue
        chunks.append(b"--" + bb + crlf)
        chunks.append(f'Content-Disposition: form-data; name="{key}"'.encode() + crlf + crlf)
        chunks.append(str(value).encode("utf-8") + crlf)
    for key, path in files:
        filename = os.path.basename(path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            content = fh.read()
        chunks.append(b"--" + bb + crlf)
        chunks.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode() + crlf)
        chunks.append(f"Content-Type: {mime}".encode() + crlf + crlf)
        chunks.append(content + crlf)
    chunks.append(b"--" + bb + b"--" + crlf)
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def _default_post(url: str, headers: dict[str, str], body: bytes, *, retries: int = 4, timeout: int = 300) -> dict[str, Any]:
    last = "未知错误"
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return _json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            last = f"HTTP {exc.code}: {text[:500]}"
            if exc.code in RETRY_STATUS and attempt < retries - 1:
                time.sleep(min(4.0 * (2 ** attempt), 60.0))
                continue
            raise RuntimeError(last)
        except urllib.error.URLError as exc:
            last = f"URLError: {exc}"
            if attempt < retries - 1:
                time.sleep(min(4.0 * (2 ** attempt), 60.0))
                continue
            raise RuntimeError(last)
    raise RuntimeError(last)


def _default_fetch(url: str, *, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


HttpPost = Callable[[str, dict[str, str], bytes], dict[str, Any]]
Fetch = Callable[[str], bytes]


def images_from_response(resp: dict[str, Any], *, fetch: Optional[Fetch] = None) -> list[bytes]:
    fetch = fetch or _default_fetch
    out: list[bytes] = []
    for item in (resp.get("data") or []):
        b64 = item.get("b64_json")
        if b64:
            out.append(base64.b64decode(b64))
        elif item.get("url"):
            out.append(fetch(item["url"]))
    return out


def create_image(cfg: GenImageConfig, prompt: str, *, n: int = 1, size: str | None = DEFAULT_SIZE,
                 quality: str | None = None, output_format: str | None = None,
                 background: str | None = None, http_post: Optional[HttpPost] = None) -> dict[str, Any]:
    http_post = http_post or _default_post
    payload = build_create_payload(cfg, prompt, n=n, size=size, quality=quality,
                                   output_format=output_format, background=background)
    body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return http_post(cfg.base_url + "/images/generations", cfg.auth_headers("application/json"), body)


def edit_image(cfg: GenImageConfig, prompt: str, image_paths: Sequence[str], *,
               mask_path: str | None = None, n: int = 1, size: str | None = DEFAULT_SIZE,
               quality: str | None = None, output_format: str | None = None,
               background: str | None = None, http_post: Optional[HttpPost] = None) -> dict[str, Any]:
    http_post = http_post or _default_post
    url, fields, files = build_edit_request(cfg, prompt, image_paths, mask_path=mask_path, n=n,
                                            size=size, quality=quality,
                                            output_format=output_format, background=background)
    body, content_type = serialize_multipart(fields, files)
    return http_post(url, cfg.auth_headers(content_type), body)
