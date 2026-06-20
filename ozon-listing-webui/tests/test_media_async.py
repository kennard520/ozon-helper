from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from backend.store import Store


def _draft(**kw):
    from backend.drafts import utc_now_iso
    now = utc_now_iso()
    d = {
        "user_id": 1, "store_client_id": "",
        "source_platform": "ozon", "source_url": kw.get("url", "https://www.ozon.ru/product/x-1/"),
        "source_offer_id": "", "source_title": "t", "purchase_url": "", "purchase_note": "",
        "ozon_title": "t", "description": "", "category_id": "", "type_id": "",
        "brand_id": None, "brand_name": "", "price": "1", "old_price": "",
        "stock": 0, "weight_g": None, "length_mm": None, "width_mm": None, "height_mm": None,
        "cost_cny": None, "video_url": kw.get("video", ""), "local_images_json": None,
        "source": "", "ozon_product_id": None, "offer_id": "", "supplier": "", "source_raw": {},
        "images": kw.get("images", []), "attributes": [],
        "status": "draft", "validation_errors": [], "publish_response": None,
        "created_at": now, "updated_at": now,
    }
    return d


class MediaStatusStoreTest(unittest.TestCase):
    def test_set_and_list_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            saved = store.insert_draft(_draft(url="https://www.ozon.ru/product/a-1/",
                                              images=["https://ir.ozone.ru/a.jpg"]))
            did = saved["id"]
            # 默认建出来是 done（列默认值）；置 pending 后能在待补传列表里查到
            store.set_media_status(did, "pending")
            pend = store.list_pending_media_drafts(1)
            self.assertEqual([p["id"] for p in pend], [did])
            self.assertEqual(pend[0]["images"], ["https://ir.ozone.ru/a.jpg"])
            store.close()

    def test_apply_media_oss_replaces_and_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            saved = store.insert_draft(_draft(url="https://www.ozon.ru/product/b-1/",
                                              images=["https://ir.ozone.ru/a.jpg", "https://ir.ozone.ru/b.jpg"],
                                              video="https://v.ozone.ru/v.mp4"))
            did = saved["id"]
            store.set_media_status(did, "pending")
            store.apply_media_oss(did, {"https://ir.ozone.ru/a.jpg": "https://oss/a.jpg",
                                        "https://v.ozone.ru/v.mp4": "https://oss/v.mp4"})
            d = store.get_draft(did)
            self.assertEqual(d["images"], ["https://oss/a.jpg", "https://ir.ozone.ru/b.jpg"])  # 只换命中的
            self.assertEqual(d["video_url"], "https://oss/v.mp4")
            self.assertEqual(d["media_status"], "done")
            self.assertEqual(store.list_pending_media_drafts(1), [])  # done 后不再 pending
            store.close()


import importlib  # noqa: E402


def _make_app(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import backend.app_service as svc
    importlib.reload(svc)
    app = svc.App()
    app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k"})
    return svc, app


class CollectSetsPendingTest(unittest.TestCase):
    def test_pending_when_has_media(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/m-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                self.assertEqual(app.store.get_draft(did)["media_status"], "pending")
            finally:
                app.store.close()

    def test_done_when_no_media(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/m-2/",
                                              "data": {"title": "t", "images": []}})
                did = res["created"][0]["id"]
                self.assertEqual(app.store.get_draft(did)["media_status"], "done")
            finally:
                app.store.close()


class UpdateDraftMediaTest(unittest.TestCase):
    def test_replaces_and_done(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/u-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                out = app.update_draft_media({"draft_id": did,
                                              "media_map": {"https://ir.ozone.ru/a.jpg": "https://oss/a.jpg"}})
                self.assertTrue(out.get("ok"))
                d = app.store.get_draft(did)
                self.assertEqual(d["images"], ["https://oss/a.jpg"])
                self.assertEqual(d["media_status"], "done")
            finally:
                app.store.close()


class PendingMediaDraftsTest(unittest.TestCase):
    def test_lists_pending(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/p-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                out = app.pending_media_drafts()
                self.assertEqual([d["id"] for d in out["drafts"]], [did])
                self.assertEqual(out["drafts"][0]["images"], ["https://ir.ozone.ru/a.jpg"])
            finally:
                app.store.close()


class PublishBlockedWhenPendingTest(unittest.TestCase):
    def test_publish_rejected_when_pending(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/pub-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]  # media_status=pending
                with self.assertRaises(ValueError):
                    app.publish(did, None)
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
