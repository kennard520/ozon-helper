"""查某个词的所有变体搜索词 + 需求（颜色/尺寸/遮阳率），走登录态浏览器 fetch。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ozon-scraper"))
from cloakbrowser import launch_persistent_context  # noqa: E402

UD = str(Path(__file__).resolve().parents[2] / ".auth" / "ozon_profile")
API = "https://seller.ozon.ru/api/site/searchteam/Stats/queries/search/v2"
PAGE = "https://seller.ozon.ru/app/analytics/what-to-sell/all-queries"
TERMS = sys.argv[1:] or ["затеня", "сетка от солнца", "теневая сетка"]

JS = """
async (p) => {
  const r = await fetch(p.url, {method:'POST',
    headers:{'content-type':'application/json','x-o3-app-name':'seller-ui',
             'x-o3-page-type':'analytics_seller','x-o3-language':'zh-Hans','x-o3-company-id':'4891171'},
    body: JSON.stringify(p.body), credentials:'include'});
  return {status:r.status, text: await r.text()};
}
"""


def main():
    ctx = launch_persistent_context(UD, headless=False, locale="ru-RU", timezone="Europe/Moscow")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(PAGE, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(3)
    rows = {}
    for term in TERMS:
        body = {"text": term, "limit": "50", "offset": "0",
                "sort_by": "count", "sort_dir": "desc", "period": "days_7"}
        res = page.evaluate(JS, {"url": API, "body": body})
        if res["status"] != 200:
            print(f"[{term}] HTTP {res['status']}", flush=True)
            continue
        data = json.loads(res["text"]).get("data", [])
        for d in data:
            rows[d["query"]] = d
        print(f"[{term}] {len(data)} 条", flush=True)
        time.sleep(0.5)
    ctx.close()

    allrows = sorted(rows.values(), key=lambda r: r.get("count", 0), reverse=True)
    Path(__file__).resolve().parent.joinpath("data", "shadenet_variants.json").write_text(
        json.dumps(allrows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n合计 {len(allrows)} 个变体词，按搜索量：")
    print(f"{'搜索量':>7}{'卖家':>5}{'缺口%':>6}{'均价₽':>7}  搜索词")
    for r in allrows[:40]:
        print(f"{r.get('count',0):>7}{r.get('uniqSellers',0):>5}{round(r.get('zrShare',0)or 0,1):>6}{round(r.get('avgCaRub',0)or 0):>7}  {r.get('query','')}")


if __name__ == "__main__":
    main()
