"""NVIDIA NIM helpers for text, VLM understanding, and image generation."""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_TEXT_MODEL = "nvidia/llama-3.1-nemotron-nano-8b-v1"
DEFAULT_VLM_MODEL = "google/paligemma"
DEFAULT_IMAGE_MODEL = "black-forest-labs/flux.1-kontext-dev"
INLINE_IMAGE_B64_LIMIT = 180_000
NVIDIA_TEXT_BASE = "https://integrate.api.nvidia.com"
NVIDIA_AI_BASE = "https://ai.api.nvidia.com"
MODEL_PRESETS = {
    "text": [
        "deepseek-ai/deepseek-v4-flash",
        "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "nvidia/nemotron-3-nano-30b-a3b",
    ],
    "multimodal": [
        DEFAULT_VLM_MODEL,
    ],
    "image": [
        DEFAULT_IMAGE_MODEL,
    ],
    "video": [],
}

UrlOpen = Callable[..., Any]


def is_nvidia_config(cfg: dict | None) -> bool:
    cfg = cfg or {}
    engine = str(cfg.get("engine") or "").strip().lower()
    base = str(cfg.get("base") or cfg.get("api_base") or "").strip().lower()
    platform = str(cfg.get("platform") or "").strip().lower()
    return engine == "nvidia" or "nvidia" in platform or "nvidia.com" in base


def model_presets(kind: str = "") -> list[str]:
    use = str(kind or "").strip().lower()
    if use in MODEL_PRESETS:
        return list(MODEL_PRESETS[use])
    out: list[str] = []
    for key in ("text", "multimodal", "image"):
        out.extend(MODEL_PRESETS[key])
    return list(dict.fromkeys(out))


def _clean_base(base: str, *, family: str) -> str:
    raw = str(base or "").strip().rstrip("/")
    if not raw:
        return NVIDIA_TEXT_BASE if family == "text" else NVIDIA_AI_BASE
    low = raw.lower()
    if family == "text" and "ai.api.nvidia.com" in low:
        return NVIDIA_TEXT_BASE
    if family != "text" and "integrate.api.nvidia.com" in low:
        return NVIDIA_AI_BASE
    if raw.endswith("/v1"):
        raw = raw[:-3].rstrip("/")
    return raw


def _json_post(url: str, key: str, payload: dict[str, Any], *, opener: UrlOpen | None = None,
               timeout: int = 180) -> dict[str, Any]:
    opener = opener or urlopen
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    try:
        with opener(req, timeout=timeout) as res:  # noqa: S310
            return json.loads(res.read().decode("utf-8", "replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"NVIDIA HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"NVIDIA connection failed: {exc}") from exc


def _extract_chat_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = data.get("text") or data.get("output") or data.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        content = "".join(parts)
    if content is None:
        raise RuntimeError(f"NVIDIA response format error: {json.dumps(data, ensure_ascii=False)[:300]}")
    return str(content).strip()


def nvidia_chat(cfg: dict, system: str, user: str, *, opener: UrlOpen | None = None) -> str:
    key = str((cfg or {}).get("key") or (cfg or {}).get("api_key") or "").strip()
    if not key:
        raise RuntimeError("NVIDIA API key is not configured")
    base = _clean_base(str((cfg or {}).get("base") or (cfg or {}).get("api_base") or ""), family="text")
    model = str((cfg or {}).get("model") or "").strip() or DEFAULT_TEXT_MODEL
    payload = {
        "model": model,
        "temperature": 0.3,
        "stream": False,
        "messages": [
            {"role": "system", "content": str(system or "")},
            {"role": "user", "content": str(user or "")},
        ],
    }
    data = _json_post(f"{base}/v1/chat/completions", key, payload, opener=opener, timeout=180)
    return _extract_chat_content(data)


def _vlm_model(model: str) -> str:
    value = str(model or "").strip()
    low = value.lower()
    if not value:
        return DEFAULT_VLM_MODEL
    if any(marker in low for marker in ("paligemma", "vision", "-vl", "_vl", "vl-", "vila", "multimodal", "omni")):
        return value
    return DEFAULT_VLM_MODEL


def _mime_for_url(url: str, content_type: str = "") -> str:
    if content_type:
        return content_type.split(";", 1)[0].strip() or "image/jpeg"
    return mimetypes.guess_type(url)[0] or "image/jpeg"


def _data_uri_from_bytes(data: bytes, mime: str, *, max_b64: int | None = None) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    if max_b64 is not None and len(b64) >= max_b64:
        raise RuntimeError("NVIDIA inline image exceeds 180KB; compress it or use the NVCF asset API")
    return f"data:{mime};base64,{b64}"


def image_to_data_uri(image: str, *, opener: UrlOpen | None = None,
                      max_b64: int | None = None) -> str:
    src = str(image or "").strip()
    if not src:
        raise ValueError("image is empty")
    if src.startswith("data:image/"):
        marker = ";base64,"
        if marker in src:
            b64 = src.split(marker, 1)[1]
            if max_b64 is not None and len(b64) >= max_b64:
                raise RuntimeError("NVIDIA inline image exceeds 180KB; compress it or use the NVCF asset API")
        return src
    opener = opener or urlopen
    if src.startswith(("http://", "https://")):
        req = Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with opener(req, timeout=60) as res:  # noqa: S310
            data = res.read()
            headers = getattr(res, "headers", {}) or {}
            mime = _mime_for_url(src, str(headers.get("Content-Type") or ""))
        return _data_uri_from_bytes(data, mime, max_b64=max_b64)
    path = Path(src)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return _data_uri_from_bytes(path.read_bytes(), mime, max_b64=max_b64)


def nvidia_vlm_chat(cfg: dict, system: str, user: str, images: list[str] | None = None, *,
                    opener: UrlOpen | None = None) -> str:
    key = str((cfg or {}).get("key") or (cfg or {}).get("api_key") or "").strip()
    if not key:
        raise RuntimeError("NVIDIA API key is not configured")
    base = _clean_base(str((cfg or {}).get("base") or (cfg or {}).get("api_base") or ""), family="ai")
    model = _vlm_model(str((cfg or {}).get("model") or ""))
    image_tag = ""
    if images:
        data_uri = image_to_data_uri(str(images[0]), opener=opener, max_b64=INLINE_IMAGE_B64_LIMIT)
        image_tag = f'\n<img src="{data_uri}" />'
    content = f"{str(system or '').strip()}\n\n{str(user or '').strip()}{image_tag}".strip()
    payload = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 1024,
        "temperature": 0.2,
        "top_p": 0.7,
        "stream": False,
    }
    data = _json_post(f"{base}/v1/vlm/{model}", key, payload, opener=opener, timeout=180)
    return _extract_chat_content(data)


