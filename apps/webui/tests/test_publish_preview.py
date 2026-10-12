"""Tests for publish_preview: side-effect-free preview of Ozon publish payload."""
from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

import webui.store as _store_mod

_ORIG_DEFAULT_DB = _store_mod.DEFAULT_DB

_OSS_SETTINGS = {"oss_endpoint": "e", "oss_bucket": "b",
                 "oss_access_key_id": "ak", "oss_access_key_secret": "sk"}


class _FakeOss:
    """OSS 已配置 + URL/本地路径重写到 https://oss/<name>（不依赖 oss2/网络）。"""
    def configured(self): return True
    def upload_remote(self, url):
        return "https://oss/" + str(url).rsplit("/", 1)[-1]


def _stub_oss(svc):
    """让 publish 的 OSS rehost 走假 OSS（发布前媒体托管校验通过）。"""
    svc.OssClient = lambda settings, **kw: _FakeOss()


class _FailingOss:
    def configured(self): return True
    def upload_remote(self, url):
        raise RuntimeError("upload failed")


def _stub_failing_oss(svc):
    svc.OssClient = lambda settings, **kw: _FailingOss()


class _ProxyHttpOss:
    def configured(self): return True
    def upload_remote(self, url):
        return "http://8.152.196.119:8585/oss/ozon-media/" + str(url).rsplit("/", 1)[-1]


def _stub_proxy_http_oss(svc):
    svc.OssClient = lambda settings, **kw: _ProxyHttpOss()


def _close_app(app) -> None:
    app.store.close()
    _store_mod.DEFAULT_DB = _ORIG_DEFAULT_DB


def _make_app(tmp: str):
    """创建一个带临时 DB 的 App 实例。"""
    import webui.store as store_mod

    store_mod.DEFAULT_DB = Path(tmp) / "prev.db"
    import webui.app_service as svc

    importlib.reload(svc)
    app = svc.App()
    app.store.save_settings(
        {"ozon_client_id": "4891171", "ozon_api_key": "K", "rub_cny": 0.0927}
    )
    return app


def _draft(app, **extra) -> dict:
    from webui.drafts import create_draft_from_url

    d = create_draft_from_url("https://detail.1688.com/offer/99.html")
    d.update(
        {
            "ozon_title": "Товар тестовый",
            "description": "Описание товара",
            "price": "1000",
            "old_price": "1200",
            "category_id": "17038048",
            "type_id": "94765",
            "weight_g": 500,
            "length_mm": 200,
            "width_mm": 150,
            "height_mm": 100,
            "source_platform": "1688",
            "images": [
                "https://cbu01.alicdn.com/img/a.jpg",
                "https://cbu01.alicdn.com/img/b.jpg",
            ],
        }
    )
    d.update(extra)
    saved = app.store.insert_draft(d)
    # 语义变更:采集图→素材(in_gallery=0),发布/预览需要图集图;
    # 用 add_draft_image 把素材图注入图集(source="generated" 自动 in_gallery=1)
    for url in ["https://cbu01.alicdn.com/img/a.jpg", "https://cbu01.alicdn.com/img/b.jpg"]:
        app.store.add_draft_image(saved["id"], url, type="白底主图", source="generated")
    return app.store.get_draft(saved["id"])


