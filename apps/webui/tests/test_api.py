from __future__ import annotations

import unittest


class AppServiceImportTest(unittest.TestCase):
    def test_app_class_importable_from_backend(self) -> None:
        from webui.app_service import App  # noqa: PLC0415
        self.assertTrue(hasattr(App, "state"))
        self.assertTrue(hasattr(App, "list_drafts"))
        self.assertTrue(hasattr(App, "publish"))


class ApiGetTest(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from webui.main import app  # noqa: PLC0415
        return TestClient(app)

    def test_state_endpoint(self) -> None:
        resp = self._client().get("/api/state")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("settings", body)
        self.assertIn("status", body)

    def test_drafts_endpoint(self) -> None:
        resp = self._client().get("/api/drafts")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("drafts", resp.json())


class ApiWriteTest(unittest.TestCase):
    def _client(self, tmp):
        import importlib  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415
        # 把默认 DB 指到临时文件
        store_mod.DEFAULT_DB = Path(tmp) / "api.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def test_settings_roundtrip(self) -> None:
        import tempfile  # noqa: PLC0415

        import webui.main as main_mod  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                resp = client.post("/api/settings", json={"ozon_client_id": "C-1"})
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["settings"]["ozon_client_id"], "C-1")
            finally:
                main_mod.APP.store.close()  # 关连接，否则 Windows 删不掉临时库

    def test_patch_draft(self) -> None:
        import tempfile  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            # 先插一条草稿
            import webui.main as main_mod  # noqa: PLC0415
            from webui.drafts import create_draft_from_url  # noqa: PLC0415
            try:
                d = main_mod.APP.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
                )
                resp = client.patch(f"/api/drafts/{d['id']}", json={"purchase_note": "厂家B"})
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["draft"]["purchase_note"], "厂家B")
            finally:
                main_mod.APP.store.close()


class MediaRouteTest(unittest.TestCase):
    def test_media_serves_local_image(self) -> None:
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.media as media_mod  # noqa: PLC0415
        from webui.main import app  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp)
            key_dir = Path(tmp) / "draft-1"
            key_dir.mkdir(parents=True)
            (key_dir / "00.jpg").write_bytes(b"\xff\xd8\xff\xe0jpegbytes")
            client = TestClient(app)
            ok = client.get("/media/draft-1/00.jpg")
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.content, b"\xff\xd8\xff\xe0jpegbytes")
            # 越界 / 不存在 → 404
            self.assertEqual(client.get("/media/../secret.txt").status_code, 404)
            self.assertEqual(client.get("/media/draft-1/nope.jpg").status_code, 404)


class PublishLocalizationGuardTest(unittest.TestCase):
    def _app(self, tmp):
        import importlib  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "guard.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        return svc.App()

    def _valid_1688_draft(self) -> dict:
        from webui.drafts import create_draft_from_url  # noqa: PLC0415
        d = create_draft_from_url("https://detail.1688.com/offer/998877665544.html")
        d.update({
            "ozon_title": "纯棉收纳箱 大号",  # 仍是中文 → 未本地化
            "description": "高品质家居收纳",
            "category_id": "17027949", "type_id": "94765",
            "price": "1000", "old_price": "0", "stock": 5,
            "images": ["https://img/1.jpg"],
            "weight_g": 500, "length_mm": 100, "width_mm": 100, "height_mm": 100,
        })
        return d

    def test_chinese_1688_draft_blocked(self) -> None:
        import tempfile  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                # 配 OSS+汇率（让 OSS 硬拦先过），用假 OSS 不依赖网络；中文未本地化应仍拦
                import webui.app_service as svc  # noqa: PLC0415
                app.store.save_settings({"rub_cny": 0.0927, "contract_currency": "CNY",
                                         "oss_endpoint": "e", "oss_bucket": "b",
                                         "oss_access_key_id": "ak", "oss_access_key_secret": "sk"})
                svc.OssClient = lambda settings, **kw: type(
                    "F", (), {"configured": lambda self: True,
                              "upload_remote": lambda self, u: "https://oss/x.jpg"})()
                app._category_attrs = lambda c, t: []  # 跳过类目必填校验(网络依赖)
                inserted = app.store.insert_draft(self._valid_1688_draft())
                # 把 store 校验后的字段补成有效（insert 会按 validate 标 invalid，update 修正）
                d = app.store.update_draft(inserted["id"], self._valid_1688_draft())
                result = app.publish(d["id"])
                self.assertFalse(result["published"])
                self.assertTrue(any("未本地化" in e for e in result["errors"]),
                                msg=f"errors={result['errors']}")
            finally:
                app.store.close()  # 关连接，否则 Windows 删不掉临时库


class FrontendServeTest(unittest.TestCase):
    """`/` 托管 Vue dist/index.html；dist 未构建时给出 503 构建提示。"""

    def _client_with_dist(self, dist_dir):
        import importlib  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        svc.FRONTEND_DIST = Path(dist_dir)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def tearDown(self) -> None:
        # 还原 backend.main：避免把指向临时目录的 StaticFiles 挂载泄漏给后续用例
        import importlib  # noqa: PLC0415

        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)

    def test_serves_dist_index_when_present(self) -> None:
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "index.html").write_text(
                "<!doctype html><html><body>VUE_DIST_SENTINEL</body></html>",
                encoding="utf-8",
            )
            client = self._client_with_dist(tmp)
            resp = client.get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("VUE_DIST_SENTINEL", resp.text)

    def test_returns_build_hint_when_dist_absent(self) -> None:
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            # 指向一个不含 index.html 的空目录 → 503 构建提示（不再回退 static/）
            client = self._client_with_dist(Path(tmp) / "nope")
            resp = client.get("/")
            self.assertEqual(resp.status_code, 503)
            self.assertIn("npm run build", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
