# -*- coding: utf-8 -*-
"""救活店铺2女包：改型号名(9048)解 SPU 冲突，重新 import 到店铺2，轮询结果。"""
import sys, json, time
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.app_service import App
from backend.ozon_client_adapter import get_ozon_info, get_ozon_attributes, publish_items, get_import_info

app = App()
s2 = app._settings_for_store('5020129')
OFF = "女包"
NEW_MODEL = "JX-BAG-NK-BLK-L"

a = list(get_ozon_attributes(s2, [OFF]).values())[0]
i = list(get_ozon_info(s2, [OFF]).values())[0]

# 复用现有属性，改 9048 型号名，过滤纯空属性
new_attrs = []
for at in a.get("attributes", []):
    aid = at.get("id")
    vals = at.get("values") or []
    if aid == 9048:
        vals = [{"dictionary_value_id": 0, "value": NEW_MODEL}]
    vals = [v for v in vals if (v.get("dictionary_value_id") or 0) > 0 or str(v.get("value") or "").strip()]
    if vals:
        new_attrs.append({"id": aid, "complex_id": at.get("complex_id", 0), "values": vals})

item = {
    "offer_id": OFF,
    "name": a.get("name"),
    "description_category_id": a.get("description_category_id"),
    "type_id": a.get("type_id"),
    "price": i.get("price"),
    "old_price": i.get("old_price"),
    "currency_code": i.get("currency_code") or "CNY",
    "vat": i.get("vat") or "0",
    "weight": a.get("weight"),
    "weight_unit": a.get("weight_unit", "g"),
    "depth": a.get("depth"), "width": a.get("width"), "height": a.get("height"),
    "dimension_unit": a.get("dimension_unit", "mm"),
    "images": a.get("images") or [],
    "attributes": new_attrs,
}

print("=== 构造的 import item（关键字段）===")
print("offer_id:", item["offer_id"])
print("9048 型号名 →", [x["values"] for x in item["attributes"] if x["id"] == 9048])
print("属性数:", len(item["attributes"]), "| 价:", item["price"], item["currency_code"],
      "| 划线:", item["old_price"], "| 图:", len(item["images"]),
      "| 尺寸mm:", item["depth"], item["width"], item["height"], "| 重g:", item["weight"])

print("\n=== 提交 import 到店铺2 ===")
resp = publish_items(s2, [item])
print("response:", json.dumps(resp, ensure_ascii=False)[:300])
task_id = (resp.get("result") or {}).get("task_id")
if not task_id:
    print("无 task_id，停"); sys.exit()

for n in range(10):
    time.sleep(3)
    info = get_import_info(s2, task_id)
    items = (info.get("result") or {}).get("items") or []
    snap = [{"offer_id": it.get("offer_id"), "status": it.get("status"),
             "errors": it.get("errors")} for it in items]
    print(f"poll {n+1}:", json.dumps(snap, ensure_ascii=False)[:500])
    if items and all(it.get("status") not in ("pending", "not_started", "") for it in items):
        break

# 复核：商品是否建成
time.sleep(2)
i2 = list(get_ozon_info(s2, [OFF]).values())[0]
st = i2.get("statuses") or {}
print("\n=== 复核状态 ===")
print("is_created:", st.get("is_created"), "| status_name:", st.get("status_name"),
      "| errors:", json.dumps(i2.get("errors"), ensure_ascii=False)[:200])
