from __future__ import annotations
import importlib
import tempfile
import unittest
from pathlib import Path


def _make_app(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import backend.app_service as svc
    importlib.reload(svc)
    app = svc.App()
    app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k"})
    return svc, app


class SettingsRoundTripTest(unittest.TestCase):
    def test_auto_publish_persists_and_exposed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                # 默认未设置 → state 暴露为 False
                self.assertFalse(app.state()["settings"]["auto_publish"])
                # 存 True → 持久化 + state 回传 True
                app.save_settings({"auto_publish": True})
                self.assertTrue(app.store.get_settings().get("auto_publish"))
                self.assertTrue(app.state()["settings"]["auto_publish"])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
