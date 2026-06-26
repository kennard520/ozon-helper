from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from webui.drafts import create_draft_from_url
from webui.store import Store


class StoreTest(unittest.TestCase):
    def test_save_and_load_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            store.save_settings({"ozon_client_id": "123", "contract_currency": "RUB"})

            self.assertEqual(store.get_settings()["ozon_client_id"], "123")
            self.assertEqual(store.get_settings()["contract_currency"], "RUB")
            store.close()

    def test_insert_list_update_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            draft = store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/123456789012.html"))
            same = store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/123456789012.html"))

            self.assertEqual(draft["id"], same["id"])
            updated = store.update_draft(draft["id"], {
                "ozon_title": "Органайзер",
                "description": "Описание",
                "category_id": "17028922",
                "type_id": "94307",
                "price": "799",
                "old_price": "999",
                "stock": 3,
                "weight_g": 500,
                "length_mm": 300,
                "width_mm": 200,
                "height_mm": 100,
                "images": ["https://example.test/a.jpg"],
                "attributes": [],
                "purchase_url": "https://supplier.example/item/a-1",
                "purchase_note": "下单选白色大号，备注不要发票",
            })

            self.assertEqual(updated["status"], "ready")
            self.assertEqual(updated["purchase_url"], "https://supplier.example/item/a-1")
            self.assertEqual(updated["purchase_note"], "下单选白色大号，备注不要发票")
            self.assertEqual(len(store.list_drafts()), 1)
            store.delete_draft(draft["id"])
            self.assertEqual(store.list_drafts(), [])
            store.close()


    def test_new_product_columns_exist_and_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            cols = {r["name"] for r in store.conn.execute("PRAGMA table_info(drafts)")}
            self.assertIn("source", cols)
            self.assertIn("ozon_product_id", cols)
            self.assertIn("offer_id", cols)
            # 新建草稿后，新列可读、默认安全值
            draft = store.insert_draft(
                create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
            )
            row = store.conn.execute(
                "SELECT source, ozon_product_id, offer_id FROM drafts WHERE id=?",
                (draft["id"],),
            ).fetchone()
            self.assertEqual(row["source"], "")
            self.assertIsNone(row["ozon_product_id"])
            # 货号必填：未提供时自动补随机货号（不再是空）
            self.assertTrue(row["offer_id"])
            store.close()


    def test_source_offer_supplier_roundtrip(self) -> None:
        """Task1 加的 source/ozon_product_id/offer_id/supplier 必须能存、能读、能改。
        offer_id 是功能5 备货 JOIN 的钥匙；supplier 是功能1 标供应商；否则全是死列。"""
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
            draft.update({"source": "1688_scrape", "offer_id": "SKU-001",
                          "supplier": "四川某厂", "ozon_product_id": 98765})
            inserted = store.insert_draft(draft)
            self.assertEqual(inserted["source"], "1688_scrape")
            self.assertEqual(inserted["offer_id"], "SKU-001")
            self.assertEqual(inserted["supplier"], "四川某厂")
            self.assertEqual(inserted["ozon_product_id"], 98765)
            # 编辑供应商/货号（功能1 标供应商场景）
            updated = store.update_draft(inserted["id"], {
                "supplier": "重庆另一厂", "offer_id": "SKU-002"})
            self.assertEqual(updated["supplier"], "重庆另一厂")
            self.assertEqual(updated["offer_id"], "SKU-002")
            self.assertEqual(updated["source"], "1688_scrape")  # 未传不应被清空
            store.close()

    def test_source_raw_roundtrip(self) -> None:
        import tempfile
        from pathlib import Path

        from webui.drafts import create_draft_from_url
        from webui.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            d = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
            d["source_raw"] = {"title": "中文标题", "params": [{"k": "材质", "v": "铝"}], "description_text": "好货"}
            inserted = store.insert_draft(d)
            got = store.get_draft(inserted["id"])
            self.assertEqual(got["source_raw"]["params"][0]["k"], "材质")
            self.assertEqual(got["source_raw"]["description_text"], "好货")
            store.close()


if __name__ == "__main__":
    unittest.main()
