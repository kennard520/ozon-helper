# -*- coding: utf-8 -*-
"""统计 MD / HTML 中的图片引用与 raw JSON 中的图片总数对比。"""
import json
import re
from pathlib import Path

BASE = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb")
RAW = BASE / "raw" / "ozon_help_zh_raw.json"

# raw JSON 里的图片 URL
with open(RAW, encoding="utf-8") as f:
    data = json.load(f)

raw_urls = set()
def scan(n):
    if not isinstance(n, dict):
        return
    t = n.get("type")
    if t in ("pictureBlock", "inlinePicture"):
        src = (n.get("attrs") or {}).get("src")
        if src:
            raw_urls.add(src)
    if t == "gallery":
        for im in ((n.get("attrs") or {}).get("images") or []):
            if im.get("src"):
                raw_urls.add(im["src"])
    for c in n.get("content") or []:
        scan(c)
for d in data["docs"]:
    cj = d.get("contentJson")
    if cj:
        try:
            scan(json.loads(cj))
        except Exception:
            pass
print("RAW 图片 URL 总数:", len(raw_urls))

# MD 统计
md_http = 0
md_local = 0
md_total = 0
md_files = 0
for p in (BASE / "markdown").rglob("*.md"):
    md_files += 1
    t = p.read_text(encoding="utf-8")
    md_total += len(re.findall(r'!\[[^\]]*\]\([^)]*\)', t))
    md_http += len(re.findall(r'!\[[^\]]*\]\(https?://[^)]*\)', t))
    md_local += len(re.findall(r'!\[[^\]]*\]\((?:\.\./)*images/[^)]*\)', t))
print(f"MD 文件: {md_files}, 图片引用总数: {md_total}, 远程: {md_http}, 本地: {md_local}")

# HTML 统计
html_http = 0
html_local = 0
html_total = 0
html_files = 0
for p in (BASE / "html").rglob("*.html"):
    html_files += 1
    t = p.read_text(encoding="utf-8")
    html_total += len(re.findall(r'<img[^>]*>', t))
    html_http += len(re.findall(r'src="https?://[^"]*"', t))
    html_local += len(re.findall(r'src="(?:\.\./)*images/[^"]*"', t))
print(f"HTML 文件: {html_files}, img 标签总数: {html_total}, 远程: {html_http}, 本地: {html_local}")
