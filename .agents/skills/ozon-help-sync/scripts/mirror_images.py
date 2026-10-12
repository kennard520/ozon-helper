# -*- coding: utf-8 -*-
"""
镜像 Ozon 帮助中心图片到本地，并把 HTML / Markdown 中的远程图片地址替换为本地相对路径。

用法: python tools/mirror_images.py
"""
import os
import re
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path(r"E:\personal\ozon-helper\ozon-help-kb")
HTML_DIR = BASE / "html"
MD_DIR = BASE / "markdown"
IMG_DIR = HTML_DIR / "images"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}

IMG_RE = re.compile(r'(<img[^>]*\ssrc=")([^"]+)(\")', re.I)
MD_IMG_RE = re.compile(r'(!\[[^\]]*\]\()([^)\s]+)(\))')


def collect_urls():
    urls = set()
    # HTML 中可能仍有少量远程图（替换失败/未替换页面）
    for p in HTML_DIR.rglob("*.html"):
        text = p.read_text(encoding="utf-8")
        for m in IMG_RE.finditer(text):
            u = m.group(2)
            if u.startswith("http"):
                urls.add(u)
    # Markdown 中图片链接未被替换，仍为远程 URL —— 以它为准收集全量
    for p in MD_DIR.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        for m in MD_IMG_RE.finditer(text):
            u = m.group(2)
            if u.startswith("http"):
                urls.add(u)
    return urls


def normalize_url(url):
    """对 URL 路径中的非 ASCII 字符做百分号编码，避免 urllib 编码错误。"""
    try:
        parts = urllib.parse.urlsplit(url)
        path = urllib.parse.quote(parts.path, safe="/%")
        query = urllib.parse.quote(parts.query, safe="=&%")
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))
    except Exception:
        return url


def download_one(url):
    try:
        parsed = urllib.parse.urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            ext = ".img"
        name = hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ext
        dest = IMG_DIR / name
        if dest.exists() and dest.stat().st_size > 0:
            return url, name, "cached"
        # 该图已被压缩脚本转成 webp
        webp_dest = IMG_DIR / (hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ".webp")
        if webp_dest.exists() and webp_dest.stat().st_size > 0:
            return url, webp_dest.name, "cached-webp"
        target = normalize_url(url)
        data = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(target, headers=UA)
                with urllib.request.urlopen(req, timeout=40) as r:
                    data = r.read()
                break
            except Exception:
                if attempt == 2:
                    raise
        if not data:
            return url, None, "empty"
        dest.write_bytes(data)
        return url, name, "ok"
    except Exception as e:
        return url, None, f"err:{type(e).__name__}"


def rewrite(path, mapping, prefix_kind):
    """把文件里的远程图片 URL 替换为本地相对路径。prefix_kind: 'html' 或 'md'。"""
    text = path.read_text(encoding="utf-8")
    if prefix_kind == "html":
        depth = len([p for p in path.relative_to(HTML_DIR).parts if p != "index.html"]) - 1  # 目录层级（不含文件名）
        rel = ("../" * depth) + "images/" if depth > 0 else "images/"
    else:
        depth = len(path.relative_to(MD_DIR).parts) - 1
        rel = ("../" * depth) + "images/"

    def rep(m):
        url = m.group(2)
        name = mapping.get(url)
        if not name:
            return m.group(0)
        return m.group(1) + rel + name + m.group(3)

    new = IMG_RE.sub(rep, text)
    if prefix_kind == "md":
        def rep_md(m):
            url = m.group(2)
            name = mapping.get(url)
            if not name:
                return m.group(0)
            return m.group(1) + rel + name + m.group(3)
        new = MD_IMG_RE.sub(rep_md, new)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main():
    urls = collect_urls()
    print("图片总数:", len(urls))
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {}
    stats = {"ok": 0, "cached": 0, "fail": 0}
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(download_one, u): u for u in urls}
        done = 0
        for fut in as_completed(futs):
            url, name, status = fut.result()
            done += 1
            if name:
                mapping[url] = name
            if status == "ok":
                stats["ok"] += 1
            elif status == "cached":
                stats["cached"] += 1
            else:
                stats["fail"] += 1
                print("FAIL", status, url[:120])
            if done % 200 == 0:
                print(f"... {done}/{len(urls)}")

    print("下载统计:", stats)
    if not mapping:
        print("无可用图片，跳过替换")
        return

    changed_h = sum(1 for p in HTML_DIR.rglob("*.html") if rewrite(p, mapping, "html"))
    changed_m = sum(1 for p in MD_DIR.rglob("*.md") if rewrite(p, mapping, "md"))
    print(f"已替换: html {changed_h} 个文件, md {changed_m} 个文件")


if __name__ == "__main__":
    main()
