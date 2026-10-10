from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import webui.store as store_mod
from webui.store import Store


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u1", "source_offer_id": "1",
        "source_title": "t", "ozon_title": "T", "description": "d",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["x"], "attributes": {}, "status": "draft",
        "publish_response": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over)
    return d


class TestWarehouseColumn(unittest.TestCase):
    def test_warehouse_id_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            d = store.insert_draft(_draft())
            updated = store.update_draft(d["id"], {"warehouse_id": 77})
            self.assertEqual(updated["warehouse_id"], 77)
            self.assertEqual(store.get_draft(d["id"])["warehouse_id"], 77)
            store.close()


class TestBatchUpdateDrafts(unittest.TestCase):
    def _app(self, tmp: str):
        import importlib  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "app.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        return svc.App()

    def test_batch_set_stock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                a = app.store.insert_draft(_draft(source_url="a", source_offer_id="1"))
                b = app.store.insert_draft(_draft(source_url="b", source_offer_id="2"))
                r = app.batch_update_drafts([a["id"], b["id"]], {"stock": 50})
                self.assertEqual(len(r["updated"]), 2)
                self.assertEqual(app.store.get_draft(a["id"])["stock"], 50)
                self.assertEqual(app.store.get_draft(b["id"])["stock"], 50)
            finally:
                app.store.close()

    def test_batch_set_warehouse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                a = app.store.insert_draft(_draft(source_url="a", source_offer_id="1"))
                r = app.batch_update_drafts([a["id"]], {"warehouse_id": 9})
                self.assertEqual(len(r["updated"]), 1)
                self.assertEqual(app.store.get_draft(a["id"])["warehouse_id"], 9)
            finally:
                app.store.close()

    def test_published_status_preserved(self) -> None:
        # 批量改库存不应把已发布草稿降级
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                a = app.store.insert_draft(_draft(source_url="a", source_offer_id="1"))
                app.store.update_draft(a["id"], {"status": "published"})
                app.batch_update_drafts([a["id"]], {"stock": 5})
                self.assertEqual(app.store.get_draft(a["id"])["status"], "published")
            finally:
                app.store.close()

    def test_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                a = app.store.insert_draft(_draft(source_url="a", source_offer_id="1"))
                with self.assertRaises(ValueError):
                    app.batch_update_drafts([a["id"]], {"price": "999"})
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
