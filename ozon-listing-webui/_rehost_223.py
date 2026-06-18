# -*- coding: utf-8 -*-
"""#223: 本地图 + 视频 上传到卖家 media-storage，换 ir.ozone.ru URL 写回。"""
import sys, json, sqlite3, urllib.request
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from backend.store import Store
from backend.seller_media import SellerMediaClient
from backend import media as _media
from backend.app_service import AUTH_ROOT

con = sqlite3.connect(r'tools/ozon-listing-webui/data/products.db')
row = con.execute("SELECT local_images_json, video_url FROM drafts WHERE id=223").fetchone()
con.close()
loc = json.loads(row[0] or '[]')
video_url = row[1] or ''
print('本地图:', len(loc), '| 视频:', video_url[:60])

st = Store()
cid = str(st.get_settings().get('ozon_client_id') or '')
sm = SellerMediaClient(AUTH_ROOT, cid)

items = []
for p in loc:
    b = _media.read_media_bytes(p)
    if b is None:
        print('读不到', p); continue
    items.append((p.rsplit('/', 1)[-1], b))

if video_url:
    try:
        vb = urllib.request.urlopen(urllib.request.Request(video_url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read()
        items.append(("video.mp4", vb))
        print('视频下载:', len(vb), 'bytes')
    except Exception as e:
        print('视频下载失败(跳过):', e)

urls = sm.upload_many(items)
print('上传得到 URL:', len(urls))

n_img = len(loc)
img_urls = urls[:n_img]
vid_url = urls[n_img] if len(urls) > n_img else video_url
st.update_draft(223, {'images': img_urls, 'video_url': vid_url})
print('已写回 #223: images=%d 张 ozone, video=%s' % (len(img_urls), vid_url[:60]))
st.close()
