"""联网 smoke（手动跑）：用真实 Ozon key 拉 FBS/rFBS 仓库列表。
前提：设置里 client_id/api_key 真实有效（client_id 曾被测试污染成 "C-1"，需先填回真实值）。

    PYTHONIOENCODING=utf-8 PYTHONPATH=tools/ozon-listing-webui \
        python tools/ozon-listing-webui/tests/smoke_warehouses_live.py
"""
from __future__ import annotations

from webui.ozon_client_adapter import fetch_warehouses
from webui.store import Store


def main() -> int:
    store = Store()
    try:
        settings = store.get_settings()
        if not settings.get("ozon_client_id") or settings.get("ozon_client_id") == "C-1":
            print("ABORT: 请先在设置页填回真实 Ozon Client-Id（当前为空或被污染的 C-1）")
            return 2
        whs = fetch_warehouses(settings)
        print("warehouses:", len(whs))
        for w in whs[:5]:
            print(f"  {w.get('warehouse_id')} | {w.get('name')} | "
                  f"is_rfbs={w.get('is_rfbs')} | {w.get('status')}")
        print("SMOKE PASS")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
