# -*- coding: utf-8 -*-
"""试抓京东商品页（CloakBrowser），看反爬放不放行 + 能拿到啥。"""
import sys, re, time
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.path.insert(0, 'tools/ozon-listing-webui/backend')
sys.stdout.reconfigure(encoding='utf-8')
from cloakbrowser import launch_persistent_context
from pathlib import Path

URL = sys.argv[1] if len(sys.argv) > 1 else "https://item.jd.com/100198764205.html"
PROF = Path('.auth/jd_profile'); PROF.mkdir(parents=True, exist_ok=True)
ctx = launch_persistent_context(str(PROF), headless=False, locale="zh-CN", timezone="Asia/Shanghai")
try:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(3)
    try:
        page.mouse.wheel(0, 2500); time.sleep(2)
    except Exception:
        pass
    html = page.content()
finally:
    try:
        ctx.close()
    except Exception:
        pass

Path('tools/ozon-listing-webui/_jd_page.html').write_text(html, encoding='utf-8')
print('HTML 长度:', len(html))
m = re.search(r'<title>(.*?)</title>', html)
print('title:', m.group(1)[:70] if m else '?')
imgs = set(re.findall(r'360buyimg\.com/[A-Za-z0-9/_-]+\.(?:jpg|png|webp)', html))
print('360buyimg 图:', len(imgs))
for u in list(imgs)[:6]:
    print('  https://img10.' + u)
blocked = any(x in html for x in ['请输入验证码', 'passport.jd.com/new/login', '验证一下', 'verify'])
print('反爬拦截迹象:', blocked)
# 价格(京东价格走 API，页面里常无)
print('页面含价格数字迹象:', bool(re.search(r'(?:price|jdPrice|"p":)', html)))
