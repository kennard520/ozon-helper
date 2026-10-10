"""图片下载到本地：采集时把源图(1688/Ozon)下到 data/images/<key>/，
返回可通过 webui /media/ 访问的本地路径。源图仍保留(发布时 Ozon 按 URL 拉取)。"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

MEDIA_ROOT = Path(__file__).resolve().parents[1] / "data" / "images"   # ozon-listing-webui/data/images（不随 backend/ 移动）
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


_DEPLOY_DATA_ROOT = Path("/app/ozon-listing-webui/data")
if _DEPLOY_DATA_ROOT.exists():
    MEDIA_ROOT = _DEPLOY_DATA_ROOT / "images"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _safe(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(key or "x")).strip("_") or "x"


def _ext(url: str) -> str:
    m = re.search(r"\.(jpg|jpeg|png|webp|gif)\b", url.lower())
    return "." + (m.group(1) if m else "jpg")


def download_images(urls: list[str], key: str, *, timeout: int = 20) -> list[str]:
    """下载图片到 data/images/<key>/，返回 [/media/<key>/NN.ext]。失败的跳过。"""
    dest = MEDIA_ROOT / _safe(key)
    dest.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    for i, url in enumerate(urls or []):
        url = str(url or "").strip()
        if not url:
            continue
        fname = f"{i:02d}{_ext(url)}"
        fpath = dest / fname
        try:
            if not fpath.exists() or fpath.stat().st_size == 0:
                req = urllib.request.Request(url, headers=_UA)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                if not data:
                    continue
                fpath.write_bytes(data)
            out.append(f"/media/{_safe(key)}/{fname}")
        except Exception:  # noqa: BLE001
            continue
    return out


def download_video(url: str, key: str, *, timeout: int = 60,
                   max_bytes: int = 80 * 1024 * 1024, overwrite: bool = False) -> str:
    """下载单个视频到 data/images/<key>/video.<ext>，返回 /media/<key>/video.<ext>。
    仅供本地预览：淘宝/1688 CDN 的视频在浏览器 <video> 元素里会卡死(防盗链/CDN 不向
    media 元素配信)，落到 /media/ 同源播放才稳。超大(>max_bytes)/失败/非 http → ''。
    overwrite=True 强制重下（AI 重生成视频时同 key 文件名不变，命中旧缓存会预览到旧视频）；
    失败时不留旧字节当"有效缓存"——先删再写，失败返回 ''。"""
    url = str(url or "").strip()
    if not url.startswith("http"):
        return ""
    dest = MEDIA_ROOT / _safe(key)
    dest.mkdir(parents=True, exist_ok=True)
    m = re.search(r"\.(mp4|mov|webm|m4v)\b", url.lower())
    fname = f"video.{m.group(1) if m else 'mp4'}"
    fpath = dest / fname
    try:
        if overwrite or not fpath.exists() or fpath.stat().st_size == 0:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(max_bytes + 1)   # 多读 1 字节用于判超限
            if not data or len(data) > max_bytes:
                return ""
            if overwrite:
                fpath.unlink(missing_ok=True)
            fpath.write_bytes(data)
        return f"/media/{_safe(key)}/{fname}"
    except Exception:  # noqa: BLE001
        return ""


def media_file(rel_path: str) -> Path | None:
    """把 /media/<key>/<file> 映射回磁盘路径，做越界防护。"""
    rel = Path(rel_path.lstrip("/"))
    if rel.is_absolute() or ".." in rel.parts:
        return None
    fpath = MEDIA_ROOT / rel
    return fpath if fpath.exists() and fpath.is_file() else None


def save_upload(key: str, filename: str, data: bytes) -> str:
    """存上传文件到 data/images/<key>/，返回 /media/<key>/<safe> 路径。"""
    import re
    import time
    import uuid
    dest = MEDIA_ROOT / _safe(key)
    dest.mkdir(parents=True, exist_ok=True)
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "bin").lower()
    ext = re.sub(r"[^a-z0-9]", "", ext)[:5] or "bin"
    name = f"up-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}.{ext}"
    (dest / name).write_bytes(data)
    return f"/media/{_safe(key)}/{name}"


def read_media_bytes(rel_path: str, *, timeout: int = 20) -> bytes | None:
    """读 /media/<key>/<file> 本地自传文件的字节，带越界防护。找不到/越界 → None。"""
    rel = str(rel_path or "").strip()
    if not rel.startswith("/media/"):
        return None
    sub = Path(rel[len("/media/"):])           # <key>/<file>
    if sub.is_absolute() or ".." in sub.parts:
        return None
    fpath = MEDIA_ROOT / sub
    if not (fpath.exists() and fpath.is_file()):
        return None
    return fpath.read_bytes()
