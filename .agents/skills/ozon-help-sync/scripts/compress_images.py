# -*- coding: utf-8 -*-
"""
压缩本地图片（>300KB 转 WebP q82），并同步更新 HTML/Markdown 中的引用文件名。
用法: python tools/compress_images.py
"""
import re
import os
from pathlib import Path
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # 允许超大图（源站有 2.4 亿像素大图）

BASE = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb")
HTML_DIR = BASE / "html"
MD_DIR = BASE / "markdown"
IMG_DIR = HTML_DIR / "images"
MIN_SIZE = 300 * 1024  # 300KB

REF_RE = re.compile(r'(images/[0-9a-f]{16})(\.\w+)')
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def compress():
    renamed = {}
    saved = 0
    for p in IMG_DIR.iterdir():
        if not p.is_file() or p.stat().st_size < MIN_SIZE:
            continue
        ext = p.suffix.lower()
        if ext not in ALLOWED_EXT or ext == ".webp":
            continue
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print("OPEN_ERR", p.name, e)
            continue
        rgb = im.convert("RGB") if im.mode not in ("RGBA", "LA", "P") and im.mode != "RGB" else im
        if im.mode in ("RGBA", "LA", "P"):
            rgb = im.convert("RGBA")
        else:
            rgb = im.convert("RGB")
        new_name = p.stem + ".webp"
        new_path = IMG_DIR / new_name
        try:
            rgb.save(new_path, "WEBP", quality=82, method=6)
        except Exception as e:
            print("SAVE_ERR", p.name, e)
            continue
        old_size = p.stat().st_size
        new_size = new_path.stat().st_size
        renamed[p.name] = new_name
        saved += old_size - new_size
        p.unlink()  # 删除原大图
    print(f"压缩: {len(renamed)} 张, 节省 {saved/1024/1024:.1f} MB")

    if not renamed:
        return

    # 更新 HTML 引用
    html_changed = 0
    for f in HTML_DIR.rglob("*.html"):
        text = f.read_text(encoding="utf-8")
        new = text
        for old_name, new_name in renamed.items():
            # 引用形式: images/<hash>.<ext>
            stem = os.path.splitext(old_name)[0]
            pat = re.compile(r'(images/' + re.escape(stem) + r')\.\w+')
            new = pat.sub(r'\1.webp', new)
        if new != text:
            f.write_text(new, encoding="utf-8")
            html_changed += 1

    # 更新 MD 引用
    md_changed = 0
    for f in MD_DIR.rglob("*.md"):
        text = f.read_text(encoding="utf-8")
        new = text
        for old_name, new_name in renamed.items():
            stem = os.path.splitext(old_name)[0]
            pat = re.compile(r'(images/' + re.escape(stem) + r')\.\w+')
            new = pat.sub(r'\1.webp', new)
        if new != text:
            f.write_text(new, encoding="utf-8")
            md_changed += 1
    print(f"更新引用: html {html_changed} 个, md {md_changed} 个")


if __name__ == "__main__":
    compress()
