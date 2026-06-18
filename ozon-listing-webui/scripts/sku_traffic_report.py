"""按 SKU 拉取 Ozon 曝光/点击/加购统计（昨天 + 今天）。

数据源：/v1/analytics/data（与卖家后台 分析→图表 一致；需 Premium Plus/Pro 订阅，
每账号每分钟限 1 次请求）。指标口径（抓自 specs/ozon-seller-api swagger 2026-05-30）：
  hits_view     曝光（показы，被展示次数）
  session_view  会话浏览（访问/进店看了商品的会话数，最接近"点击"）
  hits_tocart   加入购物车次数
  conv_tocart   加购转化率 = hits_tocart / session_view
  ordered_units 下单件数（参考）

用法：
  $env:PYTHONPATH = "tools/ozon-listing-webui;tools"
  python tools/ozon-listing-webui/scripts/sku_traffic_report.py [YYYY-MM-DD 今天日期，默认取系统当天]
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]          # ozon-listing-webui
sys.path.insert(0, str(ROOT.parent))                # tools/ （for ozon_api）

from ozon_api import OzonSellerClient, OzonApiError  # noqa: E402

DB = ROOT / "data" / "products.db"
METRICS = ["hits_view", "session_view", "hits_tocart", "conv_tocart", "ordered_units"]
LABELS = {
    "hits_view": "曝光",
    "session_view": "访问(点击)",
    "hits_tocart": "加购",
    "conv_tocart": "加购率%",
    "ordered_units": "下单件",
}


def load_creds() -> tuple[str, str]:
    con = sqlite3.connect(DB)
    kv = {k: json.loads(v) if v and v[0] in '"[{' else v
          for k, v in con.execute("select key,value from settings")}
    con.close()
    return str(kv["ozon_client_id"]), str(kv["ozon_api_key"])


def fetch(client: OzonSellerClient, d_from: str, d_to: str) -> list[dict]:
    body = {
        "date_from": d_from,
        "date_to": d_to,
        "dimension": ["sku", "day"],
        "metrics": METRICS,
        "limit": 1000,
        "offset": 0,
        "sort": [{"key": "hits_view", "order": "DESC"}],
    }
    r = client.request("/v1/analytics/data", body)
    return (r.get("result") or {}).get("data") or []


def main() -> None:
    today = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    yesterday = today - timedelta(days=1)
    cid, key = load_creds()
    client = OzonSellerClient(client_id=cid, api_key=key)

    print(f"拉取区间：{yesterday} ~ {today}  (dimension=sku,day)\n")
    try:
        rows = fetch(client, str(yesterday), str(today))
    except OzonApiError as e:
        print(f"API 错误 HTTP {e.status_code}: {e}")
        if e.status_code == 403:
            print("→ /v1/analytics/data 需要 Premium Plus / Premium Pro 订阅。")
        return

    # rows: [{dimensions:[{id,name},{id:'2026-06-04'}], metrics:[..按 METRICS 顺序..]}]
    # 聚合成 {(day): {sku: {name, metrics}}}
    by_day: dict[str, dict] = {str(yesterday): {}, str(today): {}}
    for row in rows:
        dims = row.get("dimensions") or []
        if len(dims) < 2:
            continue
        sku = str(dims[0].get("id") or "")
        name = dims[0].get("name") or ""
        day = str(dims[1].get("id") or "")
        vals = row.get("metrics") or []
        m = dict(zip(METRICS, vals))
        by_day.setdefault(day, {})[sku] = {"name": name, **m}

    for day in (str(yesterday), str(today)):
        skus = by_day.get(day) or {}
        print("=" * 96)
        print(f"[{day}]    共 {len(skus)} 个有流量的 SKU")
        print("=" * 96)
        if not skus:
            print("  （无数据——今天的数据 Ozon 通常 T+1 才完整，明天再看）\n")
            continue
        header = f"{'SKU':<12}{'曝光':>8}{'访问':>8}{'加购':>8}{'加购率':>8}{'下单':>7}  商品名"
        print(header)
        print("-" * 96)
        ordered = sorted(skus.items(), key=lambda kv: kv[1].get("hits_view", 0), reverse=True)
        tot = {k: 0.0 for k in METRICS}
        for sku, m in ordered:
            for k in METRICS:
                tot[k] += float(m.get(k) or 0)
            conv = float(m.get("conv_tocart") or 0)
            name = (m.get("name") or "")[:40]
            print(f"{sku:<12}{int(m.get('hits_view') or 0):>8}{int(m.get('session_view') or 0):>8}"
                  f"{int(m.get('hits_tocart') or 0):>8}{conv:>7.1f}%{int(m.get('ordered_units') or 0):>7}  {name}")
        print("-" * 96)
        conv_all = (tot["hits_tocart"] / tot["session_view"] * 100) if tot["session_view"] else 0
        print(f"{'合计':<12}{int(tot['hits_view']):>8}{int(tot['session_view']):>8}"
              f"{int(tot['hits_tocart']):>8}{conv_all:>7.1f}%{int(tot['ordered_units']):>7}\n")


if __name__ == "__main__":
    main()