def _nvidia_dims(size: str | None) -> tuple[int, int]:
    allowed = [768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344]
    width, height = 1024, 1024
    if size and "x" in str(size).lower():
        a, b = str(size).lower().split("x", 1)
        try:
            width, height = int(a), int(b)
        except ValueError:
            pass

    def nearest(v: int) -> int:
        return min(allowed, key=lambda x: abs(x - v))

    return nearest(width), nearest(height)


def _normalize_image_response(data: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    raw_items = data.get("data")
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                b64 = item.get("b64_json") or item.get("base64")
                url = item.get("url")
                if b64:
                    items.append({"b64_json": str(b64)})
                elif url:
                    items.append({"url": str(url)})
    artifacts = data.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict):
                b64 = item.get("base64") or item.get("b64_json")
                if b64:
                    items.append({"b64_json": str(b64)})
    for key in ("b64_json", "base64", "image"):
        if data.get(key):
            items.append({"b64_json": str(data[key])})
    if data.get("url"):
        items.append({"url": str(data["url"])})
    if not items:
        raise RuntimeError(f"NVIDIA image response format error: {json.dumps(data, ensure_ascii=False)[:300]}")
    return {"data": items}


def nvidia_generate_image(cfg: dict, prompt: str, *, size: str | None = None,
                          image_data_uri: str | None = None,
                          opener: UrlOpen | None = None) -> dict[str, Any]:
    key = str((cfg or {}).get("key") or (cfg or {}).get("api_key") or "").strip()
    if not key:
        raise RuntimeError("NVIDIA API key is not configured")
    base = _clean_base(str((cfg or {}).get("base") or (cfg or {}).get("api_base") or ""), family="ai")
    model = str((cfg or {}).get("model") or "").strip() or DEFAULT_IMAGE_MODEL
    width, height = _nvidia_dims(size)
    payload: dict[str, Any] = {
        "prompt": str(prompt or "").strip(),
        "width": width,
        "height": height,
        "samples": 1,
        "seed": 0,
    }
    if not payload["prompt"]:
        raise ValueError("NVIDIA image prompt is empty")
    if "schnell" not in model.lower():
        payload["steps"] = 30
        payload["cfg_scale"] = 5
    if image_data_uri is not None:
        payload["image"] = image_data_uri
    elif "kontext" in model.lower() or "edit" in model.lower():
        payload["image"] = None
    data = _json_post(f"{base}/v1/genai/{model}", key, payload, opener=opener, timeout=300)
    return _normalize_image_response(data)
