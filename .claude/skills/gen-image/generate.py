#!/usr/bin/env python3
"""
gen-image skill script: call an OpenAI-compatible image gateway.

Modes for product-image workflows:
- create: text -> image, POST /images/generations
- edit: reference image(s) + prompt -> image, POST /images/edits
- mask: source image + alpha mask + prompt -> local edit, POST /images/edits

Pure standard library. No third-party dependencies.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import winreg  # type: ignore  # Windows only
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASE_URL = "https://az.gptplus5.com/v1"
# Your provided curl examples use gpt-image-2-2. Override with GPTPLUS5_IMAGE_MODEL if needed.
DEFAULT_MODEL = "gpt-image-2-2"
DEFAULT_SIZE = "1024x1536"  # Ozon 3:4 portrait default
# Your provided curl examples repeat multipart field name `image` for multiple images.
DEFAULT_IMAGE_FIELD = "image"
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_FILE_BYTES = 50 * 1024 * 1024


def _get_windows_env(name: str) -> Optional[str]:
    """Read a Windows user/machine environment variable, useful in Git Bash/MSYS."""
    if not winreg:
        return None
    locations = [
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
    ]
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
                if value:
                    return str(value)
        except Exception:
            continue
    return None


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value:
        return value
    value = _get_windows_env(name)
    if value:
        return value
    return default


def _get_api_key() -> str:
    """Prefer gateway key, then OpenAI-compatible key name. Never hard-code secrets."""
    for name in ("GPTPLUS5_API_KEY", "OPENAI_API_KEY"):
        value = _get_env(name)
        if value:
            return value
    raise RuntimeError(
        "未配置 API key。请设置环境变量 GPTPLUS5_API_KEY；若你的中转站兼容 OpenAI，也可设置 OPENAI_API_KEY。"
    )


def _redact(value: str) -> str:
    """Remove secrets from errors/manifests."""
    value = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", value)
    value = re.sub(r"Bearer\s+[A-Za-z0-9_\-.]+", "Bearer ***", value, flags=re.I)
    return value


def _auth_headers(api_key: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    if extra:
        headers.update(extra)
    return headers


def _sleep_seconds_from_retry_after(header_value: Optional[str], attempt: int) -> float:
    if header_value:
        try:
            return min(float(header_value), 90.0)
        except ValueError:
            pass
    return min(4.0 * (2 ** attempt), 60.0)


def _post(url: str, data: bytes, headers: Dict[str, str], retries: int = 4, timeout: int = 300) -> Dict[str, Any]:
    """POST with retry/backoff for 429/5xx. Returns parsed JSON."""
    last_error = "未知错误"
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
                parsed = json.loads(text)
                parsed.setdefault("_meta", {})["x_request_id"] = resp.headers.get("x-request-id")
                parsed["_meta"]["status"] = resp.status
                return parsed
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            last_error = _redact(f"HTTP {exc.code}: {body[:1000]}")
            if exc.code in RETRY_STATUS and attempt < retries - 1:
                time.sleep(_sleep_seconds_from_retry_after(exc.headers.get("retry-after"), attempt))
                continue
            raise RuntimeError(last_error)
        except urllib.error.URLError as exc:
            last_error = _redact(f"URLError: {exc}")
            if attempt < retries - 1:
                time.sleep(_sleep_seconds_from_retry_after(None, attempt))
                continue
            raise RuntimeError(last_error)
    raise RuntimeError(last_error)


def _get(url: str, headers: Dict[str, str], timeout: int = 120) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(_redact(f"HTTP {exc.code}: {body[:1000]}"))


def _multipart(fields: Sequence[Tuple[str, Any]], files: Sequence[Tuple[str, str]]) -> Tuple[bytes, str]:
    """Build multipart/form-data. Allows repeated file fields such as image, image[]."""
    boundary = "----genimage" + str(int(time.time() * 1000))
    boundary_bytes = boundary.encode("ascii")
    chunks: List[bytes] = []
    crlf = b"\r\n"

    for key, value in fields:
        if value is None:
            continue
        chunks.append(b"--" + boundary_bytes + crlf)
        chunks.append(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8") + crlf + crlf)
        chunks.append(str(value).encode("utf-8") + crlf)

    for key, path in files:
        filename = os.path.basename(path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            content = handle.read()
        chunks.append(b"--" + boundary_bytes + crlf)
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode("utf-8") + crlf
        )
        chunks.append(f"Content-Type: {mime}".encode("utf-8") + crlf + crlf)
        chunks.append(content + crlf)

    chunks.append(b"--" + boundary_bytes + b"--" + crlf)
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary


def _optional_json_payload(
    *,
    model: str,
    prompt: str,
    n: int,
    size: Optional[str],
    quality: Optional[str],
    output_format: Optional[str],
    background: Optional[str],
    compression: Optional[int],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": model, "prompt": prompt, "n": n}
    for key, value in (
        ("size", size),
        ("quality", quality),
        ("output_format", output_format),
        ("background", background),
        ("output_compression", compression),
    ):
        if value is not None:
            payload[key] = value
    return payload


def _optional_multipart_fields(
    *,
    model: str,
    prompt: str,
    n: int,
    size: Optional[str],
    quality: Optional[str],
    output_format: Optional[str],
    background: Optional[str],
    compression: Optional[int],
) -> List[Tuple[str, Any]]:
    fields: List[Tuple[str, Any]] = [("model", model), ("prompt", prompt), ("n", str(n))]
    for key, value in (
        ("size", size),
        ("quality", quality),
        ("output_format", output_format),
        ("background", background),
        ("output_compression", compression),
    ):
        if value is not None:
            fields.append((key, value))
    return fields


def create_image(
    *,
    base_url: str,
    api_key: str,
    prompt: str,
    model: str,
    n: int,
    size: Optional[str],
    quality: Optional[str],
    output_format: Optional[str],
    background: Optional[str],
    compression: Optional[int],
) -> Dict[str, Any]:
    payload = _optional_json_payload(
        model=model,
        prompt=prompt,
        n=n,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        compression=compression,
    )
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = _auth_headers(api_key, {"Content-Type": "application/json"})
    return _post(base_url.rstrip("/") + "/images/generations", data, headers)


def edit_image(
    *,
    base_url: str,
    api_key: str,
    prompt: str,
    model: str,
    n: int,
    size: Optional[str],
    quality: Optional[str],
    output_format: Optional[str],
    background: Optional[str],
    compression: Optional[int],
    image_paths: Sequence[str],
    mask_path: Optional[str],
    image_field: str,
) -> Dict[str, Any]:
    fields = _optional_multipart_fields(
        model=model,
        prompt=prompt,
        n=n,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        compression=compression,
    )
    files: List[Tuple[str, str]] = [(image_field, path) for path in image_paths]
    if mask_path:
        files.append(("mask", mask_path))
    body, content_type = _multipart(fields, files)
    headers = _auth_headers(api_key, {"Content-Type": content_type})
    return _post(base_url.rstrip("/") + "/images/edits", body, headers)


def _save_images(resp: Dict[str, Any], out_dir: str, name_prefix: str, output_format: Optional[str]) -> List[Dict[str, Any]]:
    os.makedirs(out_dir, exist_ok=True)
    saved: List[Dict[str, Any]] = []
    ext = (output_format or "png").lower()
    if ext == "jpeg":
        ext = "jpg"

    for index, item in enumerate(resp.get("data", [])):
        out_path = os.path.join(out_dir, f"{name_prefix}_{index}.{ext}")
        b64 = item.get("b64_json")
        if b64:
            with open(out_path, "wb") as handle:
                handle.write(base64.b64decode(b64))
            source = "b64_json"
        elif item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=120) as response:
                blob = response.read()
            with open(out_path, "wb") as handle:
                handle.write(blob)
            source = "url"
        else:
            continue
        saved.append(
            {
                "index": index,
                "path": out_path.replace("\\", "/"),
                "bytes": os.path.getsize(out_path),
                "source": source,
            }
        )
    return saved


def _default_out_dir() -> str:
    home = os.path.expanduser("~")
    today = time.strftime("%Y-%m-%d")
    return os.path.join(home, "Downloads", "gen-image", today)


def _safe_prefix(name: Optional[str]) -> str:
    value = name or ("img_" + time.strftime("%Y%m%d_%H%M%S"))
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    return value or ("img_" + time.strftime("%Y%m%d_%H%M%S"))


def _png_info(path: str) -> Optional[Dict[str, Any]]:
    """Return minimal PNG info if this is a PNG, otherwise None."""
    with open(path, "rb") as handle:
        header = handle.read(33)
    if len(header) < 33 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    bit_depth = header[24]
    color_type = header[25]
    return {
        "format": "png",
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "has_alpha": color_type in (4, 6),
    }


def _validate_existing_files(paths: Iterable[str]) -> None:
    for path in paths:
        if not path:
            continue
        if not os.path.exists(path):
            raise RuntimeError(f"文件不存在: {path}")
        if not os.path.isfile(path):
            raise RuntimeError(f"不是普通文件: {path}")
        if os.path.getsize(path) > MAX_FILE_BYTES:
            raise RuntimeError(f"文件超过 50MB，建议先压缩: {path}")


def _validate_mask(source_path: str, mask_path: str, strict: bool) -> List[str]:
    """Validate common mask pitfalls. Returns warnings."""
    warnings: List[str] = []
    if not strict:
        return warnings

    source_ext = os.path.splitext(source_path)[1].lower()
    mask_ext = os.path.splitext(mask_path)[1].lower()
    if source_ext != mask_ext:
        raise RuntimeError("蒙版模式建议原图和 mask 使用同一格式；最稳是二者都保存为 PNG。")
    if mask_ext != ".png":
        raise RuntimeError("蒙版必须带 alpha 通道；请把原图和 mask 都保存为 PNG。")

    source_info = _png_info(source_path)
    mask_info = _png_info(mask_path)
    if not source_info or not mask_info:
        raise RuntimeError("无法读取 PNG 信息，请确认原图和 mask 是有效 PNG 文件。")
    if (source_info["width"], source_info["height"]) != (mask_info["width"], mask_info["height"]):
        raise RuntimeError(
            f"原图和 mask 尺寸不一致: 原图 {source_info['width']}x{source_info['height']}, "
            f"mask {mask_info['width']}x{mask_info['height']}"
        )
    if not mask_info["has_alpha"]:
        raise RuntimeError("mask PNG 没有 alpha 通道。请使用透明区域/不透明区域的 RGBA PNG 蒙版。")
    return warnings


def _resolve_mode(mode: str, images: Sequence[str], mask: Optional[str]) -> str:
    if mode != "auto":
        return mode
    if mask:
        return "mask"
    if images:
        return "edit"
    return "create"


def _write_manifest(path: str, manifest: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def _usage(resp: Dict[str, Any]) -> Dict[str, Any]:
    usage = resp.get("usage") or {}
    return {
        "input": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output": usage.get("output_tokens", usage.get("completion_tokens")),
        "total": usage.get("total_tokens"),
        "raw": usage,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call GPT Image through an OpenAI-compatible gateway for ecommerce product images."
    )
    parser.add_argument("prompt", nargs="?", help="生成/修改提示词")
    parser.add_argument("--mode", choices=["auto", "create", "edit", "mask"], default="auto")
    parser.add_argument("--image", action="append", default=[], help="参考图/原图路径；可重复传多张")
    parser.add_argument("--mask", help="局部修改蒙版 PNG；给了就走 mask 模式")
    parser.add_argument(
        "--image-field",
        default=_get_env("GPTPLUS5_IMAGE_FIELD", DEFAULT_IMAGE_FIELD),
        help="multipart 图片字段名。你的中转站 curl 示例用 image；若网关要求 image[] 可改成 image[]。",
    )
    parser.add_argument("--model", default=_get_env("GPTPLUS5_IMAGE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=_get_env("GPTPLUS5_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", choices=["low", "medium", "high", "auto"], default=None)
    parser.add_argument("--format", dest="output_format", choices=["png", "jpeg", "webp"], default=None)
    parser.add_argument("--background", choices=["transparent", "opaque", "auto"], default=None)
    parser.add_argument("--compression", type=int, default=None, help="JPEG/WebP 压缩 0-100，网关支持时生效")
    parser.add_argument("--out", default=None, help="输出目录，默认 ~/Downloads/gen-image/YYYY-MM-DD/")
    parser.add_argument("--name", default=None, help="输出文件名前缀")
    parser.add_argument("--manifest", default=os.path.join(HERE, "_last.json"), help="结果 JSON 路径")
    parser.add_argument("--no-strict-mask", action="store_true", help="跳过 mask PNG 尺寸/alpha 检查")
    parser.add_argument("--list-models", action="store_true", help="列出中转站可用模型并退出")
    parser.add_argument("--dry-run", action="store_true", help="只输出将要请求的参数，不调用接口")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    base_url = str(args.base_url).rstrip("/")

    api_key = None
    if args.list_models or not args.dry_run:
        try:
            api_key = _get_api_key()
        except Exception as exc:
            print(f"ERROR: {_redact(str(exc))}")
            return 1

    if args.list_models:
        try:
            models = _get(base_url + "/models", _auth_headers(api_key or ""))
            print(json.dumps(models, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(f"ERROR: {_redact(str(exc))}")
            return 1

    if not args.prompt:
        print("ERROR: 缺少 prompt。")
        return 1

    if args.compression is not None and not 0 <= args.compression <= 100:
        print("ERROR: --compression 必须是 0-100。")
        return 1
    if args.n < 1 or args.n > 10:
        print("ERROR: --n 建议 1-10。")
        return 1

    mode = _resolve_mode(args.mode, args.image, args.mask)
    out_dir = args.out or _default_out_dir()
    name_prefix = _safe_prefix(args.name)
    warnings: List[str] = []

    try:
        if mode == "create":
            if args.mask:
                raise RuntimeError("create 模式不能传 --mask。需要局部修改请用 --mode mask。")
        elif mode in ("edit", "mask"):
            if not args.image:
                raise RuntimeError(f"{mode} 模式必须传 --image。")
            _validate_existing_files(args.image)
            if args.mask:
                _validate_existing_files([args.mask])
        if mode == "mask":
            if not args.mask:
                raise RuntimeError("mask 模式必须传 --mask。")
            warnings.extend(_validate_mask(args.image[0], args.mask, strict=not args.no_strict_mask))

        request_summary = {
            "mode": mode,
            "model": args.model,
            "base_url": base_url,
            "prompt": args.prompt,
            "images_in": args.image,
            "mask_in": args.mask,
            "image_field": args.image_field if mode in ("edit", "mask") else None,
            "size": args.size,
            "quality": args.quality,
            "output_format": args.output_format,
            "background": args.background,
            "compression": args.compression,
            "n": args.n,
            "out_dir": out_dir,
            "warnings": warnings,
        }

        if args.dry_run:
            manifest = {"ok": True, "dry_run": True, **request_summary, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            _write_manifest(args.manifest, manifest)
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            return 0

        if mode == "create":
            response = create_image(
                base_url=base_url,
                api_key=api_key or "",
                prompt=args.prompt,
                model=args.model,
                n=args.n,
                size=args.size,
                quality=args.quality,
                output_format=args.output_format,
                background=args.background,
                compression=args.compression,
            )
        else:
            response = edit_image(
                base_url=base_url,
                api_key=api_key or "",
                prompt=args.prompt,
                model=args.model,
                n=args.n,
                size=args.size,
                quality=args.quality,
                output_format=args.output_format,
                background=args.background,
                compression=args.compression,
                image_paths=args.image,
                mask_path=args.mask,
                image_field=args.image_field,
            )

        saved = _save_images(response, out_dir, name_prefix, args.output_format)
        tokens = _usage(response)
        manifest = {
            "ok": bool(saved),
            **request_summary,
            "images": saved,
            "tokens": tokens,
            "response_meta": response.get("_meta", {}),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _write_manifest(args.manifest, manifest)

        if saved:
            print(f"OK {mode} {args.model} -> {len(saved)} 张, tokens total={tokens['total']}")
            for item in saved:
                print(item["path"])
            return 0

        print(f"ERROR: 接口返回无图。usage={tokens['raw']}")
        return 1

    except Exception as exc:  # noqa: BLE001
        manifest = {
            "ok": False,
            "mode": mode,
            "model": args.model,
            "base_url": base_url,
            "prompt": args.prompt,
            "images_in": args.image,
            "mask_in": args.mask,
            "error": _redact(str(exc)),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _write_manifest(args.manifest, manifest)
        print(f"ERROR: {manifest['error']}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
