"""联网 smoke（手动跑）：用真实 Ozon key 拉 FBS 待处理订单。
**只拉单，绝不调 ship/label**（发货不可逆）。
前提：client_id/api_key 真实有效（client_id 曾被污染成 "C-1"，需先填回真实值）。

    PYTHONIOENCODING=utf-8 PYTHONPATH=tools/ozon-listing-webui \
        python tools/ozon-listing-webui/tests/smoke_fbs_live.py
"""
from __future__ import annotations

from webui.ozon_client_adapter import pull_fbs_postings
from webui.store import Store


def main() -> int:
    store = Store()
    try:
        settings = store.get_settings()
        if not settings.get("ozon_client_id") or settings.get("ozon_client_id") == "C-1":
            print("ABORT: 请先在设置页填回真实 Ozon Client-Id（当前为空或被污染的 C-1）")
            return 2
        postings = pull_fbs_postings(settings, status="awaiting_packaging", days=14)
        print("unfulfilled postings:", len(postings))
        for p in postings[:3]:
            prods = ", ".join(f"{x['offer_id']}x{x['quantity']}(sku={x['sku']})"
                              for x in p.get("products") or [])
            print(f"  {p['posting_number']} | {p['status']} | ship_by={p['ship_by']} | {prods}")
        print("SMOKE PASS（仅拉单，未发货）")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
