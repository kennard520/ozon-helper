from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import webui.store as store_mod


class _DbBase(unittest.TestCase):
    """每个用例一个临时 db，不污染主库。"""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "t.db"
        self._old = store_mod.DEFAULT_DB
        store_mod.DEFAULT_DB = self.tmp

    def tearDown(self):
        store_mod.DEFAULT_DB = self._old


class TestSettingsForStore(_DbBase):
    def _app(self):
        import webui.app_service as app_service
        return app_service.App()

    def test_main_store_when_blank(self):
        app = self._app()
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1"})
        s = app._settings_for_store("")
        self.assertEqual(s["ozon_client_id"], "111")
        self.assertEqual(s["ozon_api_key"], "K1")

    def test_main_store_when_same_id(self):
        app = self._app()
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1"})
        self.assertEqual(app._settings_for_store("111")["ozon_api_key"], "K1")

    def test_extra_store_overrides_keys(self):
        app = self._app()
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1",
                                 "ozon_stores": [{"name": "店2", "client_id": "222", "api_key": "K2"}],
                                 "rub_cny": 0.5})
        s = app._settings_for_store("222")
        self.assertEqual(s["ozon_client_id"], "222")
        self.assertEqual(s["ozon_api_key"], "K2")
        self.assertEqual(s["rub_cny"], 0.5)   # 全局字段保留

    def test_unknown_store_raises(self):
        app = self._app()
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1"})
        with self.assertRaises(ValueError):
            app._settings_for_store("999")


class TestSettingsStoresCrud(_DbBase):
    def _app(self):
        import webui.app_service as app_service
        return app_service.App()

    def test_save_and_redacted_state(self):
        app = self._app()
        app.save_settings({"ozon_stores": [
            {"name": "店2", "client_id": "222", "api_key": "SECRET"},
            {"name": "", "client_id": "333", "api_key": "x"},   # 缺 name → 跳过
        ]})
        st = app.state()["settings"]["ozon_stores"]
        self.assertEqual(len(st), 1)
        self.assertEqual(st[0]["client_id"], "222")
        self.assertTrue(st[0]["api_key_saved"])
        self.assertNotIn("api_key", st[0])                       # 不回传完整 key

    def test_edit_name_keeps_existing_key(self):
        app = self._app()
        app.save_settings({"ozon_stores": [{"name": "店2", "client_id": "222", "api_key": "SECRET"}]})
        # 重存时不带 api_key（前端只改名）→ 保留原 key
        app.save_settings({"ozon_stores": [{"name": "店二", "client_id": "222"}]})
        self.assertEqual(app.store.get_settings()["ozon_stores"][0]["api_key"], "SECRET")

    def test_last_publish_store_roundtrip(self):
        app = self._app()
        app.save_settings({"last_publish_store": "222"})
        self.assertEqual(app.state()["settings"]["last_publish_store"], "222")


class TestValidateUsesStore(_DbBase):
    def _app(self):
        import webui.app_service as app_service
        return app_service.App()

    def test_validate_uses_target_store_rate(self):
        app = self._app()
        # 主店有汇率，目标店共享全局 rub_cny → 校验不应因汇率拦截
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1", "rub_cny": 0.5,
                                 "contract_currency": "CNY",
                                 "ozon_stores": [{"name": "店2", "client_id": "222", "api_key": "K2"}]})
        app._category_attrs = lambda c, t: []  # 跳过类目必填校验(网络依赖)
        draft = {"images": ["https://ir.ozone.ru/a.jpg"], "video_url": "",
                 "ozon_title": "Тест", "description": "D", "category_id": "1", "type_id": "2",
                 "price": "10", "stock": 1, "weight_g": 100,
                 "length_mm": 10, "width_mm": 10, "height_mm": 10}
        store_settings = app._settings_for_store("222")
        errors, _warnings, item = app._validate_and_build_item(draft, store_settings)
        # 目标店带全局汇率 → 不报汇率错；item 正常构建
        self.assertEqual(errors, [])
        self.assertIsNotNone(item)


