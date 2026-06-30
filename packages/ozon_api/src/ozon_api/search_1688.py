"""对当季绿区 top 选品，逐个搜 alibaba(锁 zh-CN 显示 CN¥)拿进价区间。

匿名免登录。通用品关键词搜够用（品牌品才需图搜）。
输出每个词的 CN¥ min/中位/max + 候选数 + 供应商多样性。
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ozon-scraper"))
from ozon_scraper.alibaba import fetch_search_html, parse_alibaba_html  # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "1688_cost_probe.json"

# 俄语选品 → 中文搜索词（当季绿区 top）
PICKS = [
    ("门用防蚊磁性纱门", "москитная сетка на дверь", "夏季"),
    ("卷帘窗帘", "рулонные шторы", "四季"),
    ("数字油画diy", "картина по номерам", "四季"),
    ("遮阳网", "сетка затеняющая", "夏季"),
    ("爬藤网黄瓜支架网", "сетка для огурцов", "夏季"),
    ("门垫地垫", "коврик придверный", "四季"),
    ("驱蚊手环", "браслет от комаров", "夏季"),
    ("浴室置物架", "полка для ванной", "四季"),
]


def _prices(offers) -> list[float]:
    vals = []
    for o in offers:
        for p in (o.price_cny_min, o.price_cny_max):
            if isinstance(p, (int, float)) and p > 0:
                vals.append(p)
    return vals


def main() -> None:
    results = []
    for zh, ru, win in PICKS:
        print(f"\n=== [{win}] {zh}  (← {ru}) ===", flush=True)
        try:
            html = fetch_search_html(zh, headless=True, timeout_ms=35_000)
            offers = parse_alibaba_html(html, limit=30)
        except Exception as exc:  # noqa: BLE001
            print(f"  搜索失败: {exc}", flush=True)
            results.append({"zh": zh, "ru": ru, "window": win, "error": str(exc)})
            time.sleep(2)
            continue
        prices = _prices(offers)
        suppliers = {o.supplier for o in offers if o.supplier}
        rec = {
            "zh": zh, "ru": ru, "window": win,
            "n_offers": len(offers),
            "n_suppliers": len(suppliers),
            "cny_min": min(prices) if prices else None,
            "cny_median": round(st.median(prices), 1) if prices else None,
            "cny_max": max(prices) if prices else None,
        }
        results.append(rec)
        print(f"  候选 {rec['n_offers']} · 供应商 {rec['n_suppliers']} · "
              f"CN¥ {rec['cny_min']}~{rec['cny_median']}~{rec['cny_max']}", flush=True)
        # 列前 3 个看看
        for o in offers[:3]:
            print(f"    - ¥{o.price_cny_min}~{o.price_cny_max} | MOQ {o.min_order} | {(o.title or '')[:40]}", flush=True)
        time.sleep(2)

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] 已存 -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