class PublishPreviewOkTest(unittest.TestCase):
    def test_preview_returns_ok_with_correct_summary(self) -> None:
        """有效草稿 preview 返回 ok=True，摘要含正确转换后价格和字段。"""
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp)
            # 跳过类目必填校验（网络依赖）
            app._category_attrs = lambda c, t: []
            draft = _draft(app)
            result = app.publish_preview(draft["id"])

            self.assertTrue(result["ok"], f"Expected ok=True, got errors: {result.get('errors')}")
            self.assertEqual(result["errors"], [])
            s = result["summary"]
            self.assertIsNotNone(s)
            # 内部价已是 CNY，合同币种 CNY → 不换算，原样发
            self.assertEqual(s["price"], "1000")
            self.assertEqual(s["old_price"], "1200")
            self.assertEqual(s["currency_code"], "CNY")
            self.assertEqual(s["images_count"], 2)
            # 两张普通图 → attributes 里的图片属性数量可能包含其他，只验 images_count
            self.assertFalse(s["has_video"])
            # category_id / type_id 要能读出来（整数或字符串，不为空）
            self.assertTrue(s["category_id"])
            self.assertTrue(s["type_id"])
            _close_app(app)

    def test_preview_with_video_reports_has_video_true(self) -> None:
        """草稿有视频 URL → summary.has_video == True。"""
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app, video_url="https://cloud.video.taobao.com/x.mp4")
            result = app.publish_preview(draft["id"])
            self.assertTrue(result["ok"])
            self.assertTrue(result["summary"]["has_video"])
            _close_app(app)

    def test_preview_warns_and_marks_low_res_wb_video_skipped(self) -> None:
        """WB 360p 视频会被 Ozon 拒绝，预览应提示且发布 payload 不带视频。"""
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(
                app,
                source_platform="wb",
                video_url="http://8.152.196.119:8585/oss/ozon-media/rehosted.mp4",
                source_raw={
                    "video_url": "https://videonme-basket-11.wbbasket.ru/vol129/part90154/901541649/mp4/360p/1.mp4",
                },
            )
            result = app.publish_preview(draft["id"])

            self.assertTrue(result["ok"])
            self.assertFalse(result["summary"]["has_video"])
            self.assertTrue(any("视频" in w and "跳过" in w for w in result["warnings"]))
            _close_app(app)

    def test_preview_surfaces_ozon_variant_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp)
            app._category_attrs = lambda c, t: []
            warning = "该 Ozon 商品属于包含 3 个 SKU 的变体组；本次仅导入当前 SKU。"
            draft = _draft(
                app,
                source_platform="ozon",
                source_raw={"ozon_sync": {"variant_warning": warning}},
            )

            result = app.publish_preview(draft["id"])

            self.assertTrue(result["ok"])
            self.assertIn(warning, result["warnings"])
            _close_app(app)


class PublishPreviewSideEffectFreeTest(unittest.TestCase):
    def test_preview_does_not_write_status_on_error(self) -> None:
        """技术性错误（RUB 无汇率）时 preview 不把草稿 status 改成 invalid。"""
        with tempfile.TemporaryDirectory() as tmp:
            import webui.store as store_mod

            store_mod.DEFAULT_DB = Path(tmp) / "se.db"
            import webui.app_service as svc

            importlib.reload(svc)
            app = svc.App()
            # RUB 合同币种故意不配 rub_cny → 汇率拦截
            app.store.save_settings(
                {"ozon_client_id": "X", "ozon_api_key": "K", "contract_currency": "RUB"}
            )
            app._category_attrs = lambda c, t: []
            draft = _draft(app)
            original_status = draft.get("status")

            result = app.publish_preview(draft["id"])

            # 错误被返回
            self.assertFalse(result["ok"])
            self.assertTrue(any("汇率" in e for e in result["errors"]))

            # DB 里的草稿 status 未被改写
            refreshed = app.store.get_draft(draft["id"])
            self.assertEqual(refreshed.get("status"), original_status,
                             "preview must not persist status changes to the draft")
            _close_app(app)

    def test_preview_does_not_call_publish_items(self) -> None:
        """preview 不应调用 publish_items（外部写）。"""
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = _make_app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app)

            called = {"n": 0}
            orig = svc.publish_items

            def fake_publish(settings, items):
                called["n"] += 1
                return {"result": {"task_id": 0}}

            svc.publish_items = fake_publish
            try:
                app.publish_preview(draft["id"])
                self.assertEqual(called["n"], 0, "publish_items must NOT be called during preview")
            finally:
                svc.publish_items = orig
                _close_app(app)


