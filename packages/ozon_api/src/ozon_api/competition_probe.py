"""用登录态浏览器拉 Ozon 公开搜索结果，读真实竞争：
价格带 + 评论数分布（评论越高=老玩家壁垒越硬，新人越难挤）。
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ozon-scraper"))
from cloakbrowser import launch_persistent_context  # noqa: E402
from ozon_scraper.search import parse_search_html, summarize_for_scout  # noqa: E402

UD = str(Path(__file__).resolve().parents[2] / ".auth" / "ozon_profile")
OUT = Path(__file__).resolve().parent / "data" / "competition_probe.json"

PICKS = [
    ("数字油画", "картина по номерам"),
    ("遮阳网", "сетка затеняющая"),
    ("浴室置物架", "полка для ванной"),
    ("卷帘", "рулонные шторы"),
    ("门用防蚊纱门", "москитная сетка на дверь"),
    ("爬藤网", "сетка для огурцов"),
]


def _scroll(page, n=5):
    for _ in range(n):
        page.mouse.wheel(0, 4000)
        time.sleep(1.2)


def main():
    ctx = launch_persistent_context(UD, headless=False, locale="ru-RU", timezone="Europe/Moscow")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    out = []
    for zh, ru in PICKS:
        url = "https://www.ozon.ru/search/?text=" + ru.replace(" ", "+") + "&from_global=true"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            time.sleep(4)
            _scroll(page)
            results = parse_search_html(page.content())
        except Exception as exc:  # noqa: BLE001
            print(f"{zh}: ERR {exc}", flush=True)
            continue
        s = summarize_for_scout(results, keyword=ru)
        p = s["price"]
        rv = s["review_count"]
        rec = {"zh": zh, "ru": ru, "summary": s}
        out.append(rec)
        print(f"\n=== {zh} ({ru}) ===", flush=True)
        print(f"  解析 {s['sample_size']} 个 · 价 ₽{p.get('min')}~{p.get("median")}~{p.get('max')}", flush=True)
        print(f"  评论 中位{rv.get("median")} 最高{rv.get('max')} · ≥1000评的SKU:{s['review_count_gte_1000']}个", flush=True)
        for t in s["top_3_by_reviews"]:
            print(f"    头部: {t['review_count']}评 ₽{t['price_rub']} | {(t['title'] or '')[:40]}", flush=True)
        time.sleep(2)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] 存 -> {OUT}", flush=True)
    ctx.close()


if __name__ == "__main__":
    main()
