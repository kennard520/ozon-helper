# -*- coding: utf-8 -*-
"""稳健版：全程累加店铺 offerlist 接口响应，翻页多法触发，最后统一提取全部 offerId。"""
import sys, re, time, json
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.stdout.reconfigure(encoding='utf-8')
from cloakbrowser import launch_persistent_context
from pathlib import Path

URL = "https://joinsun.1688.com/page/offerlist.htm"
PROF = Path('.auth/1688_profile')
bodies = []

def on_resp(resp):
    try:
        if 'moduleasyncservice' in resp.url:
            bodies.append(resp.text())
    except Exception:
        pass

def ids_now():
    out = set()
    for t in bodies:
        for m in re.findall(r'"id"\s*:\s*"?(\d{11,13})"?', t):
            if not m.startswith('17'):
                out.add(m)
    return out

ctx = launch_persistent_context(str(PROF), headless=False, locale="zh-CN", timezone="Asia/Shanghai")
try:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.on("response", on_resp)
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(4)
    last = -1
    for rnd in range(15):
        for _ in range(3):
            page.mouse.wheel(0, 5000); time.sleep(0.8)
        # 试点分页：数字页码 / 下一页 / fui-next
        for sel in ['.fui-next:not(.fui-next-disabled)', 'a:has-text("下一页")',
                    '.next-pagination-item.next', 'button[aria-label*="next" i]']:
            try:
                el = page.query_selector(sel)
                if el:
                    el.scroll_into_view_if_needed(timeout=2000)
                    el.click(timeout=2000); time.sleep(3); break
            except Exception:
                continue
        n = len(ids_now())
        print(f'轮 {rnd+1}: 累计 offerId {n}')
        if n >= 80 or (n == last and rnd > 3):
            break
        last = n
finally:
    try:
        ctx.close()
    except Exception:
        pass

allid = sorted(ids_now())
Path('tools/ozon-listing-webui/_shop_offers.json').write_text(json.dumps(allid, ensure_ascii=False), encoding='utf-8')
print('=== 最终 offer ID:', len(allid), '/ 店铺 80 ===')