class PublishAfterRefactorTest(unittest.TestCase):
    """确认 _validate_and_build_item 重构后 publish 行为不变。"""

    def _app(self, tmp):
        import webui.store as store_mod

        store_mod.DEFAULT_DB = Path(tmp) / "pub2.db"
        import webui.app_service as svc

        importlib.reload(svc)
        app = svc.App()
        app.store.save_settings(
            {"ozon_client_id": "4891171", "ozon_api_key": "K", "rub_cny": 0.0927, **_OSS_SETTINGS}
        )
        _stub_oss(svc)
        return app

    def test_publish_still_blocks_on_missing_rub_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import webui.store as store_mod

            store_mod.DEFAULT_DB = Path(tmp) / "pr2.db"
            import webui.app_service as svc

            importlib.reload(svc)
            app = svc.App()
            # 配 OSS（让 OSS 硬拦先过），RUB 合同币种故意不配 rub_cny → 汇率拦截
            app.store.save_settings(
                {"ozon_client_id": "X", "ozon_api_key": "K", "contract_currency": "RUB", **_OSS_SETTINGS}
            )
            _stub_oss(svc)
            app._category_attrs = lambda c, t: []
            draft = _draft(app)
            r = app.publish(draft["id"])
            self.assertFalse(r["published"])
            self.assertTrue(any("汇率" in e for e in r["errors"]))
            # publish 应写 status=invalid
            self.assertEqual(r["draft"]["status"], "invalid")
            task = next(t for t in app.store.latest_task_runs_for_draft(draft["id"]) if t["task_type"] == "publish")
            self.assertEqual(task["status"], "failed")
            self.assertTrue(task["error"])
            _close_app(app)

    def test_publish_still_calls_publish_items_on_success(self) -> None:
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app)

            captured = {}

            def fake_publish(settings, items):
                captured["items"] = items
                return {"result": {"task_id": 0}}

            orig = svc.publish_items
            svc.publish_items = fake_publish
            try:
                r = app.publish(draft["id"])
                # publish_items 被调用了
                self.assertIn("items", captured)
                item = captured["items"][0]
                # 内部价已是 CNY，合同币种 CNY → 原样发，不换算
                self.assertEqual(item["price"], "1000")
                self.assertEqual(item["currency_code"], "CNY")
            finally:
                svc.publish_items = orig
                _close_app(app)

    def test_publish_surfaces_variant_warning_and_still_submits_single_item(self) -> None:
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: []
            warning = "该 Ozon 商品属于包含 3 个 SKU 的变体组；本次仅导入当前 SKU。"
            draft = _draft(
                app,
                source_platform="ozon",
                source_raw={"ozon_sync": {"variant_warning": warning}},
            )
            called = {"n": 0}
            original_publish = svc.publish_items

            def fake_publish(settings, items):
                called["n"] += 1
                return {"result": {"task_id": 0}}

            svc.publish_items = fake_publish
            try:
                result = app.publish(draft["id"])
                self.assertEqual(called["n"], 1)
                self.assertIn(warning, result["warnings"])
            finally:
                svc.publish_items = original_publish
                _close_app(app)

    def test_publish_stops_when_media_rehost_fails(self) -> None:
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app)
            _stub_failing_oss(svc)

            called = {"n": 0}
            orig = svc.publish_items

            def fake_publish(settings, items):
                called["n"] += 1
                return {"result": {"task_id": 0}}

            svc.publish_items = fake_publish
            try:
                r = app.publish(draft["id"])
                self.assertFalse(r["published"])
                self.assertEqual(called["n"], 0)
                self.assertTrue(any("OSS" in e for e in r["errors"]))
                self.assertEqual(r["draft"]["status"], "invalid")
            finally:
                svc.publish_items = orig
                _close_app(app)

    def test_publish_stops_when_final_media_url_is_not_https(self) -> None:
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app)
            _stub_proxy_http_oss(svc)

            called = {"n": 0}
            orig = svc.publish_items

            def fake_publish(settings, items):
                called["n"] += 1
                return {"result": {"task_id": 0}}

            svc.publish_items = fake_publish
            try:
                r = app.publish(draft["id"])
                self.assertFalse(r["published"])
                self.assertEqual(called["n"], 0)
                self.assertTrue(any("HTTPS" in e or "URL" in e for e in r["errors"]))
                self.assertEqual(r["draft"]["status"], "invalid")
            finally:
                svc.publish_items = orig
                _close_app(app)

    def test_publish_allows_validation_risks_and_sends_to_ozon(self) -> None:
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app, ozon_title="English title without Cyrillic")

            preview = app.publish_preview(draft["id"])
            self.assertTrue(preview["ok"])
            self.assertTrue(any("标题" in w or "title" in w.lower() for w in preview["warnings"]))
            self.assertTrue(preview["checks"])

            captured = {}
            orig = svc.publish_items
            def fake_publish(settings, items):
                captured["items"] = items
                return {"result": {"task_id": 0}}
            svc.publish_items = fake_publish
            try:
                r = app.publish(draft["id"])
                self.assertIn("items", captured)
                self.assertTrue(any("标题" in w or "title" in w.lower() for w in r.get("warnings", [])))
            finally:
                svc.publish_items = orig
                _close_app(app)


    def test_publish_task_failed_when_ozon_rejects(self) -> None:
        import webui.app_service as svc

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: []
            draft = _draft(app)
            orig = svc.publish_items
            svc.publish_items = lambda settings, items: (_ for _ in ()).throw(RuntimeError("bad media url"))
            try:
                r = app.publish(draft["id"])
                self.assertFalse(r["published"])
                task = next(t for t in app.store.latest_task_runs_for_draft(draft["id"]) if t["task_type"] == "publish")
                self.assertEqual(task["status"], "failed")
                self.assertIn("bad media url", task["error"])
            finally:
                svc.publish_items = orig
                _close_app(app)


