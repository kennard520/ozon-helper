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


def _draft(**kw):
    from backend.drafts import utc_now_iso
    now = utc_now_iso()
    d = {
        "user_id": 1, "store_client_id": "",
        "source_platform": "ozon", "source_url": kw.get("url", "https://www.ozon.ru/product/g-1/"),
        "source_offer_id": "", "source_title": "t", "purchase_url": "", "purchase_note": "",
        "ozon_title": "t", "description": "", "category_id": "", "type_id": "",
        "brand_id": None, "brand_name": "", "price": "1", "old_price": "",
        "stock": 0, "weight_g": None, "length_mm": None, "width_mm": None, "height_mm": None,
        "cost_cny": None, "video_url": "", "local_images_json": None,
        "source": "", "ozon_product_id": None, "offer_id": "", "supplier": "", "source_raw": {},
        "images": kw.get("images", []), "attributes": [],
        "status": kw.get("status", "draft"), "validation_errors": [], "publish_response": None,
        "created_at": now, "updated_at": now,
    }
    return d


class MaybeAutoPublishGuardTest(unittest.TestCase):
    def _setup(self, tmp, *, auto, status="draft", media="done", images=None):
        svc, app = _make_app(tmp)
        app.save_settings({"auto_publish": auto})
        saved = app.store.insert_draft(_draft(images=images or []))
        # insert_draft 对缺必填的草稿会强制 status=invalid；要测 published 守卫得显式置
        if status != "draft":
            app.store.update_draft(saved["id"], {"status": status})
        if media != "done":
            app.store.set_media_status(saved["id"], media)
        calls = []
        app._dispatch_auto_publish = lambda did: calls.append(did)
        return app, saved["id"], calls

    def test_on_and_ready_dispatches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=True)
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [did])
            finally:
                app.store.close()

    def test_off_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=False)
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_media_pending_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=True, media="pending",
                                          images=["https://ir.ozone.ru/a.jpg"])
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_already_published_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=True, status="published")
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_dispatch_raise_is_swallowed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, _ = self._setup(tmp, auto=True)
            try:
                def _boom(_did):
                    raise RuntimeError("boom")
                app._dispatch_auto_publish = _boom
                app._maybe_auto_publish(did)  # 不抛错即通过
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
