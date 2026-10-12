# -*- coding: utf-8 -*-
"""抽查特殊节点（note/link/picture/table/geo/file）的 attrs 值。"""
import json

RAW = r"E:\code\zqr\ozon-helper\ozon-help-kb\raw\ozon_help_zh_raw.json"
with open(RAW, encoding="utf-8") as f:
    data = json.load(f)

samples = {"note": 0, "link": 0, "pictureBlock": 0, "table": 0, "geo": 0, "file": 0, "gallery": 0, "IframeBlock": 0, "heading": 0, "tabsItem": 0, "codeBlock": 0, "inlinePicture": 0}
def scan(n, path):
    t = n.get("type")
    if t in samples and samples[t] < 2:
        samples[t] += 1
        print(f"\n[{t}] path={path}")
        print(json.dumps(n, ensure_ascii=False)[:600])
    for m in n.get("marks", []):
        if m.get("type") == "link" and samples["link"] < 2:
            samples["link"] += 1
            print(f"\n[mark:link] path={path}")
            print(json.dumps(m, ensure_ascii=False)[:400])
    for c in n.get("content", []):
        scan(c, path + "/" + (t or "?"))

for d in data["docs"]:
    cj = d.get("contentJson")
    if not cj:
        continue
    try:
        scan(json.loads(cj), d["path"])
    except Exception:
        pass
    if all(v >= 2 for v in samples.values()):
        break