class PublishPreviewRouteTest(unittest.TestCase):
    def test_route_returns_404_for_missing_draft(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            import webui.store as store_mod

            store_mod.DEFAULT_DB = Path(tmp) / "rt.db"
            import webui.app_service as svc
            import webui.main as main_mod

            importlib.reload(svc)
            importlib.reload(main_mod)
            from fastapi.testclient import TestClient

            with TestClient(main_mod.app) as client:
                r = client.get("/api/drafts/9999/publish-preview")
            self.assertEqual(r.status_code, 404)
            _close_app(main_mod.APP)

    def test_route_returns_200_for_valid_draft(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            import webui.store as store_mod

            store_mod.DEFAULT_DB = Path(tmp) / "rt2.db"
            import webui.app_service as svc
            import webui.main as main_mod

            importlib.reload(svc)
            importlib.reload(main_mod)
            from fastapi.testclient import TestClient

            main_mod.APP.store.save_settings(
                {"ozon_client_id": "4891171", "ozon_api_key": "K", "rub_cny": 0.0927}
            )
            main_mod.APP._category_attrs = lambda c, t: []
            draft = _draft(main_mod.APP)
            with TestClient(main_mod.app) as client:
                r = client.get(f"/api/drafts/{draft['id']}/publish-preview")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertIn("ok", data)
            self.assertIn("summary", data)
            _close_app(main_mod.APP)


class MissingAttrIsWarningTest(unittest.TestCase):
    """缺类目必填属性 → 警告(不拦)，仍可发布。"""

    def _app(self, tmp):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "warn.db"
        import webui.app_service as svc
        importlib.reload(svc)
        app = svc.App()
        app.store.save_settings(
            {"ozon_client_id": "4891171", "ozon_api_key": "K", "rub_cny": 0.0927, **_OSS_SETTINGS}
        )
        _stub_oss(svc)
        return app

    def test_preview_ok_with_warning_when_required_attr_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            # 类目要求一个必填属性 id=85(Бренд)，草稿没填它
            app._category_attrs = lambda c, t: [{"id": 85, "name": "Бренд", "is_required": True}]
            draft = _draft(app)
            result = app.publish_preview(draft["id"])
            self.assertTrue(result["ok"])                         # 不再被拦
            self.assertEqual(result["errors"], [])
            self.assertTrue(any("Бренд" in w for w in result["warnings"]))
            self.assertIsNotNone(result["summary"])
            _close_app(app)

    def test_publish_proceeds_despite_missing_attr(self) -> None:
        import webui.app_service as svc
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app._category_attrs = lambda c, t: [{"id": 85, "name": "Бренд", "is_required": True}]
            draft = _draft(app)
            orig = svc.publish_items
            svc.publish_items = lambda settings, items: {"result": {"task_id": 0}}
            try:
                r = app.publish(draft["id"])
                self.assertNotIn("缺必填属性", " ".join(r.get("errors", [])))  # 没因缺属性被拦
                self.assertTrue(any("Бренд" in w for w in r.get("warnings", [])))
            finally:
                svc.publish_items = orig
                _close_app(app)
