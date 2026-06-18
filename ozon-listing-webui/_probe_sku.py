# -*- coding: utf-8 -*-
"""勘察 1 个 1688 电池商品页：① 风控放不放行 ② 有没有内部多规格(skuInfoMap) ③ 字段质量。"""
import sys, json, time
sys.path.insert(0, 'tools/ozon-listing-webui')
sys.path.insert(0, 'tools/ozon-listing-webui/backend')
sys.path.insert(0, 'tools/ozon-scraper')
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from cloakbrowser import launch_persistent_context
import collector_1688 as c

URL = sys.argv[1] if len(sys.argv) > 1 else "https://detail.1688.com/offer/1031952110859.html"
PROF = Path('.auth/1688_profile')
ctx = launch_persistent_context(str(PROF), headless=False, locale="zh-CN", timezone="Asia/Shanghai")
try:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_function(
            "() => document.documentElement.innerHTML.includes('offerTitle')"
            " || document.documentElement.innerHTML.includes('offerImgList')",
            timeout=15000)
    except Exception:
        pass
    time.sleep(1.5)
    html = page.content()
finally:
    ctx.close()

Path('tools/ozon-listing-webui/_probe_page.html').write_text(html, encoding='utf-8')
low = html.lower()
blocked = any(x in low for x in ("nc_iconfont", "x5sec-token", "punish", "captcha", "滑动验证"))
print("=== 风控 ===")
print("HTML 长度:", len(html), "| 反爬迹象:", blocked)

print("\n=== 基础字段 ===")
title = c._grab_str(html, "offerTitle") or c._grab_str(html, "subject")
print("标题:", title[:60])
print("图片数:", len(c._images(html)))
print("成本(最低档):", c._cost_cny(html))
print("阶梯价:", c._price_tiers(html))
print("件重(g):", c._weight_g_from_unit(html))

print("\n=== 内部规格 skuModel ===")
sku = c._grab_json(html, "skuModel")
if not isinstance(sku, dict):
    print("无 skuModel(可能是单规格商品)")
else:
    props = sku.get("skuProps") or []
    print("skuProps(规格维度):")
    for p in props:
        if isinstance(p, dict):
            vals = [v.get("name") for v in (p.get("value") or []) if isinstance(v, dict)]
            print(f"  - {p.get('prop')}: {vals}")
    info = sku.get("skuInfoMap")
    if isinstance(info, dict):
        print(f"\nskuInfoMap 规格组合数: {len(info)}")
        for i, (k, v) in enumerate(info.items()):
            if i >= 8:
                print("  ...")
                break
            price = v.get("price") if isinstance(v, dict) else None
            print(f"  [{k}] price={price}  raw={json.dumps(v, ensure_ascii=False)[:120]}")
    else:
        print("无 skuInfoMap")
print("\n=== 属性表 normalCpv ===")
for a in c._attributes(html)[:12]:
    print(f"  {a['name']}: {a['value']}")
