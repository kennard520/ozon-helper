"""发布前把草稿媒体 URL 重写到 OSS（并发上传 + 去重，纯函数 upload 注入）。

插件已把媒体传到「卖家自己的 Ozon 店铺」(ir.ozone.ru) 的场景：这些是 Ozon 原生链接，
本就能渲染，**跳过不再传 OSS**（再传反而走回地理坑）。只有非 Ozon 链接才需要 OSS 兜底。
"""
from __future__ import annotations

import copy
import re
from concurrent.futures import ThreadPoolExecutor

# Ozon 自家 CDN：ir.ozone.ru / cdn*.ozone.ru / *.ozonusercontent.com
_OZON_CDN = re.compile(r"(^|//|\.)(ozone\.ru|ozonusercontent\.com)/", re.I)


def is_ozon_cdn(url) -> bool:
    """URL 是否已是 Ozon 原生 CDN（已托管，无需再传 OSS）。"""
    return bool(_OZON_CDN.search(str(url or "")))


def _all_media_urls(draft: dict) -> list:
    """枚举草稿里全部媒体 URL（主图/图集/视频/富文本内嵌图），用于判定是否需要 OSS。"""
    draft = draft or {}
    urls: set = set()
    for u in draft.get("images") or []:
        if str(u or "").strip():
            urls.add(u)
    if str(draft.get("video_url") or "").strip():
        urls.add(draft["video_url"])
    sr = draft.get("source_raw")
    if isinstance(sr, dict) and sr.get("rich_content_json"):
        _collect_rich(sr["rich_content_json"], urls)
    return list(urls)


def needs_rehost(draft: dict) -> bool:
    """草稿里是否存在非 Ozon 原生媒体（存在才需要 OSS 兜底托管）。"""
    return any(not is_ozon_cdn(u) for u in _all_media_urls(draft))


def _collect_rich(node, urls: set) -> None:
    """收集富文本里所有内嵌图 URL（img.src / img.srcMobile）。"""
    if isinstance(node, list):
        for x in node:
            _collect_rich(x, urls)
    elif isinstance(node, dict):
        img = node.get("img")
        if isinstance(img, dict):
            for k in ("src", "srcMobile"):
                v = img.get(k)
                if isinstance(v, str) and v.strip():
                    urls.add(v)
        for k, v in node.items():
            if k != "img":
                _collect_rich(v, urls)


def _apply_rich(node, mapping: dict) -> None:
    """按 {原URL: OSS URL} 替换富文本内嵌图。"""
    if isinstance(node, list):
        for x in node:
            _apply_rich(x, mapping)
    elif isinstance(node, dict):
        img = node.get("img")
        if isinstance(img, dict):
            for k in ("src", "srcMobile"):
                if isinstance(img.get(k), str) and img[k] in mapping:
                    img[k] = mapping[img[k]]
        for k, v in node.items():
            if k != "img":
                _apply_rich(v, mapping)


