# -*- coding: utf-8 -*-
"""Ozon 商品漏斗统计：曝光 / 点击(PDP访问) / 加购 / 下单。
调 POST /v1/analytics/data（AnalyticsAPI_AnalyticsGetData，抓取于 specs 2026-05-30）。
凭证从 ozon-listing-webui/data/products.db 的 settings 表读取。
注意：hits_/session_/conv_ 系列指标仅 Premium Plus/Pro 卖家可用，无订阅会被拒或只回 revenue/ordered_units。
限速：每账号每分钟 1 次。
"""
from __future__ import annotations
import sys, json, sqlite3, datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve()
TOOLS = HERE.parents[2]                       # backend → webui → tools
sys.path.insert(0, str(TOOLS))
from ozon_api.client import OzonSellerClient, OzonApiError  # noqa: E402

DB = HERE.parents[1] / "data" / "products.db"

# 指标 → 中文名（枚举来自 swagger analyticsMetric）
FULL_METRICS = [
    ("hits_view",        "曝光·总"),
    ("hits_view_search", "曝光·搜索"),
    ("hits_view_pdp",    "曝光·详情页"),
    ("session_view_pdp", "点击/访问详情页(会话)"),
    ("hits_tocart",      "加购·总"),
    ("hits_tocart_pdp",  "加购·详情页"),
    ("conv_tocart",      "加购转化率"),
    ("ordered_units",    "下单件数"),
    ("revenue",          "销售额"),
]
BASE_METRICS = [("ordered_units", "下单件数"), ("revenue", "销售额")]


def load_client() -> OzonSellerClient:
    rows = dict(sqlite3.connect(DB).execute("SELECT key,value FROM settings").fetchall())
    def g(k):
        v = rows.get(k)
        try: v = json.loads(v)
        except Exception: pass
        return str(v).strip()
    return OzonSellerClient(client_id=g("ozon_client_id"), api_key=g("ozon_api_key"))


def fetch(client, metrics, date_from, date_to, dimension):
    body = {
        "date_from": date_from, "date_to": date_to,
        "dimension": dimension,
        "metrics": [m for m, _ in metrics],
        "limit": 1000, "offset": 0,
        "sort": [{"key": metrics[0][0], "order": "DESC"}],
    }
    return client.request("/v1/analytics/data", body)


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    date_to = dt.date(2026, 6, 4)              # 锚定当前日期（环境 currentDate）
    date_from = date_to - dt.timedelta(days=days)
    df, dt_ = date_from.isoformat(), date_to.isoformat()
    client = load_client()
    print(f"窗口: {df} ~ {dt_} ({days}天) | 维度: sku\n")

    metrics = FULL_METRICS
    msg = lambda e: e.payload.get("message") if isinstance(e.payload, dict) else str(e)
    # 限速：分析接口每账号每分钟 1 次 + 整体每秒 2 次。429 时自动等待重试。
    import time
    for attempt in range(4):
        try:
            data = fetch(client, metrics, df, dt_, ["sku"])
            break
        except OzonApiError as e:
            if e.status_code == 429 and attempt < 3:
                wait = 20 * (attempt + 1)
                print(f"[限速 429] {msg(e)} → 等 {wait}s 重试 ({attempt+1}/3)…")
                time.sleep(wait)
                continue
            if e.status_code == 403:
                print(f"[403 拒绝访问] {msg(e)}")
                print("→ 该指标需 Premium Plus/Pro 订阅。降级到基础指标…\n")
                metrics = BASE_METRICS
                data = fetch(client, metrics, df, dt_, ["sku"])
                break
            print(f"[失败] HTTP {e.status_code}: {e.payload}")
            return
    else:
        print("[多次限速仍失败] 稍后再试（分析接口每分钟仅 1 次）。")
        return

    rows = (data.get("result") or {}).get("data") or []
    if not rows:
        print("无数据（该窗口内没有曝光/订单，或商品尚未产生流量）。")
        print("原始响应:", json.dumps(data, ensure_ascii=False)[:500])
        return

    headers = ["SKU"] + [name for _, name in metrics]
    print(" | ".join(headers))
    print("-" * 100)
    totals = [0.0] * len(metrics)
    for r in rows:
        dim = r.get("dimensions") or [{}]
        sku = dim[0].get("id") or dim[0].get("name") or "?"
        vals = r.get("metrics") or []
        cells = [str(sku)]
        for i, v in enumerate(vals):
            totals[i] += (v or 0)
            cells.append(f"{v:.2f}" if metrics[i][0] in ("conv_tocart", "revenue") else str(int(v or 0)))
        print(" | ".join(cells))
    print("-" * 100)
    keys = [m for m, _ in metrics]
    def total_cell(i):
        key = keys[i]
        if key == "revenue":
            return f"{totals[i]:.2f}"
        if key == "conv_tocart":
            # 比率不能求和：用 总加购/总曝光 重算
            if "hits_tocart" in keys and "hits_view" in keys:
                v = totals[keys.index("hits_view")]
                return f"{(totals[keys.index('hits_tocart')] / v * 100):.2f}" if v else "0.00"
            return "—"
        return str(int(totals[i]))
    print("合计 | " + " | ".join(total_cell(i) for i in range(len(metrics))))


if __name__ == "__main__":
    main()
