import importlib
import tempfile
import unittest
from pathlib import Path


class _FakeOss:
    def configured(self): return True
    def upload_remote(self, url):
        return "https://oss/" + url.rsplit("/", 1)[-1]


class _FailOss:
    def configured(self): return True
    def upload_remote(self, url):
        raise RuntimeError("net down")


class OssPublishTest(unittest.TestCase):
    def _app(self, tmp):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import webui.app_service as svc
        importlib.reload(svc)
        self._svc = svc
        return svc

    def _ready_draft(self, app):
        from webui.drafts import create_draft_from_url
        d = app.store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/123456789012.html"))
        app.store.update_draft(d["id"], {
            "ozon_title": "Тест", "description": "D", "category_id": "1", "type_id": "2",
            # 非 Ozon 源图：触发 OSS 兜底（Ozon 原生 ir.ozone.ru 会跳过，见 test_media_rehost）
            "price": "100", "images": ["https://src/a.jpg"],
            "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
            "source_raw": {"rich_content_json": {"content": [{"blocks": [
                {"img": {"src": "https://src/r.jpg"}}]}]}},
        })
        return d["id"]

    def test_publish_blocked_when_oss_not_configured(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k",
                                         "rub_cny": 0.1, "contract_currency": "CNY"})
                did = self._ready_draft(app)
                r = app.publish(did)
                self.assertFalse(r["published"])
                self.assertTrue(any("OSS" in e for e in r["errors"]))
            finally:
                app.store.close()

    def test_publish_rehosts_to_oss(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                app.store.save_settings({
                    "ozon_client_id": "1", "ozon_api_key": "k", "rub_cny": 0.1, "contract_currency": "CNY",
                    "oss_endpoint": "oss-cn-hangzhou.aliyuncs.com", "oss_bucket": "b",
                    "oss_access_key_id": "ak", "oss_access_key_secret": "sk"})
                did = self._ready_draft(app)
                app._category_attrs = lambda c, t: []  # 跳过类目必填校验(网络依赖)
                svc.OssClient = lambda s, **kw: _FakeOss()
                sent = {}
                svc.publish_items = lambda settings, items: sent.update(item=items[0]) or {"result": {"task_id": 0}}
                r = app.publish(did)
                item = sent["item"]
                self.assertTrue(all(u.startswith("https://oss/") for u in item["images"]))
                rich = next(a for a in item["attributes"] if int(a["id"]) == 11254)
                self.assertIn("https://oss/", rich["values"][0]["value"])
            finally:
                app.store.close()

    def test_rehost_failure_surfaces_warning(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                app.store.save_settings({
                    "ozon_client_id": "1", "ozon_api_key": "k", "rub_cny": 0.1, "contract_currency": "CNY",
                    "oss_endpoint": "e", "oss_bucket": "b", "oss_access_key_id": "ak", "oss_access_key_secret": "sk"})
                did = self._ready_draft(app)
                app._category_attrs = lambda c, t: []
                svc.OssClient = lambda s, **kw: _FailOss()      # 所有上传失败
                svc.publish_items = lambda settings, items: {"result": {"task_id": 0}}
                r = app.publish(did)
                # 失败不阻断发布，但 warnings 里要提示"未能上传到 OSS"
                self.assertTrue(any("OSS" in w for w in (r.get("warnings") or [])))
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
