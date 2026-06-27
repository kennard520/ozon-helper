# -*- coding: utf-8 -*-
"""拉指定属性的字典候选值。落 JSON。"""
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "products.db")
OUT = os.path.join(HERE, "_attr_values.json")
CAT, TYP = 86539914, 91884
ATTRS = [int(x) for x in sys.argv[1:]] or [9782, 8229, 5111, 10060, 11115, 21281, 10400]


def creds():
    con = sqlite3.connect(DB)
    try:
        rows = dict(con.execute("SELECT key,value FROM settings"))
    finally:
        con.close()
    cid = (rows.get("ozon_client_id") or "").strip().strip('"').strip("'")
    key = (rows.get("ozon_api_key") or "").strip().strip('"').strip("'")
    return cid, key


def post(path, body, cid, key, tries=4):
    last = None
    for i in range(tries):
        req = urllib.request.Request("https://api-seller.ozon.ru" + path,
            data=json.dumps(body).encode(), headers={"Client-Id": cid, "Api-Key": key,
            "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e; time.sleep(3 * (i + 1))
    return -1, str(last)


def main():
    cid, key = creds()
    out = {}
    for aid in ATTRS:
        st, d = post("/v1/description-category/attribute/values",
            {"description_category_id": CAT, "type_id": TYP, "attribute_id": aid,
             "language": "RU", "limit": 100}, cid, key)
        vals = d.get("result", []) if isinstance(d, dict) else d
        out[str(aid)] = [v.get("value") for v in vals] if isinstance(vals, list) else vals
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print("OK", OUT)


if __name__ == "__main__":
    main()
