# -*- coding: utf-8 -*-
"""匿名多排序枚举 1688 店铺 offerId（不登录，靠不同排序的 top-N 取并集）。"""
import sys, re, time, json
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.path.insert(0, 'tools/ozon-listing-webui/backend')
sys.stdout.reconfigure(encoding='utf-8')
from cloakbrowser import launch_persistent_context
from pathlib import Path

SHOP = "https://joinsun.1688.com/page/offerlist.htm"
SORTS = ["", "&sortType=booked", "&sortType=price", "&sortType=priceUp",
         "&sortType=time", "&sortType=wangpu_score", "&sortType=oldStock"]
OFFER_RE = re.compile(r'detail\.1688\.com\\?/offer\\?/(\d{10,16})|offerId["=:\\\s]*(\d{10,16})')
PROF = Path('.auth/1688_profile')
OUT = Path('tools/ozon-listing-webui/_shop_offers.json')

# 已有的 30 个并进来
prev = set()
if OUT.exists():
    try:
        prev = set(json.loads(OUT.read_text(encoding='utf-8')))
    except Exception:
        pass


def offers_in(html):
    ids = set()
    for a, b in OFFER_RE.findall(html):
        ids.add(a or b)
    ids.discard('')
    return ids


ctx = launch_persistent_context(str(PROF), headless=False, locale="zh-CN", timezone="Asia/Shanghai")
all_ids = set(prev)
print("起始(已有):", len(all_ids), flush=True)
try:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for s in SORTS:
        for pg in (1, 2, 3):
            try:
                page.goto(f"{SHOP}?pageNum={pg}{s}", wait_until="domcontentloaded", timeout=40000)
            except Exception:
                continue
            time.sleep(1.8)
            try:
                for _ in range(3):
                    page.mouse.wheel(0, 5000); time.sleep(0.8)
            except Exception:
                pass
            all_ids |= offers_in(page.content())
        print(f"排序 {s or '默认'}: 累计 {len(all_ids)}", flush=True)
finally:
    try:
        ctx.close()
    except Exception:
        pass

OUT.write_text(json.dumps(sorted(all_ids), ensure_ascii=False), encoding='utf-8')
print("=== 并集总数:", len(all_ids), "===", flush=True)
