# -*- coding: utf-8 -*-
"""把 markdown/ 全部 267 篇合并为一个 combined.md（供只接受单文件的 AI 工具整库加载）。"""
import re
from pathlib import Path

MD_DIR = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb\markdown")
OUT = Path(r"E:\code\zqr\ozon-helper\ozon-help-kb\combined.md")

files = sorted(MD_DIR.rglob("*.md"))
parts = ["# Ozon 帮助中心知识库（中文版）\n",
         "本文档是 Ozon Global 卖家帮助中心中文版（region=CHN）全部文章的单文件合并版，共 %d 篇。每篇以 H2 标题分隔。" % len(files),
         ""]
for f in files:
    t = f.read_text(encoding="utf-8")
    # 解析 frontmatter
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', t, re.S)
    if m:
        fm, body = m.group(1), m.group(2)
        title = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.M)
        path = re.search(r'^path:\s*(.+)$', fm, re.M)
        title = (title.group(1).strip() if title else f.name)
        path = (path.group(1).strip() if path else "")
        body = body.strip()
    else:
        title = f.stem
        path = ""
        body = t.strip()
    # 相对路径
    rel = f.relative_to(MD_DIR)
    parts.append("\n---\n\n## %s\n" % title)
    parts.append("* 文件：`markdown/%s`" % rel.as_posix())
    if path:
        parts.append("* 路径：`%s`" % path)
    parts.append("\n" + body)

OUT.write_text("\n".join(parts), encoding="utf-8")
print("OK: 合并 %d 篇 -> combined.md (%d KB)" % (len(files), OUT.stat().st_size // 1024))
