# -*- coding: utf-8 -*-
"""电池 20 变体：①#224 本地图传 media-storage→ozone，套到全部；②标题/描述/型号去 Greenworks（兼容品牌属性保留）。"""
import sys, json, re, sqlite3
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.store import Store
from backend.seller_media import SellerMediaClient
from backend import media as _media
from backend.app_service import AUTH_ROOT

con = sqlite3.connect(r'tools/ozon-listing-webui/data/products.db')
con.row_factory = sqlite3.Row
loc = json.loads(con.execute("SELECT local_images_json FROM drafts WHERE id=224").fetchone()[0] or '[]')
ids = [r['id'] for r in con.execute("SELECT id FROM drafts WHERE offer_id LIKE 'gw-%' ORDER BY id").fetchall()]
con.close()

st = Store()
cid = str(st.get_settings().get('ozon_client_id') or '')
sm = SellerMediaClient(AUTH_ROOT, cid)

# 1. 上传 25 张本地图一次
items = []
for p in loc:
    b = _media.read_media_bytes(p)
    if b is not None:
        items.append((p.rsplit('/', 1)[-1], b))
img_urls = sm.upload_many(items)
print('图片上传:', len(img_urls), '张 → ozone')
if len(img_urls) < len(items):
    print('警告: 部分图未上传成功');

def strip_gw_title(t):
    t = re.sub(r',\s*совместим с Greenworks', '', t)
    return t.strip()

def strip_gw_desc(d):
    d = re.sub(r'\s*Совместим с (?:платформой )?Greenworks \d+V\.', '', d)
    d = re.sub(r'• Совместимость: Greenworks \d+V', '• Назначение: садовая техника и электроинструмент', d)
    d = re.sub(r'совместим с Greenworks \d+V', 'для садовой техники', d)
    return d

# 2. 逐草稿：套图 + 去品牌
for i in ids:
    d = st.get_draft(i)
    new_title = strip_gw_title(d.get('ozon_title') or '')
    new_desc = strip_gw_desc(d.get('description') or '')
    attrs = d.get('attributes') or []
    for a in attrs:
        if a.get('id') == 4180:   # Название
            a['values'] = [{'value': new_title}]
        elif a.get('id') == 9048:  # 型号名（去 Greenworks，保留构造区分）
            v = a['values'][0].get('value', '')
            a['values'] = [{'value': v.replace('Greenworks ', 'Аккумулятор ')}]
        elif a.get('id') == 4191:  # 简介
            v = a['values'][0].get('value', '')
            a['values'] = [{'value': re.sub(r',?\s*совместим с Greenworks \d+V', '', v).strip()}]
        # 22903 Совместимый бренд=Greenworks 保留不动
    st.update_draft(i, {'images': img_urls, 'ozon_title': new_title, 'description': new_desc,
                        'attributes': attrs, 'price': d.get('price')})
st.close()
print('已处理', len(ids), '个: 套 ozone 图 + 去 Greenworks（兼容品牌属性保留）')
