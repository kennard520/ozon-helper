# -*- coding: utf-8 -*-
"""店铺2女包图自传：下载 1688 图 → 传到店铺2 Ozon media-storage → 换链接 upsert。"""
import sys, json, time, urllib.request
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
src_imgs = a.get("images") or []
print("现有图（源）:", len(src_imgs))

# 1) 下载 1688 图
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
def dl(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://detail.1688.com/"})
    return urllib.request.urlopen(req, timeout=30).read()

blobs = []
for idx, u in enumerate(src_imgs, 1):
    try:
        b = dl(u)
        blobs.append((f"bag-{idx}.jpg", b))
        print(f"  下载 {idx}: {len(b)} bytes")
    except Exception as e:
        print(f"  下载 {idx} 失败: {e!r}")
if not blobs:
    print("无图可传，停"); sys.exit()

# 2) 上传到店铺2 media-storage
sm = app.seller_media
sm.set_company_id('5020129')
print("\n店铺2 登录态:", sm.is_logged_in())
try:
    new_urls = sm.upload_many(blobs)
    print("上传后 URL:", json.dumps(new_urls, ensure_ascii=False)[:600])
except Exception as e:
    print("上传失败:", repr(e))
    print(">>> 多半是店铺2需要单独的卖家后台登录态。停。")
    sys.exit()

if not new_urls or not all(str(u).startswith("http") for u in new_urls):
    print(">>> 上传未返回有效 URL，停。"); sys.exit()

# 3) upsert：images 换成 ir.ozone.ru，型号名保持 JX-BAG-NK-BLK-L
new_attrs = []
for at in a.get("attributes", []):
    aid = at.get("id"); vals = at.get("values") or []
    if aid == 9048:
        vals = [{"dictionary_value_id": 0, "value": NEW_MODEL}]
    vals = [v for v in vals if (v.get("dictionary_value_id") or 0) > 0 or str(v.get("value") or "").strip()]
    if vals:
        new_attrs.append({"id": aid, "complex_id": at.get("complex_id", 0), "values": vals})

item = {
    "offer_id": OFF, "name": a.get("name"),
    "description_category_id": a.get("description_category_id"), "type_id": a.get("type_id"),
    "price": i.get("price"), "old_price": i.get("old_price"),
    "currency_code": i.get("currency_code") or "CNY", "vat": i.get("vat") or "0",
    "weight": a.get("weight"), "weight_unit": a.get("weight_unit", "g"),
    "depth": a.get("depth"), "width": a.get("width"), "height": a.get("height"),
    "dimension_unit": a.get("dimension_unit", "mm"),
    "images": list(new_urls), "attributes": new_attrs,
}
print("\n=== upsert（图换 ir.ozone.ru）===")
resp = publish_items(s2, [item])
task_id = (resp.get("result") or {}).get("task_id")
print("task_id:", task_id)
for n in range(10):
    time.sleep(3)
    info = get_import_info(s2, task_id)
    items = (info.get("result") or {}).get("items") or []
    snap = [{"status": it.get("status"), "errors": it.get("errors")} for it in items]
    print(f"poll {n+1}:", json.dumps(snap, ensure_ascii=False)[:400])
    if items and all(it.get("status") not in ("pending", "not_started", "") for it in items):
        break

i2 = list(get_ozon_info(s2, [OFF]).values())[0]
st = i2.get("statuses") or {}
print("\n=== 复核 ===")
print("is_created:", st.get("is_created"), "| status_name:", st.get("status_name"))
print("图现在是:", "ir.ozone.ru" if any("ozone" in str(u) for u in (i2.get('images') or [])) else "仍 1688",
      "| 图数:", len(i2.get("images") or []))
