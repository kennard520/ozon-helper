import importlib
import tempfile
import unittest
from pathlib import Path

from backend.drafts import create_draft_from_url
from backend.store import Store

URL = "https://detail.1688.com/offer/123456789012.html"


class StoreScopedDraftsTest(unittest.TestCase):
    def test_same_source_one_draft_per_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            try:
                a = create_draft_from_url(URL); a["store_client_id"] = "A"
                store.insert_draft(a)
                b = create_draft_from_url(URL); b["store_client_id"] = "B"
                store.insert_draft(b)
                # 同来源在 A、B 各存一份
                self.assertEqual(store.list_drafts_page(store_client_id="A")[1], 1)
                self.assertEqual(store.list_drafts_page(store_client_id="B")[1], 1)
                self.assertEqual(store.list_drafts_page()[1], 2)  # 不按店=全部
                # 同店同源去重：再插一次 A 不新增
                a2 = create_draft_from_url(URL); a2["store_client_id"] = "A"
                store.insert_draft(a2)
                self.assertEqual(store.list_drafts_page(store_client_id="A")[1], 1)
            finally:
                store.close()

    def test_row_carries_store_and_counts_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            try:
                a = create_draft_from_url(URL); a["store_client_id"] = "A"
                saved = store.insert_draft(a)
                self.assertEqual(saved["store_client_id"], "A")
                self.assertEqual(store.count_by_status(store_client_id="A")["all"], 1)
                self.assertEqual(store.count_by_status(store_client_id="B")["all"], 0)
            finally:
                store.close()


class ExtCollectStoreBindingTest(unittest.TestCase):
    def _app(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import backend.app_service as svc
        importlib.reload(svc)
        return svc

    def test_ext_collect_binds_store_and_list_filters(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                app.store.save_settings({"ozon_client_id": "DEF", "ozon_api_key": "k"})
                # 显式带店 S1
                r1 = app.ext_collect_parsed({
                    "url": "https://www.ozon.ru/product/abc-555/",
                    "data": {"title": "Тест", "store_client_id": "S1"}})
                d1 = app.store.get_draft(r1["created"][0]["id"])
                self.assertEqual(d1["store_client_id"], "S1")
                # 不带店 → 回退默认店 DEF
                r2 = app.ext_collect_parsed({
                    "url": "https://www.ozon.ru/product/xyz-666/",
                    "data": {"title": "Тест2"}})
                d2 = app.store.get_draft(r2["created"][0]["id"])
                self.assertEqual(d2["store_client_id"], "DEF")
                # 列表按店过滤
                self.assertEqual(app.list_drafts(store_client_id="S1")["total"], 1)
                self.assertEqual(app.list_drafts(store_client_id="DEF")["total"], 1)
                self.assertEqual(app.list_drafts()["total"], 2)
            finally:
                app.store.close()


class CopyDraftToStoreTest(unittest.TestCase):
    def _app(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import backend.app_service as svc
        importlib.reload(svc)
        return svc

    def test_copy_clones_content_and_resets_store_fields(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                a = create_draft_from_url(URL)
                a.update({"store_client_id": "A", "ozon_title": "Тест", "category_id": "1",
                          "type_id": "2", "price": "100", "images": ["https://x/a.jpg"],
                          "stock": 9, "warehouse_id": 7, "ozon_product_id": 555,
                          "offer_id": "OF-1", "supplier": "厂A", "cost_cny": 12.5})
                src = app.store.insert_draft(a)
                r = app.copy_draft_to_store(src["id"], "B")
                self.assertTrue(r["ok"])
                clone = r["draft"]
                self.assertNotEqual(clone["id"], src["id"])
                self.assertEqual(clone["store_client_id"], "B")
                # 内容带过去
                self.assertEqual(clone["ozon_title"], "Тест")
                self.assertEqual(clone["offer_id"], "OF-1")
                self.assertEqual(clone["supplier"], "厂A")
                # 店级字段重置
                self.assertEqual(clone["stock"], 0)
                self.assertIsNone(clone["warehouse_id"])
                self.assertIsNone(clone["ozon_product_id"])
                # A、B 各一份
                self.assertEqual(app.list_drafts(store_client_id="A")["total"], 1)
                self.assertEqual(app.list_drafts(store_client_id="B")["total"], 1)
            finally:
                app.store.close()

    def test_copy_rejects_duplicate_and_same_store(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                a = create_draft_from_url(URL); a["store_client_id"] = "A"
                src = app.store.insert_draft(a)
                self.assertFalse(app.copy_draft_to_store(src["id"], "A")["ok"])  # 同店
                app.copy_draft_to_store(src["id"], "B")
                r = app.copy_draft_to_store(src["id"], "B")                       # 重复
                self.assertFalse(r["ok"])
                self.assertIn("已存在", r["error"])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
