"""Ozon 卖家后台「搜索查询」分析 — 分页抓取（200 页 ×50 = 1万条）。

裸 requests 会被 abt-challenge 反爬挡(403，校验 TLS/JA3 指纹)，已验证两次死路。
所以请求走已登录的 CloakBrowser 页面上下文(page.evaluate 里 fetch)，指纹+cookie
全真，跟 SPA 自己发请求一样。

用法:
    .venv\\Scripts\\python.exe tools\\ozon_api\\test.py [页数]   # 默认 200
前提:先跑过 tools/ozon-scraper/scratch_seller_dashboard.py 登录，
登录态存在 .auth/ozon_profile。
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

from cloakbrowser import launch_persistent_context

REPO = pathlib.Path(__file__).resolve().parents[2]
USER_DATA = REPO / ".auth" / "ozon_profile"
OUT = pathlib.Path(__file__).resolve().parent / "data" / "search_queries_days7.jsonl"

API_URL = "https://seller.ozon.ru/api/site/searchteam/Stats/queries/search/v2"
PAGE_URL = "https://seller.ozon.ru/app/analytics/what-to-sell/all-queries"

PAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 200
LIMIT = 50
PERIOD = "days_7"
SLEEP = 0.4

_FETCH_JS = """
async (p) => {
  const r = await fetch(p.url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-o3-app-name': 'seller-ui',
      'x-o3-page-type': 'analytics_seller',
      'x-o3-language': 'zh-Hans',
      'x-o3-company-id': '4891171',
    },
    body: JSON.stringify(p.body),
    credentials: 'include',
  });
  const text = await r.text();
  return { status: r.status, text };
}
"""

_LOGIN_MARKERS = ("Вход и регистрация", "Войдите по номеру телефона")


def _logged_out(page) -> bool:
    try:
        return any(m in page.inner_text("body", timeout=5000) for m in _LOGIN_MARKERS)
    except Exception:  # noqa: BLE001
        return True


def _request_page(page, offset: int) -> dict:
    body = {
        "text": "",
        "limit": str(LIMIT),
        "offset": str(offset),
        "sort_by": "count",
        "sort_dir": "desc",
        "period": PERIOD,
    }
    res = page.evaluate(_FETCH_JS, {"url": API_URL, "body": body})
    if res["status"] != 200:
        raise RuntimeError(f"HTTP {res['status']}: {res['text'][:200]}")
    return json.loads(res["text"])


def _extract_rows(payload: dict) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    return []


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ctx = launch_persistent_context(
        str(USER_DATA), headless=False, locale="ru-RU", timezone="Europe/Moscow"
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(3)
    if _logged_out(page):
        print("[!] 未登录，请先跑 scratch_seller_dashboard.py 登录。", flush=True)
        ctx.close()
        return 1
    print(f"[+] 已登录，开始抓 {PAGES} 页 ×{LIMIT}…", flush=True)

    seen: set[str] = set()
    total = 0
    with OUT.open("w", encoding="utf-8") as f:
        for i in range(PAGES):
            offset = i * LIMIT
            try:
                payload = _request_page(page, offset)
            except Exception as exc:  # noqa: BLE001
                print(f"[!] 第{i}页(offset={offset})失败: {exc}", flush=True)
                break
            rows = _extract_rows(payload)
            if not rows:
                print(f"[=] 第{i}页空，停止。", flush=True)
                break
            for r in rows:
                key = r.get("query") or json.dumps(r, ensure_ascii=False, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1
            if i % 10 == 0:
                print(f"[..] 第{i}页 offset={offset} 累计 {total} 行", flush=True)
            time.sleep(SLEEP)

    print(f"[+] 完成，共 {total} 行 -> {OUT}", flush=True)
    ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
