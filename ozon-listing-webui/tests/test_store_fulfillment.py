from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.store import Store


class FulfillmentStoreTest(unittest.TestCase):
    def test_upsert_and_list_warehouses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            store.upsert_warehouses([
                {"warehouse_id": 111, "name": "FBS-Москва", "is_rfbs": True, "status": "created"},
                {"warehouse_id": 222, "name": "FBS-СПб", "is_rfbs": False, "status": "created"},
            ])
            rows = store.list_warehouses()
            self.assertEqual({r["warehouse_id"] for r in rows}, {111, 222})
            # 设默认仓：只允许一个
            store.set_default_warehouse(222)
            rows = {r["warehouse_id"]: r for r in store.list_warehouses()}
            self.assertTrue(rows[222]["is_default"])
            self.assertFalse(rows[111]["is_default"])
            store.close()

    def test_upsert_postings_and_build_procurement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            # 先有一个商品，带供应商/采购链接
            store.conn.execute(
                "INSERT INTO drafts (source_platform, source_url, source_offer_id, source_title, "
                "ozon_title, description, category_id, price, old_price, stock, images_json, "
                "attributes_json, status, validation_errors_json, created_at, updated_at, "
                "offer_id, purchase_url, purchase_note, supplier) "
                "VALUES ('1688','u1','o1','t','t','d','1','10','10',1,'[]','{}','draft','[]',"
                "'now','now','SKU-1','https://detail.1688.com/offer/1.html','厂家A','厂家A')"
            )
            store.conn.commit()
            store.upsert_postings([
                {"posting_number": "P-1", "ozon_order_id": "O-1", "status": "awaiting_packaging",
                 "ship_by": "2026-06-01T00:00:00Z", "warehouse_id": 111,
                 "products": [{"offer_id": "SKU-1", "quantity": 2}], "raw": {"x": 1}},
            ])
            self.assertEqual(len(store.list_postings()), 1)
            # 备货行从 posting × 商品 JOIN 生成
            store.rebuild_procurement()
            proc = store.list_procurement()
            self.assertEqual(len(proc), 1)
            self.assertEqual(proc[0]["offer_id"], "SKU-1")
            self.assertEqual(proc[0]["qty"], 2)
            self.assertEqual(proc[0]["supplier"], "厂家A")
            self.assertEqual(proc[0]["purchase_url"], "https://detail.1688.com/offer/1.html")
            self.assertEqual(proc[0]["purchase_state"], "待采购")
            store.close()

    def test_set_procurement_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            store.upsert_postings([
                {"posting_number": "P-9", "ozon_order_id": "O-9", "status": "awaiting_packaging",
                 "ship_by": None, "warehouse_id": None,
                 "products": [{"offer_id": "X", "quantity": 1}], "raw": {}},
            ])
            store.rebuild_procurement()
            pid = store.list_procurement()[0]["id"]
            store.set_procurement_state(pid, "已下单", note="拍了2件")
            row = store.list_procurement()[0]
            self.assertEqual(row["purchase_state"], "已下单")
            self.assertEqual(row["note"], "拍了2件")
            store.close()


if __name__ == "__main__":
    unittest.main()
