# -*- coding: utf-8 -*-
"""确认 9048 型号名改生效没 + barcode，定位 SPU 判重依据。"""
import sys, json
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.app_service import App
from backend.ozon_client_adapter import get_ozon_attributes

app = App()
s2 = app._settings_for_store('5020129')
a = list(get_ozon_attributes(s2, ["女包"]).values())[0]
print("9048 型号名现值:", [x['values'] for x in a.get('attributes', []) if x['id'] == 9048])
print("barcode:", repr(a.get('barcode')))
print("全属性 id:", [x['id'] for x in a.get('attributes', [])])
# 看每个属性的值，找可能含 869171795561 或唯一标识的
for x in a.get('attributes', []):
    vs = x.get('values') or []
    flat = " | ".join(str(v.get('value') or v.get('dictionary_value_id') or '') for v in vs)
    if flat.strip():
        print(f"  attr {x['id']}: {flat[:80]}")
