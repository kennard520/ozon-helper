"""按 SKU 拉取「买家通过什么搜索词进来的」（Ozon 商品搜索查询分析）。

数据源：/v1/analytics/product-queries/details（对应后台 搜索中的商品→我的商品的查询）。
口径（swagger 2026-05-30）：
  query                搜索词文本
  unique_search_users  搜该词的独立用户数（搜索量）
  unique_view_users    搜该词后看到本商品的独立用户数（曝光人数，Premium 指标）
  view_conversion      看到→点进的转化率
  position             该词下商品平均搜索排位（越小越靠前）
  order_count          该词带来的下单数
  gmv                  该词带来的成交额

注意：搜索词数据 **不含当天**，需 1–2 天算完；近一个月可按任意区间查，更早只能按周（需 Premium+）。
本脚本默认查「近 N 天到昨天」（默认 7 天）。

用法：
  python tools/ozon-listing-webui/scripts/sku_keywords_report.py [天数=7] [结束日期=昨天]
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from ozon_api import OzonSellerClient, OzonApiError  # noqa: E402

DB = ROOT / "data" / "products.db"


def load_creds() -> tuple[str, str]:
    con = sqlite3.connect(DB)
    kv = {k: json.loads(v) if v and v[0] in '"[{' else v
          for k, v in con.execute("select key,value from settings")}
    con.close()
    return str(kv["ozon_client_id"]), str(kv["ozon_api_key"])


def all_store_skus(client: OzonSellerClient) -> dict[str, dict]:
    """返回 {sku: {offer_id, name}}，覆盖全店在售商品。"""
    offer_ids, last_id = [], ""
    while True:
        r = client.list_products(visibility="ALL", last_id=last_id, limit=1000)
        res = r.get("result") or {}
        batch = res.get("items") or []
        offer_ids += [str(it.get("offer_id")) for it in batch if it.get("offer_id")]
        last_id = res.get("last_id") or ""
        if len(batch) < 1000 or not last_id:
            break
    out: dict[str, dict] = {}
    for i in range(0, len(offer_ids), 1000):
        r = client.get_products_info(offer_ids=offer_ids[i:i + 1000])
        for it in (r.get("items") or []):
            sku = str(it.get("sku") or "")
            if sku and sku != "0":
                out[sku] = {"offer_id": str(it.get("offer_id") or ""), "name": it.get("name") or ""}
    return out


def fetch_queries(client: OzonSellerClient, skus: list[str], d_from: str, d_to: str) -> list[dict]:
    queries: list[dict] = []
    page = 0
    while True:
        body = {
            "date_from": f"{d_from}T00:00:00Z",
            "date_to": f"{d_to}T23:59:59Z",
            "skus": skus,
            "page": page,
            "page_size": 100,
            "limit_by_sku": 15,
            "sort_by": "BY_SEARCHES",
            "sort_dir": "DESC",
        }
        for attempt in range(6):
            try:
                r = client.request("/v1/analytics/product-queries/details", body)
                break
            except OzonApiError as e:
                if e.status_code == 429 and attempt < 5:
                    time.sleep(2 + attempt * 2)
                    continue
                raise
        queries += r.get("queries") or []
        page_count = int(r.get("page_count") or 1)
        page += 1
        if page >= page_count:
            break
    return queries


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    # 搜索词接口要求 date_to <= 今天-3（更近的日期会报 "no data for period"）
    d_to = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today() - timedelta(days=3)
    d_from = d_to - timedelta(days=days - 1)

    cid, key = load_creds()
    client = OzonSellerClient(client_id=cid, api_key=key)

    skumap = all_store_skus(client)
    print(f"区间：{d_from} ~ {d_to}（不含当天，T+1~2 滞后）   全店 SKU：{len(skumap)}\n")
    if not skumap:
        print("店内无在售商品。")
        return

    try:
        queries = fetch_queries(client, list(skumap), str(d_from), str(d_to))
    except OzonApiError as e:
        print(f"API 错误 HTTP {e.status_code}: {e}")
        return

    by_sku: dict[str, list[dict]] = {}
    for q in queries:
        by_sku.setdefault(str(q.get("sku") or ""), []).append(q)

    if not queries:
        print("该区间没有可披露的搜索词数据。")
        print("原因通常是单个搜索词的独立用户数没达到 Ozon 的样本/隐私阈值——")
        print("即便商品有搜索访问，只要分摊到每个词上人数太少，平台就不会披露具体词。")
        print("等流量再涨一截、或拉更长时间窗口后，这里才会开始出词。")
        return

    # 按该 SKU 总搜索量排序输出
    def sku_volume(sku: str) -> int:
        return sum(int(q.get("unique_search_users") or 0) for q in by_sku.get(sku, []))

    for sku in sorted(by_sku, key=sku_volume, reverse=True):
        info = skumap.get(sku, {})
        name = (info.get("name") or "")[:50]
        qs = sorted(by_sku[sku], key=lambda q: int(q.get("unique_search_users") or 0), reverse=True)
        print("=" * 90)
        print(f"SKU {sku}  {name}")
        print(f"{'搜索词':<38}{'搜索':>6}{'曝光':>6}{'点进%':>7}{'排位':>6}{'下单':>5}")
        print("-" * 90)
        for q in qs:
            query = (q.get("query") or "")[:36]
            srch = int(q.get("unique_search_users") or 0)
            view = int(q.get("unique_view_users") or 0)
            conv = float(q.get("view_conversion") or 0)
            pos = float(q.get("position") or 0)
            oc = int(q.get("order_count") or 0)
            # query 含中俄文等宽不齐，用制表分隔更稳
            print(f"{query:<38}{srch:>6}{view:>6}{conv:>6.1f}%{pos:>6.0f}{oc:>5}")
        print()


if __name__ == "__main__":
    main()
