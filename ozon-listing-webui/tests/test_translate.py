from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from backend.translate import GlossaryEngine, ManualEngine, get_engine, _chat_completions_url


class TranslateEngineTest(unittest.TestCase):
    def test_manual_passthrough(self):
        eng = get_engine("manual", {})
        self.assertIsInstance(eng, ManualEngine)
        self.assertEqual(eng.translate("收纳箱"), "收纳箱")  # 占位：原样返回（仍需人工/换引擎）

    def test_glossary_replaces_known_terms(self):
        eng = get_engine("glossary", {})
        self.assertIsInstance(eng, GlossaryEngine)
        out = eng.translate("收纳箱")
        self.assertNotEqual(out, "收纳箱")  # 命中词典 → 被替换成俄文
        self.assertNotIn("收纳", out)

    def test_unknown_engine_falls_back_manual(self):
        self.assertIsInstance(get_engine("nope", {}), ManualEngine)

    def test_remote_without_key_raises(self):
        eng = get_engine("remote", {})  # 没配 key
        with self.assertRaises(Exception):
            eng.translate("收纳箱")

    def test_remote_empty_text_returns_empty_without_calling_api(self):
        # 有 key/base 但文本为空 → 直接返回 ""，绝不调 API（否则模型回"请提供内容"被当译文）
        eng = get_engine("remote", {
            "translate_api_base": "https://api.deepseek.com",
            "translate_api_key": "sk-x", "translate_model": "deepseek-v4-flash",
        })
        self.assertEqual(eng.translate(""), "")
        self.assertEqual(eng.translate("   "), "")

    def test_chat_url_always_v1(self):
        # 统一打 /v1/chat/completions：少 /v1 会打到网关首页被 Cloudflare 403（Agnes 的坑）
        self.assertEqual(_chat_completions_url("https://apihub.agnes-ai.com"),
                         "https://apihub.agnes-ai.com/v1/chat/completions")
        # 带 /v1 或尾斜杠都不重复
        self.assertEqual(_chat_completions_url("https://api.openai.com/v1"),
                         "https://api.openai.com/v1/chat/completions")
        self.assertEqual(_chat_completions_url("https://api.deepseek.com/"),
                         "https://api.deepseek.com/v1/chat/completions")


class TranslateEndpointTest(unittest.TestCase):
    """临时库 + reload，端到端测翻译端点（manual 默认 / glossary 切换）。"""

    def _client(self, tmp):
        from fastapi.testclient import TestClient  # noqa: PLC0415
        import backend.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "t.db"
        import backend.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import backend.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def _chinese_1688_draft(self) -> dict:
        from backend.drafts import create_draft_from_url  # noqa: PLC0415
        d = create_draft_from_url(
            "https://detail.1688.com/offer/112233445566.html", source_platform="1688"
        )
        d.update({"ozon_title": "纯棉收纳箱 大号", "description": "高品质家居收纳"})
        return d

    def test_default_manual_then_glossary(self) -> None:
        import backend.main as main_mod  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                d = main_mod.APP.store.insert_draft(self._chinese_1688_draft())
                # 默认 manual：原样返回、仍含中文、note 非空
                r = client.post(f"/api/drafts/{d['id']}/translate")
                self.assertEqual(r.status_code, 200)
                body = r.json()
                self.assertEqual(body["engine"], "manual")
                self.assertTrue(body["still_cjk"])
                self.assertTrue(body["note"])
                # 切 glossary 引擎再翻：标题命中词典变俄文
                client.post("/api/settings", json={"translate_engine": "glossary"})
                r2 = client.post(f"/api/drafts/{d['id']}/translate")
                self.assertEqual(r2.status_code, 200)
                body2 = r2.json()
                self.assertEqual(body2["engine"], "glossary")
                self.assertIn("Коробка", body2["draft"]["ozon_title"])
                # state 回传引擎名，但不回传 key
                state = client.get("/api/state").json()
                self.assertEqual(state["settings"]["translate_engine"], "glossary")
                self.assertIn("translate_api_key_saved", state["settings"])
                self.assertNotIn("translate_api_key", state["settings"])
            finally:
                main_mod.APP.store.close()  # 关连接，否则 Windows 删不掉临时库

    def test_translate_missing_draft_404(self) -> None:
        import backend.main as main_mod  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                r = client.post("/api/drafts/999999/translate")
                self.assertEqual(r.status_code, 404)
            finally:
                main_mod.APP.store.close()


if __name__ == "__main__":
    unittest.main()
