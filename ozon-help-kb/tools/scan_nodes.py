# -*- coding: utf-8 -*-
"""扫描 Ozon 帮助中心 contentJson 的全部节点/标记类型，用于编写完整转换器。"""
import json
import collections

RAW = r"E:\code\zqr\ozon-helper\ozon-help-kb\raw\ozon_help_zh_raw.json"

with open(RAW, encoding="utf-8") as f:
    data = json.load(f)

docs = data["docs"]
print("docs:", len(docs))

node_types = collections.Counter()
mark_types = collections.Counter()
attr_samples = collections.defaultdict(set)

def scan(n):
    t = n.get("type")
    if t:
        node_types[t] += 1
        for k, v in n.items():
            if k in ("type", "content", "marks", "text", "attrs"):
                continue
            attr_samples[t].add(str(k))
    for m in n.get("marks", []):
        mark_types[m.get("type")] += 1
    for c in n.get("content", []):
        scan(c)
    # attrs 里的键（如 language）
    a = n.get("attrs")
    if isinstance(a, dict):
        for k in a.keys():
            attr_samples["attr:" + (n.get("type") or "?")].add(k)

for d in docs:
    cj = d.get("contentJson")
    if not cj:
        print("NO_CJ:", d["path"])
        continue
    try:
        scan(json.loads(cj))
    except Exception as e:
        print("PARSE_ERR", d["path"], e)

print("\n== NODE TYPES ==")
for k, v in node_types.most_common():
    print(f"{k}: {v}  attrs_keys={sorted(attr_samples.get(k, []))}")

print("\n== MARK TYPES ==")
for k, v in mark_types.most_common():
    print(f"{k}: {v}")

print("\n== ATTR KEYS ==")
for k in sorted(attr_samples):
    if k.startswith("attr:"):
        print(f"{k}: {sorted(attr_samples[k])}")
