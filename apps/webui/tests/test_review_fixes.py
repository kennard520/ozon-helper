from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

import webui.store as store_mod


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u", "source_offer_id": "1",
        "source_title": "t", "ozon_title": "Товар", "description": "d",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["x"], "attributes": {}, "status": "draft", "publish_response": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over)
    return d


class TestSaveSettingsAiAutoApply(unittest.TestCase):
    """#1: save_settings 必须持久化 ai_auto_apply（False 也要存得住）。"""
    def _app(self, tmp):
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import webui.app_service as svc
        importlib.reload(svc)
        return svc.App()

    def test_true_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                app.save_settings({"ai_auto_apply": True})
                self.assertTrue(app.store.get_settings().get("ai_auto_apply"))
                self.assertTrue(app.state()["settings"]["ai_auto_apply"])
            finally:
                app.store.close()

    def test_false_persisted_not_dropped(self):
        # 关键：先设 True 再设 False，False 必须真覆盖（不能被 falsy 判断丢弃）
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                app.save_settings({"ai_auto_apply": True})
                app.save_settings({"ai_auto_apply": False})
                self.assertFalse(app.store.get_settings().get("ai_auto_apply"))
            finally:
                app.store.close()


def tearDownModule():
    store_mod.DEFAULT_DB = store_mod.Path(
        store_mod.os.environ.get("OZON_WEBUI_DB")
        or (store_mod.Path(__file__).resolve().parents[1] / "data" / "products.db"))
    import webui.app_service as _svc; importlib.reload(_svc)
    import webui.main as _main; importlib.reload(_main)


if __name__ == "__main__":
    unittest.main()
