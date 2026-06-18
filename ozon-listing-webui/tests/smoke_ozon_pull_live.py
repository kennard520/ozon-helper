"""联网 smoke（手动跑，非默认 CI）：用真实 Ozon key 拉自己后台已建的商品，
验证 list/info/attributes 三接口活的、能合并成草稿字段。

前提：设置里 ozon_client_id / ozon_api_key 必须是**真实有效**的（注意历史上
client_id 曾被测试污染成 "C-1"，需先在设置页填回真实 Client-Id）。

用法（仓库根）：
    PYTHONIOENCODING=utf-8 PYTHONPATH=tools/ozon-listing-webui \
        python tools/ozon-listing-webui/tests/smoke_ozon_pull_live.py
"""
from __future__ import annotations

from backend.ozon_client_adapter import (
    get_ozon_attributes,
    get_ozon_info,
    list_ozon_products,
    ozon_to_draft,
)
from backend.store import Store


def main() -> int:
    store = Store()
    try:
        settings = store.get_settings()
        if not settings.get("ozon_client_id") or settings.get("ozon_client_id") == "C-1":
            print("ABORT: 请先在设置页填回真实 Ozon Client-Id（当前为空或被污染的 C-1）")
            return 2

        listing = list_ozon_products(settings, visibility="ALL")
        print("products listed:", len(listing))
        if not listing:
            print("SMOKE PASS (账号下暂无商品)")
            return 0

        offer_ids = [str(it["offer_id"]) for it in listing[:5] if it.get("offer_id")]
        info = get_ozon_info(settings, offer_ids)
        attrs = get_ozon_attributes(settings, offer_ids)
        oid = offer_ids[0]
        draft = ozon_to_draft(info.get(oid, {}), attrs.get(oid))
        print("first offer_id:", oid)
        print("  name:", draft["ozon_title"][:50])
        print("  price:", draft["price"], "| stock:", draft["stock"])
        print("  cat/type:", draft["category_id"], draft["type_id"])
        print("  weight_g:", draft["weight_g"], "| dims mm:",
              draft["length_mm"], draft["width_mm"], draft["height_mm"])
        print("  images:", len(draft["images"]), "| attrs:", len(draft["attributes"]))
        assert draft["offer_id"] == oid
        print("SMOKE PASS")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
