from __future__ import annotations

import importlib
import shutil
import tempfile
import unittest
from pathlib import Path

import webui.store as store_mod


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u", "source_offer_id": "1",
        "source_title": "t", "ozon_title": "T", "description": "d",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["x"], "attributes": {}, "status": "draft", "publish_response": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over)
    return d


class TestDeleteDraft(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store_mod.DEFAULT_DB = Path(self.tmp) / "d.db"
        import webui.app_service as svc
        importlib.reload(svc)
        self.svc = svc
        self.app = svc.App()

    def tearDown(self):
        self.app.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_delete_published_does_not_call_ozon(self):
        # 删除草稿只清本地工作台记录；即使已发布，也不能级联删除 Ozon 线上商品。
        called = {"n": 0}
        def _spy(settings, offer_ids):
            called["n"] += 1
            return {"result": [{"offer_id": offer_ids[0]}]}
        self.svc.delete_products = _spy
        d = self.app.store.insert_draft(_draft())
        self.app.store.update_draft(d["id"], {"status": "published"})
        r = self.app.delete(d["id"])
        self.assertTrue(r["deleted"])
        self.assertFalse(r["ozon_deleted"])
        self.assertIsNone(r.get("ozon_error"))
        self.assertEqual(called["n"], 0)
        self.assertIsNone(self.app.store.get_draft(d["id"]))

    def test_delete_published_with_publish_response_does_not_call_ozon(self):
        called = {"n": 0}
        def _spy(settings, offer_ids):
            called["n"] += 1
            return {"result": [{"offer_id": offer_ids[0]}]}
        self.svc.delete_products = _spy
        d = self.app.store.insert_draft(_draft())
        self.app.store.update_draft(d["id"], {"publish_response": {"task_id": 123}})
        r = self.app.delete(d["id"])
        self.assertTrue(r["deleted"])
        self.assertFalse(r["ozon_deleted"])
        self.assertIsNone(r.get("ozon_error"))
        self.assertEqual(called["n"], 0)
        self.assertIsNone(self.app.store.get_draft(d["id"]))

    def test_delete_unpublished_no_ozon_call(self):
        # 未发布草稿同样只删本地
        called = {"n": 0}
        def _spy(settings, offer_ids):
            called["n"] += 1
            return {}
        self.svc.delete_products = _spy
        d = self.app.store.insert_draft(_draft())   # status=draft（其实会被校验成 invalid，但非 published）
        r = self.app.delete(d["id"])
        self.assertTrue(r["deleted"])
        self.assertEqual(called["n"], 0)


if __name__ == "__main__":
    unittest.main()