class TestPublishTargetsStore(_DbBase):
    def _app(self):
        import webui.app_service as app_service
        return app_service.App()

    def _valid_draft(self, app):
        from webui.drafts import create_draft_from_url
        d = create_draft_from_url("https://www.wildberries.ru/catalog/1/detail.aspx")
        d.update({
            "source_platform": "wb", "ozon_title": "Товар", "description": "Описание",
            "category_id": "1", "type_id": "2", "price": "10", "old_price": "",
            "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
            "images": ["https://ir.ozone.ru/a.jpg"],
        })
        saved = app.store.insert_draft(d)
        # 语义变更:采集图→素材(in_gallery=0),发布需要图集图;add generated 图集图
        app.store.add_draft_image(saved["id"], "https://ir.ozone.ru/a.jpg",
                                  type="白底主图", source="generated")
        return app.store.get_draft(saved["id"])

    def test_publish_uses_target_store_and_records_last(self):
        import webui.app_service as app_service
        app = self._app()
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1", "rub_cny": 0.5,
                                 "contract_currency": "CNY",
                                 "oss_endpoint": "e", "oss_bucket": "b",
                                 "oss_access_key_id": "ak", "oss_access_key_secret": "sk",
                                 "ozon_stores": [{"name": "店2", "client_id": "222", "api_key": "K2"}]})
        d = self._valid_draft(app)
        # 跳过类目必填属性校验（网络依赖）
        app._category_attrs = lambda c, t: []
        # 发布前媒体 rehost 到 OSS：注入假 OSS（不依赖 oss2/网络）
        app_service.OssClient = lambda settings, **kw: type(
            "F", (), {"configured": lambda self: True,
                      "upload_remote": lambda self, u: "https://oss/" + str(u).rsplit("/", 1)[-1]})()
        captured = {}
        # mock publish_items / get_import_info（模块级符号）
        app_service.publish_items = lambda settings, items: (captured.update(cid=settings.get("ozon_client_id")) or
                                                             {"result": {"task_id": None}})
        res = app.publish(d["id"], store_client_id="222")
        self.assertEqual(captured["cid"], "222")                       # 发到了目标店
        self.assertEqual(app.store.get_settings()["last_publish_store"], "222")
        self.assertEqual(res["draft"]["publish_response"]["store_client_id"], "222")


class TestExtPingExposesRate(_DbBase):
    """插件靠 ext_ping 拿汇率(rub_cny)，在插件侧把卢布换算成人民币再回传。"""
    def _app(self):
        import webui.app_service as app_service
        return app_service.App()

    def test_ping_returns_configured_rate(self):
        app = self._app()
        app.store.save_settings({"rub_cny": 0.0784})
        p = app.ext_ping()
        self.assertTrue(p["ok"])
        self.assertEqual(p["rub_cny"], 0.0784)

    def test_ping_rate_none_when_unset(self):
        app = self._app()
        self.assertIsNone(app.ext_ping()["rub_cny"])

    def test_ping_rate_none_when_garbage(self):
        app = self._app()
        app.store.save_settings({"rub_cny": "abc"})
        self.assertIsNone(app.ext_ping()["rub_cny"])




class TestListDraftsDefaultsToDefaultStore(_DbBase):
    """不带 store_client_id 时回退默认店(settings.ozon_client_id)，避免草稿忽有忽无。"""
    def _app(self):
        import webui.app_service as app_service
        return app_service.App()

    def _draft(self, app, store_cid):
        from webui.drafts import create_draft_from_url
        d = create_draft_from_url("https://www.ozon.ru/product/x-" + store_cid + "-1/")
        d.update({"ozon_title": "t", "store_client_id": store_cid})
        return app.store.insert_draft(d)

    def test_no_store_defaults_to_settings_default_store(self):
        app = self._app()
        app.store.save_settings({"ozon_client_id": "111", "ozon_api_key": "K1"})
        self._draft(app, "111")
        self._draft(app, "222")
        # 不带 store → 回退默认店 111，只看 111 的草稿
        res = app.list_drafts()
        self.assertEqual(res["total"], 1)
        self.assertEqual([d["store_client_id"] for d in res["drafts"]], ["111"])
        # 明确带 222 → 只看 222
        res2 = app.list_drafts(store_client_id="222")
        self.assertEqual(res2["total"], 1)
        self.assertEqual([d["store_client_id"] for d in res2["drafts"]], ["222"])

    def test_no_default_store_falls_back_to_all(self):
        app = self._app()  # 没配 ozon_client_id
        self._draft(app, "111")
        self._draft(app, "222")
        res = app.list_drafts()  # 没默认店 → 不过滤，全看到
        self.assertEqual(res["total"], 2)
