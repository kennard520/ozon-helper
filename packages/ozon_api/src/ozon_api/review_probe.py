"""进商品详情页拉真实评论数，判断头部壁垒（老玩家是否锁死首屏）。

登录态浏览器（.auth/ozon_profile）能过反爬。
每个选品取搜索页前 N 个商品 → 逐个进详情页 → 评论数/评分/价格。
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ozon-scraper"))
from cloakbrowser import launch_persistent_context  # noqa: E402
from ozon_scraper.parser import parse_product_html  # noqa: E402
from ozon_scraper.search import parse_search_html  # noqa: E402

UD = str(Path(__file__).resolve().parents[2] / ".auth" / "ozon_profile")
OUT = Path(__file__).resolve().parent / "data" / "review_probe.json"
TOPN = 12

PICKS = [
    ("相框", "рамка для фото"),
    ("收纳篮", "корзина для хранения"),
    ("花器", "кашпо"),
]


def main():
    ctx = launch_persistent_context(UD, headless=False, locale="ru-RU", timezone="Europe/Moscow")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    out = []
    for zh, ru in PICKS:
        print(f"\n=== {zh} ({ru}) ===", flush=True)
        url = "https://www.ozon.ru/search/?text=" + ru.replace(" ", "+") + "&from_global=true"
        urls = []
        for attempt in range(2):
            page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            try:
                page.wait_for_selector("div.tile-root", timeout=15_000, state="attached")
            except Exception:  # noqa: BLE001
                pass
            time.sleep(4)
            for _ in range(3):
                page.mouse.wheel(0, 4000)
                time.sleep(1)
            results = parse_search_html(page.content())
            urls = [r.url for r in results if r.url][:TOPN]
            if urls:
                break
            print(f"  第{attempt+1}次搜索 0 url，重试…", flush=True)
        print(f"  取前 {len(urls)} 个商品页…", flush=True)

        prods = []
        for i, u in enumerate(urls):
            full = u if u.startswith("http") else "https://www.ozon.ru" + u
            try:
                page.goto(full, wait_until="domcontentloaded", timeout=40_000)
                page.wait_for_selector('script[type="application/ld+json"]', timeout=15_000, state="attached")
                time.sleep(1.5)
                p = parse_product_html(page.content())
                prods.append({"title": (p.name or "")[:40], "review_count": p.review_count,
                              "rating": p.rating, "price": p.price})
            except Exception as exc:  # noqa: BLE001
                print(f"    [{i}] 失败 {type(exc).__name__}", flush=True)
            time.sleep(1)

        revs = [x["review_count"] for x in prods if isinstance(x["review_count"], int)]
        rec = {
            "zh": zh, "ru": ru, "n_visited": len(prods),
            "rev_median": round(st.median(revs)) if revs else None,
            "rev_max": max(revs) if revs else None,
            "n_ge_500": sum(1 for x in revs if x >= 500),
            "n_ge_1000": sum(1 for x in revs if x >= 1000),
            "n_ge_5000": sum(1 for x in revs if x >= 5000),
            "products": sorted(prods, key=lambda x: x["review_count"] or 0, reverse=True),
        }
        out.append(rec)
        print(f"  评论 中位{rec['rev_median']} 最高{rec['rev_max']} · ≥500:{rec['n_ge_500']} ≥1000:{rec['n_ge_1000']} ≥5000:{rec['n_ge_5000']}（共{len(revs)}个有数）", flush=True)
        for x in rec["products"][:5]:
            print(f"    {x['review_count']}评 ⭐{x['rating']} ₽{x['price']} | {x['title']}", flush=True)
        time.sleep(2)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] 存 -> {OUT}", flush=True)
    ctx.close()


if __name__ == "__main__":
    main()
