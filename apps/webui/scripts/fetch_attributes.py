"""按 product_id 获取 Ozon 商品特征(含重量/尺寸)。

用法：
    python tools/ozon-listing-webui/fetch_attributes.py 1234567890 [更多id...]
    python tools/ozon-listing-webui/fetch_attributes.py --offer-id ABC-123
    python tools/ozon-listing-webui/fetch_attributes.py 123 --raw          # 打印原始 JSON

凭据优先级：命令行 --client-id/--api-key > 环境变量 OZON_CLIENT_ID/OZON_API_KEY
           > 项目设置(data/products.db，即 WebUI 设置页里填的那套)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api-seller.ozon.ru/v4/product/info/attributes"
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 强制 UTF-8 输出，避免 Windows 控制台(GBK)把俄/中文显示成乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass


def load_credentials(cli_client_id: str | None, cli_api_key: str | None) -> tuple[str, str]:
    """命令行 > 环境变量 > 项目 products.db 设置。"""
    client_id = cli_client_id or os.getenv("OZON_CLIENT_ID") or ""
    api_key = cli_api_key or os.getenv("OZON_API_KEY") or ""
    if not (client_id and api_key):
        try:
            from backend.store import Store  # noqa: PLC0415
            store = Store()
            try:
                st = store.get_settings()
            finally:
                store.close()
            client_id = client_id or str(st.get("ozon_client_id") or "")
            api_key = api_key or str(st.get("ozon_api_key") or "")
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 读取项目设置失败：{exc}", file=sys.stderr)
    if not (client_id and api_key):
        sys.exit("缺少凭据：用 --client-id/--api-key、环境变量，或先在 WebUI 设置页填好 Client-Id/Api-Key。")
    return client_id, api_key


def fetch_attributes(client_id: str, api_key: str, *,
                     product_ids: list[str] | None = None,
                     offer_ids: list[str] | None = None,
                     limit: int = 100) -> list[dict]:
    """翻页拉全 result（按 last_id 游标）。"""
    flt: dict = {"visibility": "ALL"}
    if product_ids:
        flt["product_id"] = [str(p) for p in product_ids]
    if offer_ids:
        flt["offer_id"] = [str(o) for o in offer_ids]
    headers = {
        "Client-Id": str(client_id),
        "Api-Key": str(api_key),
        "Content-Type": "application/json",
    }
    out: list[dict] = []
    last_id = ""
    while True:
        body = json.dumps({"filter": flt, "limit": limit, "last_id": last_id, "sort_dir": "asc"}).encode("utf-8")
        req = urllib.request.Request(ENDPOINT, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            sys.exit(f"HTTP {e.code}: {detail[:500]}")
        items = data.get("result") or []
        out.extend(items)
        last_id = data.get("last_id") or ""
        if not last_id or len(items) < limit:
            break
    return out


def print_item(it: dict) -> None:
    print("=" * 60)
    print(f"product_id : {it.get('id')}")
    print(f"offer_id   : {it.get('offer_id')}")
    print(f"名称       : {it.get('name')}")
    print(f"类目/类型   : description_category_id={it.get('description_category_id')} type_id={it.get('type_id')}")
    # 重量 / 尺寸
    du = it.get("dimension_unit") or "?"
    wu = it.get("weight_unit") or "?"
    print(f"重量       : {it.get('weight')} {wu}")
    print(f"尺寸(长×宽×高): {it.get('depth')} × {it.get('width')} × {it.get('height')} {du}")
    # 特征
    attrs = it.get("attributes") or []
    print(f"特征 ({len(attrs)} 项)：")
    for a in attrs:
        aid = a.get("attribute_id", a.get("id"))
        vals = a.get("values") or []
        txt = " , ".join(str(v.get("value") or v.get("dictionary_value_id") or "") for v in vals)
        print(f"   [id={aid}] {txt}")


def main() -> int:
    ap = argparse.ArgumentParser(description="按 product_id 获取 Ozon 商品特征(含重量/尺寸)")
    ap.add_argument("product_ids", nargs="*", help="一个或多个 product_id")
    ap.add_argument("--offer-id", action="append", default=[], help="改用 offer_id 查（可多次）")
    ap.add_argument("--client-id", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--raw", action="store_true", help="打印原始 JSON")
    args = ap.parse_args()

    if not args.product_ids and not args.offer_id:
        ap.error("至少给一个 product_id（或 --offer-id）")

    client_id, api_key = load_credentials(args.client_id, args.api_key)
    items = fetch_attributes(client_id, api_key,
                             product_ids=args.product_ids or None,
                             offer_ids=args.offer_id or None)
    if args.raw:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    if not items:
        print("（没查到，确认 product_id 是你店铺里的、且凭据正确）")
        return 1
    for it in items:
        print_item(it)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
