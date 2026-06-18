# -*- coding: utf-8 -*-
"""下载共用视频→传 media-storage→换 ozone URL；并去掉所有 gw 草稿标签里的 #greenworks。"""
import sys, urllib.request, sqlite3
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.store import Store
from backend.seller_media import SellerMediaClient
from backend.app_service import AUTH_ROOT

TAOBAO = "https://cloud.video.taobao.com/play/u/3684118372/p/2/e/6/t/1/521035559073.mp4"
NEW_TAGS = "#аккумулятордляинструмента #аккумулятор #литийионный #садоваятехника #аккумуляторныйблок"

req = urllib.request.Request(TAOBAO, headers={'User-Agent': 'Mozilla/5.0'})
data = urllib.request.urlopen(req, timeout=120).read()
print('视频下载:', len(data), 'bytes')

st = Store()
cid = str(st.get_settings().get('ozon_client_id') or '')
sm = SellerMediaClient(AUTH_ROOT, cid)
urls = sm.upload_many([("video.mp4", data)])
ozurl = urls[0] if urls else ''
print('ozone 视频 URL:', ozurl)
if not ozurl:
    print('上传失败，终止'); st.close(); sys.exit(1)

con = sqlite3.connect(r'tools/ozon-listing-webui/data/products.db')
con.row_factory = sqlite3.Row
ids = [r['id'] for r in con.execute("SELECT id FROM drafts WHERE offer_id LIKE 'gw-%'").fetchall()]
con.close()
for i in ids:
    d = st.get_draft(i)
    attrs = d.get('attributes') or []
    for a in attrs:
        if a.get('id') == 23171:
            a['values'] = [{'value': NEW_TAGS}]
    st.update_draft(i, {'attributes': attrs, 'video_url': ozurl, 'price': d.get('price')})
st.close()
print('已更新', len(ids), '个草稿: 视频换 ozone + 标签去 greenworks')
