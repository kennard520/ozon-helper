# -*- coding: utf-8 -*-
"""拉店铺2女包(offer_id=女包)完整数据：上架状态/SPU错误/属性/描述。"""
import sys, json
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.app_service import App
from backend.ozon_client_adapter import get_ozon_info, get_ozon_attributes, get_ozon_descriptions

app = App()
s2 = app._settings_for_store('5020129')
off = "女包"

info = get_ozon_info(s2, [off])
item = list(info.values())[0]
print('=== INFO keys ===', list(item.keys()))
print('=== errors（全文）===', json.dumps(item.get('errors'), ensure_ascii=False))
for k in ('statuses', 'status', 'visible', 'state', 'is_archived', 'stocks',
          'price', 'old_price', 'currency_code', 'volume_weight', 'primary_image'):
    if k in item:
        print(f'  {k}:', json.dumps(item.get(k), ensure_ascii=False)[:240])

print('\n=== ATTRIBUTES ===')
try:
    a = get_ozon_attributes(s2, [off])
    print('type:', type(a).__name__, json.dumps(a, ensure_ascii=False)[:1800])
except Exception as e:
    print('attr ERR:', repr(e))

print('\n=== DESCRIPTION ===')
try:
    d = get_ozon_descriptions(s2, [off])
    print(json.dumps(d, ensure_ascii=False)[:900])
except Exception as e:
    print('desc ERR:', repr(e))
