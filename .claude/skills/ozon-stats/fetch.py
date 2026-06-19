#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ozon 流量/转化数据抓取器（/ozon-stats skill 用）。

只用标准库。流程：
1. 从 ozon-listing-webui 的 products.db 读 Client-Id / Api-Key
2. 一次 /v1/analytics/data（dimension=[sku,day]）拿全维度原料（避开 1分钟1次限速）
3. 一次 /v3/product/info/list 反查 SKU→俄语标题
4. 聚合成 totals / by_sku / by_day，写 UTF-8 的 _last.json（规避 Windows 控制台乱码）

无参 = 昨天。用法见 --help。
"""
import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DB_PATH = os.path.join(REPO, "tools", "ozon-listing-webui", "data", "products.db")
OUT_PATH = os.path.join(HERE, "_last.json")

# 指标顺序 == 请求顺序 == 响应 metrics 数组顺序
METRICS = [
    "hits_view",       # 曝光
    "session_view",    # 会话(到访)
    "hits_tocart",     # 加购
    "conv_tocart",     # 加购转化率(%) —— 聚合层会重算
    "ordered_units",   # 下单件数
    "returns",         # 退货
    "cancellations",   # 取消
    "revenue",         # 金额(₽)
]


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def _parse_stores(raw):
    """ozon_stores 的 value 是 JSON（可能双层编码）→ list[dict]。"""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, str):
            v = json.loads(v)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def load_creds(store_client_id=None):
    if not os.path.exists(DB_PATH):
        die("找不到 products.db（%s）。先在 ozon-listing-webui WebUI 里配置 Ozon Client-Id / Api-Key。" % DB_PATH)
    con = sqlite3.connect(DB_PATH)
    try:
        rows = dict(con.execute("SELECT key, value FROM settings"))
    finally:
        con.close()
    if store_client_id:
        want = str(store_client_id).strip().strip('"').strip("'")
        for s in _parse_stores(rows.get("ozon_stores")):
            cid = str(s.get("client_id") or "").strip()
            if cid == want:
                key = str(s.get("api_key") or "").strip()
                if not key:
                    die("店 %s（%s）没存 api_key。" % (cid, s.get("name") or ""))
                return cid, key, str(s.get("name") or "")
        die("ozon_stores 里找不到 client_id=%s 的店。" % want)
    cid = (rows.get("ozon_client_id") or "").strip().strip('"').strip("'")
    key = (rows.get("ozon_api_key") or "").strip().strip('"').strip("'")
    if not cid or not key:
        die("settings 表里没有 ozon_client_id / ozon_api_key。去 WebUI 设置页填好再来。")
    # 反查默认店名（在 ozon_stores 里找 client_id 匹配的）
    name = ""
    for s in _parse_stores(rows.get("ozon_stores")):
        if str(s.get("client_id") or "").strip() == cid:
            name = str(s.get("name") or ""); break
    return cid, key, name


def post(url, body, cid, key, timeout=60):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Client-Id": cid, "Api-Key": key, "Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def fetch_analytics(date_from, date_to, cid, key):
    body = {
        "date_from": date_from,
        "date_to": date_to,
        "dimension": ["sku", "day"],
        "metrics": METRICS,
        "sort": [{"key": "hits_view", "order": "DESC"}],
        "limit": 1000,
    }
    st, txt = post("https://api-seller.ozon.ru/v1/analytics/data", body, cid, key)
    if st == 429:
        time.sleep(62)
        st, txt = post("https://api-seller.ozon.ru/v1/analytics/data", body, cid, key)
    if st == 403:
        die("HTTP 403：可能未订阅 Premium，曝光/加购类指标对该账号不可用。原文：%s" % txt[:300])
    if st != 200:
        die("analytics/data 返回 HTTP %s：%s" % (st, txt[:400]))
    return json.loads(txt)


def fetch_names(skus, cid, key):
    if not skus:
        return {}
    names = {}
    st, txt = post(
        "https://api-seller.ozon.ru/v3/product/info/list",
        {"sku": [int(x) for x in skus]},
        cid,
        key,
    )
    if st != 200:
        return names  # 名称是锦上添花，失败就留空
    d = json.loads(txt)
    items = d.get("items") or d.get("result", {}).get("items") or []
    for it in items:
        name = it.get("name", "")
        keys = []
        if it.get("sku"):
            keys.append(str(it["sku"]))
        for src in it.get("sources", []) or []:
            if src.get("sku"):
                keys.append(str(src["sku"]))
        for k in keys:
            names[k] = name
    return names


def blank_acc():
    return {k: 0.0 for k in METRICS}


def add_row(acc, metric_vals):
    for i, k in enumerate(METRICS):
        acc[k] += metric_vals[i] or 0


def finalize(acc):
    """rate 类指标在聚合层重算；整数指标转 int。"""
    out = {}
    for k in METRICS:
        if k == "conv_tocart":
            sv = acc["session_view"]
            out[k] = round(acc["hits_tocart"] / sv * 100, 2) if sv else 0.0
        elif k == "revenue":
            out[k] = round(acc[k], 2)
        else:
            out[k] = int(round(acc[k]))
    return out


def aggregate(data, names):
    rows = data.get("result", {}).get("data", [])
    by_sku = {}
    by_day = {}
    totals = blank_acc()
    for r in rows:
        dims = r["dimensions"]
        m = r["metrics"]
        # dimension 顺序 = 请求顺序 [sku, day]
        sku = dims[0]["id"]
        day = dims[1]["id"] if len(dims) > 1 else ""
        add_row(totals, m)
        by_sku.setdefault(sku, blank_acc())
        add_row(by_sku[sku], m)
        by_day.setdefault(day, blank_acc())
        add_row(by_day[day], m)

    sku_list = []
    for sku, acc in by_sku.items():
        rec = finalize(acc)
        rec["sku"] = sku
        rec["name"] = names.get(sku, "")
        sku_list.append(rec)
    sku_list.sort(key=lambda x: x["hits_view"], reverse=True)

    day_list = []
    for day, acc in sorted(by_day.items()):
        rec = finalize(acc)
        rec["day"] = day
        day_list.append(rec)

    return finalize(totals), sku_list, day_list, len(rows)


def parse_range(args, today):
    yesterday = today - dt.timedelta(days=1)
    if args.date:
        return args.date, args.date
    if args.days:
        start = yesterday - dt.timedelta(days=args.days - 1)
        return start.isoformat(), yesterday.isoformat()
    if args.date_from or args.date_to:
        df = args.date_from or args.date_to
        dtt = args.date_to or args.date_from
        return df, dtt
    return yesterday.isoformat(), yesterday.isoformat()


def main():
    ap = argparse.ArgumentParser(description="Ozon 流量/转化数据抓取（默认昨天）")
    ap.add_argument("--from", dest="date_from", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", help="截止日期 YYYY-MM-DD")
    ap.add_argument("--date", help="单日 YYYY-MM-DD")
    ap.add_argument("--days", type=int, help="滚动 N 天（截止昨天）")
    ap.add_argument("--store", help="目标店 Client-Id（从 ozon_stores 取 key）；不传=默认店")
    ap.add_argument("--out", help="输出 JSON 路径；默认 _last.json")
    args = ap.parse_args()

    out_path = args.out or OUT_PATH
    today = dt.date.today()
    date_from, date_to = parse_range(args, today)

    cid, key, store_name = load_creds(args.store)
    data = fetch_analytics(date_from, date_to, cid, key)
    rows = data.get("result", {}).get("data", [])
    skus = sorted({r["dimensions"][0]["id"] for r in rows})
    names = fetch_names(skus, cid, key)
    totals, by_sku, by_day, nrows = aggregate(data, names)

    result = {
        "meta": {
            "store_client_id": cid,
            "store_name": store_name,
            "date_from": date_from,
            "date_to": date_to,
            "row_count": nrows,
            "sku_count": len(by_sku),
            "truncated": nrows >= 1000,
            "api_timestamp": data.get("timestamp", ""),
            "metrics_order": METRICS,
            "note": "rate 类(conv_tocart)在聚合层用 加购/会话 重算；analytics/data 限 1分钟1次",
        },
        "totals": totals,
        "by_sku": by_sku,
        "by_day": by_day,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    label = "%s/%s" % (store_name or "?", cid)
    if nrows == 0:
        print("OK_EMPTY %s  [%s] (%s ~ %s 无流量数据)" % (out_path, label, date_from, date_to))
    else:
        print("OK %s  [%s] (%s ~ %s, %d 行, %d SKU%s)" % (
            out_path, label, date_from, date_to, nrows, len(by_sku),
            ", 已截断1000行" if nrows >= 1000 else "",
        ))


if __name__ == "__main__":
    main()
