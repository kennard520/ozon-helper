# -*- coding: utf-8 -*-
"""枚举 1688 店铺 offerlist 的所有商品 offerId（登录态 CloakBrowser）。"""
import sys, re, time, json
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.path.insert(0, 'tools/ozon-listing-webui/backend')
sys.stdout.reconfigure(encoding='utf-8')
from cloakbrowser import launch_persistent_context
from pathlib import Path

SHOP = "https://joinsun.1688.com/page/offerlist.htm"
PROF = Path('.auth/1688_profile')  # 复用已登录的 1688 账号态
ctx = launch_persistent_context(str(PROF), headless=False, locale="zh-CN", timezone="Asia/Shanghai")
offer_ids = set()
try:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for pg in range(1, 11):  # 最多翻 10 页
        url = f"{SHOP}?pageNum={pg}"
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(2.5)
        try:
            page.mouse.wheel(0, 4000); time.sleep(1.5)
            page.mouse.wheel(0, 4000); time.sleep(1.5)
        except Exception:
            pass
        html = page.content()
        ids = set(re.findall(r'(?:detail\.1688\.com/offer/|offerId[=:"\s]*)(\d{10,16})', html))
        new = ids - offer_ids
        offer_ids |= ids
        title = (page.title() or '')[:30]
        print(f'第{pg}页: 新增 {len(new)} 个 (累计 {len(offer_ids)}) | 标题 {title}')
        if 'login' in (page.url or '').lower() or '登录' in title:
            print('  撞登录墙，停止'); break
        if not new and pg > 1:
            print('  无新商品，到底了'); break
finally:
    try:
        ctx.close()
    except Exception:
        pass
Path('tools/ozon-listing-webui/_shop_offers.json').write_text(
    json.dumps(sorted(offer_ids), ensure_ascii=False), encoding='utf-8')
print('总商品数:', len(offer_ids))
print('样例 URL:')
for i in sorted(offer_ids)[:5]:
    print('  https://detail.1688.com/offer/%s.html' % i)
