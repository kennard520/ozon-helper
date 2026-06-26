from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


def _make_app(tmp):
    import webui.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import webui.app_service as svc
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
    from webui.drafts import utc_now_iso
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


class CollectAutoPublishWiringTest(unittest.TestCase):
    def _app(self, tmp, auto):
        svc, app = _make_app(tmp)
        app._auto_match_category = lambda scraped: None
        app._auto_map_safe = lambda did: None
        app.save_settings({"auto_publish": auto})
        calls = []
        app._dispatch_auto_publish = lambda did: calls.append(did)
        return app, calls

    def test_no_media_dispatches_on_collect(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp, auto=True)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-1/",
                                              "data": {"title": "t", "images": []}})
                did = res["created"][0]["id"]
                self.assertEqual(calls, [did])  # 无媒体 → 采集即派发
            finally:
                app.store.close()

    def test_has_media_defers_to_update_draft_media(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp, auto=True)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-2/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                self.assertEqual(calls, [])  # 有媒体（pending）→ 采集时不派发
                app.update_draft_media({"draft_id": did,
                                        "media_map": {"https://ir.ozone.ru/a.jpg": "https://oss/a.jpg"}})
                self.assertEqual(calls, [did])  # 媒体 done 后才派发
            finally:
                app.store.close()

    def test_off_never_dispatches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp, auto=False)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-3/",
                                              "data": {"title": "t", "images": []}})
                did = res["created"][0]["id"]
                app.update_draft_media({"draft_id": did, "media_map": {}})
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_response_carries_auto_publish_flag(self):
        # 插件据此决定采集后弹不弹 webui 编辑器：开着不弹、关着弹
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, _ = self._app(tmp, auto=True)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-flag-on/",
                                              "data": {"title": "t", "images": []}})
                self.assertIs(res["auto_publish"], True)
            finally:
                app.store.close()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, _ = self._app(tmp, auto=False)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-flag-off/",
                                              "data": {"title": "t", "images": []}})
                self.assertIs(res["auto_publish"], False)
            finally:
                app.store.close()

    def test_collect_survives_dispatch_failure(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, _ = self._app(tmp, auto=True)
            try:
                def _boom(_did):
                    raise RuntimeError("boom")
                app._dispatch_auto_publish = _boom
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-4/",
                                              "data": {"title": "t", "images": []}})
                self.assertTrue(res["created"])  # 采集照常返回，best-effort 吞掉
            finally:
                app.store.close()


class MediaOnOssIsDoneTest(unittest.TestCase):
    """插件同步流已把媒体传 OSS → 采集即 done → auto-publish 能触发；
    原始 ir.ozone.ru 链接 → 仍 pending（计划三后台补传后再发）。"""
    def _app(self, tmp):
        svc, app = _make_app(tmp)
        app._auto_match_category = lambda s: None
        app._auto_map_safe = lambda did: None
        app.save_settings({"auto_publish": True, "oss_public_base": "http://oss.test/oss"})
        calls = []
        app._dispatch_auto_publish = lambda did: calls.append(did)
        return app, calls

    def test_oss_media_done_and_dispatches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/oss-1/",
                    "data": {"title": "t", "images": ["http://oss.test/oss/a.jpg"]}})
                did = res["created"][0]["id"]
                self.assertEqual(app.store.get_draft(did)["media_status"], "done")
                self.assertEqual(calls, [did])
            finally:
                app.store.close()

    def test_raw_media_stays_pending(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/raw-1/",
                    "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                self.assertEqual(app.store.get_draft(did)["media_status"], "pending")
                self.assertEqual(calls, [])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
