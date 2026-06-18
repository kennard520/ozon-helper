# -*- coding: utf-8 -*-
"""一次性：拉两个 SKU 的完整 listing（info/list + description + v4 attributes），落 JSON 对比。"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "products.db")
OUT = os.path.join(HERE, "_compare.json")

SKUS = [int(x) for x in sys.argv[1:]] or [4457465432, 4585366561]


def creds():
    con = sqlite3.connect(DB_PATH)
    try:
        rows = dict(con.execute("SELECT key, value FROM settings"))
    finally:
        con.close()
    cid = (rows.get("ozon_client_id") or "").strip().strip('"').strip("'")
    key = (rows.get("ozon_api_key") or "").strip().strip('"').strip("'")
    return cid, key


def post(path, body, cid, key, tries=4):
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(
            "https://api-seller.ozon.ru" + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Client-Id": cid, "Api-Key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001  瞬时 SSL/网络断连，退避重试
            last = e
            time.sleep(3 * (attempt + 1))
    return -1, "NET_FAIL: %s" % last


def main():
    cid, key = creds()
    out = {}

    st, info = post("/v3/product/info/list", {"sku": SKUS}, cid, key)
    out["info_list_status"] = st
    items = info.get("items", []) if isinstance(info, dict) else []
    out["info_list"] = items

    # offer_id 反查
    offer_ids = []
    for it in items:
        if it.get("offer_id"):
            offer_ids.append(str(it["offer_id"]))

    # 描述
    descs = {}
    for oid in offer_ids:
        s, d = post("/v1/product/info/description", {"offer_id": oid}, cid, key)
        if s == 200 and isinstance(d, dict):
            descs[oid] = (d.get("result") or {}).get("description", "")
        else:
            descs[oid] = "[HTTP %s] %s" % (s, str(d)[:200])
        # 中间落盘一次，保证就算后面崩了也有已拿到的
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({**out, "descriptions": descs}, f, ensure_ascii=False, indent=1)
    out["descriptions"] = descs

    # 属性表
    s, attr = post(
        "/v4/product/info/attributes",
        {"filter": {"offer_id": offer_ids, "visibility": "ALL"}, "limit": 100, "sort_dir": "asc"},
        cid, key,
    )
    out["attributes_status"] = s
    out["attributes"] = attr.get("result", []) if isinstance(attr, dict) else attr

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("OK", OUT, "skus=", SKUS, "offers=", offer_ids)


if __name__ == "__main__":
    main()
