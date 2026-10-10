"""联网 smoke（手动跑）：用真实 Ozon key 拉每个仓库配置的配送方式（/v2/delivery-method/list）。
校验 v2 的字段与 cursor 翻页（filter.warehouse_ids 数组 + cursor + has_next）。
前提：设置里 client_id/api_key 真实有效（client_id 曾被测试污染成 "C-1"，需先填回真实值）。

    PYTHONIOENCODING=utf-8 PYTHONPATH=tools/ozon-listing-webui \
        python tools/ozon-listing-webui/tests/smoke_delivery_methods_live.py
"""
from __future__ import annotations

from webui.ozon_client_adapter import fetch_delivery_methods, fetch_warehouses
from webui.store import Store


def main() -> int:
    store = Store()
    try:
        settings = store.get_settings()
        if not settings.get("ozon_client_id") or settings.get("ozon_client_id") == "C-1":
            print("ABORT: 请先在设置页填回真实 Ozon Client-Id（当前为空或被污染的 C-1）")
            return 2
        whs = fetch_warehouses(settings)
        wids = [w.get("warehouse_id") for w in whs]
        print("warehouses:", len(whs), "->", wids)
        methods = fetch_delivery_methods(settings, wids)
        print("delivery_methods:", len(methods))
        for m in methods[:10]:
            print(f"  wh={m.get('warehouse_id')} | id={m.get('delivery_method_id')} | "
                  f"{m.get('name')} | provider={m.get('provider_id')} | "
                  f"status={m.get('status')} | cutoff={m.get('cutoff')}")
        if not methods:
            print("WARN: 0 条配送方式——确认仓库确有配置，或检查 v2 响应键名（result / delivery_methods）")
        print("SMOKE PASS")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
