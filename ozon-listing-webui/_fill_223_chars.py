# -*- coding: utf-8 -*-
"""从存的吸尘器页面抽全部特征，写进 #223(采集格式)，清理描述品牌词。"""
import sys, re, json
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.path.insert(0, 'tools/ozon-listing-webui/backend')
sys.stdout.reconfigure(encoding='utf-8')
from backend import collector as C
from backend.store import Store

h = open(r'tools/ozon-listing-webui/_ozon_page.html', encoding='utf-8', errors='ignore').read()
states = json.load(open(r'tools/ozon-listing-webui/_ozon_states.json', encoding='utf-8'))
p = C.parse_product_html(h)
chars = C._chars_from_states(states) or C._all_chars(p)
# 过滤竞品专属 + 品牌相关
SKIP = {'Артикул', 'Бренд'}
new_chars = []
for c in chars:
    nm = (c.get('name') or '').strip()
    val = str(c.get('value') or '').strip()
    if nm in SKIP or not nm or not val:
        continue
    # 去品牌词
    val = re.sub(r'\b(Xiaomi|Mijia|Сяоми|Ксиоми)\b', '', val, flags=re.I).strip(' ,')
    new_chars.append({'name': nm, 'value': val})

st = Store()
d = st.get_draft(223)
# 保留现有 {id,values}，把采集 {name,value} 合进去（去重按 name）
existing = d.get('attributes') or []
keep_idval = [a for a in existing if isinstance(a, dict) and 'id' in a and 'values' in a]
merged = keep_idval + new_chars

# 清理描述里的品牌词
desc = d.get('description') or ''
desc = re.sub(r'\b(Xiaomi|Mijia)\b', '', desc, flags=re.I)
desc = re.sub(r'\s{2,}', ' ', desc).strip()

st.update_draft(223, {'attributes': merged, 'description': desc, 'price': d.get('price')})
print('写入采集特征:', len(new_chars), '条')
for c in new_chars:
    print('  ', c['name'], '=', c['value'][:40])
print('描述长度:', len(desc), '| 含品牌:', bool(re.search(r'Xiaomi|Mijia', desc, re.I)))
st.close()
