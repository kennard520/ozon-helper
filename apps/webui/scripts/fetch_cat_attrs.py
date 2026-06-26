# -*- coding: utf-8 -*-
"""拉某类目+type 的属性清单（id/name/是否必填/是否字典）。落 JSON。"""
import json, os, sqlite3, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "data", "products.db")
OUT = os.path.join(HERE, "_cat_attrs.json")
CAT = int(sys.argv[1]) if len(sys.argv) > 1 else 30960284
TYP = int(sys.argv[2]) if len(sys.argv) > 2 else 97897


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
    return -1, "NET_FAIL %s" % last


def main():
    cid, key = creds()
    st, d = post("/v1/description-category/attribute",
                 {"description_category_id": CAT, "type_id": TYP, "language": "RU"}, cid, key)
    out = {"status": st, "cat": CAT, "type": TYP, "attributes": d.get("result", []) if isinstance(d, dict) else d}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n = len(out["attributes"]) if isinstance(out["attributes"], list) else 0
    print("OK", OUT, "status", st, "attrs", n)


if __name__ == "__main__":
    main()