def rehost_draft_media(draft: dict, upload, *, max_workers: int = 8) -> tuple[dict, dict]:
    """把草稿里的主图/图集、视频、富文本内嵌图**并发**传到 OSS（同一 URL 只传一次）。
    upload(url_or_localpath)->oss_url（失败抛错）。返回 (新草稿, {"uploaded","failed"})。"""
    draft = draft or {}
    out = dict(draft)
    images = list(draft.get("images") or [])
    video = str(draft.get("video_url") or "").strip()
    sr = draft.get("source_raw")
    rich = None
    if isinstance(sr, dict) and sr.get("rich_content_json"):
        rich = copy.deepcopy(sr["rich_content_json"])

    # 1) 收集所有要传的 URL（去重）；已是 Ozon 原生(ir.ozone.ru 等)的跳过——
    #    那是插件已传到卖家自己店铺的链接，本就能渲染，再传 OSS 反而走回地理坑。
    urls: set = set()
    for u in images:
        if str(u or "").strip() and not is_ozon_cdn(u):
            urls.add(u)
    if video and not is_ozon_cdn(video):
        urls.add(draft["video_url"])
    if rich is not None:
        rich_urls: set = set()
        _collect_rich(rich, rich_urls)
        for u in rich_urls:
            if not is_ozon_cdn(u):
                urls.add(u)

    # 2) 并发上传 → {原URL: OSS URL}（失败保留原 URL）
    mapping: dict = {}
    stats = {"uploaded": 0, "failed": 0}

    def _do(u):
        try:
            return u, upload(u), True
        except Exception:  # noqa: BLE001
            return u, u, False

    if urls:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(urls))) as ex:
            for u, new, ok in ex.map(_do, list(urls)):
                mapping[u] = new
                stats["uploaded" if ok else "failed"] += 1

    # 3) 用 map 改写结构
    out["images"] = [mapping.get(u, u) for u in images]
    if video:
        out["video_url"] = mapping.get(draft["video_url"], draft["video_url"])
    if rich is not None:
        _apply_rich(rich, mapping)
        out["source_raw"] = {**sr, "rich_content_json": rich}
    return out, stats


# ===== 发布前把我们 OSS 的「代理地址」换成「公网直链」=====
# oss_public_base 是国内 ECS 代理(http://ip:8585/oss)，给 webui 省流量用；但 Ozon 抓图服务器
# (俄罗斯) 够不到国内 HTTP:8585 → 商品图空白。发布时统一换成 OSS 公网直链(HTTPS、全球可达)。
RICH_CONTENT_ATTR_ID = 11254
VIDEO_LINK_ATTR_ID = 21841


def public_oss_url(url, settings: dict) -> str:
    """代理地址 {oss_public_base}/{key} → 公网直链 https://{bucket}.{endpoint}/{key}。其它原样返回。"""
    s = settings or {}
    base = str(s.get("oss_public_base") or "").rstrip("/")
    bucket = str(s.get("oss_bucket") or "")
    endpoint = str(s.get("oss_endpoint") or "")
    u = str(url or "")
    if base and bucket and endpoint and u.startswith(base + "/"):
        return "https://" + bucket + "." + endpoint + "/" + u[len(base) + 1:]
    return u


def _map_rich_urls(node, fn) -> None:
    """对富文本里所有内嵌图 url(img.src/srcMobile)应用 fn。"""
    if isinstance(node, list):
        for x in node:
            _map_rich_urls(x, fn)
    elif isinstance(node, dict):
        img = node.get("img")
        if isinstance(img, dict):
            for k in ("src", "srcMobile"):
                if isinstance(img.get(k), str) and img[k].strip():
                    img[k] = fn(img[k])
        for k, v in node.items():
            if k != "img":
                _map_rich_urls(v, fn)


def rewrite_item_media(item: dict, settings: dict) -> dict:
    """发布前把 import item 里所有媒体 URL(图集/视频/富文本内嵌图)换成 OSS 公网直链。返回副本。"""
    import json  # noqa: PLC0415
    it = copy.deepcopy(item or {})

    def fn(u):
        return public_oss_url(u, settings)

    it["images"] = [fn(u) for u in (it.get("images") or [])]
    for ca in (it.get("complex_attributes") or []):
        for a in (ca.get("attributes") or []):
            if str(a.get("id")) == str(VIDEO_LINK_ATTR_ID):
                for v in (a.get("values") or []):
                    if isinstance(v.get("value"), str) and v["value"].strip():
                        v["value"] = fn(v["value"])
    for a in (it.get("attributes") or []):
        if str(a.get("id")) == str(RICH_CONTENT_ATTR_ID):
            for v in (a.get("values") or []):
                raw = v.get("value")
                if isinstance(raw, str) and raw.strip():
                    try:
                        node = json.loads(raw)
                        _map_rich_urls(node, fn)
                        v["value"] = json.dumps(node, ensure_ascii=False, separators=(",", ":"))
                    except Exception:  # noqa: BLE001
                        pass
    return it
