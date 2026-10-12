# -*- coding: utf-8 -*-
"""检查 HTML/MD 图片引用与 images/ 目录文件的一致性，找出断链与孤儿文件。"""
import re
from pathlib import Path

BASE = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb")
IMG_DIR = BASE / "html" / "images"

referenced = set()
for p in (BASE / "html").rglob("*.html"):
    t = p.read_text(encoding="utf-8")
    for m in re.finditer(r'images/([0-9a-f]{16}\.\w+)', t):
        referenced.add(m.group(1))
for p in (BASE / "markdown").rglob("*.md"):
    t = p.read_text(encoding="utf-8")
    for m in re.finditer(r'images/([0-9a-f]{16}\.\w+)', t):
        referenced.add(m.group(1))

existing = {f.name for f in IMG_DIR.iterdir() if f.is_file()}
missing = sorted(r for r in referenced if r not in existing)
orphans = sorted(f for f in existing if f not in referenced)

print("HTML/MD 引用的图片名:", len(referenced))
print("images/ 目录文件:", len(existing))
print("断链(引用了但文件不存在):", len(missing))
for m in missing[:20]:
    print("  MISSING", m)
print("孤儿文件(存在但未被引用):", len(orphans))
for m in orphans[:20]:
    print("  ORPHAN", m)
