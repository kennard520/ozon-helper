from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

import webui.store as store_mod
from webui.ai_card import build_image_prompt_input, parse_image_prompts


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u", "source_offer_id": "1",
        "source_title": "牙贴", "ozon_title": "", "description": "",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["https://img/a.jpg", "https://img/b.jpg"], "attributes": {}, "status": "draft",
        "publish_response": None, "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over)
    return d


class TestParseImagePrompts(unittest.TestCase):
    def test_normal(self):
        r = parse_image_prompts('{"main":"M","selling_points":["a","b","c"]}', 3)
        self.assertEqual(r["main"], "M")
        self.assertEqual(r["selling_points"], ["a", "b", "c"])

    def test_pads_when_too_few(self):
        r = parse_image_prompts('{"main":"M","selling_points":["a"]}', 3)
        self.assertEqual(r["selling_points"], ["a", "", ""])

    def test_truncates_when_too_many(self):
        r = parse_image_prompts('{"main":"M","selling_points":["a","b","c","d"]}', 2)
        self.assertEqual(r["selling_points"], ["a", "b"])

    def test_bad_json_no_crash(self):
        r = parse_image_prompts("garbage not json", 2)
        self.assertEqual(r["main"], "")
        self.assertEqual(r["selling_points"], ["", ""])

    def test_fenced_json(self):
        r = parse_image_prompts('```json\n{"main":"X","selling_points":["y"]}\n```', 1)
        self.assertEqual(r["main"], "X")
        self.assertEqual(r["selling_points"], ["y"])


class TestBuildImagePromptInput(unittest.TestCase):
    def test_prefers_ozon_russian(self):
        s = build_image_prompt_input({
            "ozon_title": "Шлем", "description": "описание",
            "attributes": [{"name": "Цвет", "value": "синий"}],
        })
        self.assertIn("Шлем", s)
        self.assertIn("Цвет: синий", s)
        self.assertIn("описание", s)

    def test_falls_back_to_source_title(self):
        s = build_image_prompt_input({"source_title": "牙贴", "ozon_title": "", "description": ""})
        self.assertIn("牙贴", s)

    def test_publish_format_attrs_skipped(self):
        # 上架格式 {id,values} 无可读名，不应进画像
        s = build_image_prompt_input({
            "ozon_title": "T", "attributes": [{"id": 85, "values": [{"value": "x"}]}],
        })
        self.assertNotIn("85", s)


class TestAiImagePromptsService(unittest.TestCase):
    def _app(self, tmp):
        store_mod.DEFAULT_DB = Path(tmp) / "ip.db"
        import webui.app_service as svc
        importlib.reload(svc)
        app = svc.App()
        import webui.ai_card as aic
        self._orig = aic.deepseek_chat
        aic.deepseek_chat = lambda settings, system, user, images=None: '{"main":"MAIN","selling_points":["s1","s2","s3"]}'
        self._aic = aic
        return app

    def _restore(self):
        self._aic.deepseek_chat = self._orig

    def test_returns_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                r = app.ai_image_prompts(d["id"], 3)
                self.assertTrue(r["ok"])
                self.assertEqual(r["main"], "MAIN")
                self.assertEqual(len(r["selling_points"]), 3)
                self.assertEqual(r["source_images"], ["https://img/a.jpg", "https://img/b.jpg"])
            finally:
                self._restore(); app.store.close()

    def test_n_points_clamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                self.assertEqual(len(app.ai_image_prompts(d["id"], 0)["selling_points"]), 1)   # 下限 1
                self.assertEqual(len(app.ai_image_prompts(d["id"], 99)["selling_points"]), 6)  # 上限 6
            finally:
                self._restore(); app.store.close()

    def test_missing_draft_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                with self.assertRaises(KeyError):
                    app.ai_image_prompts(99999, 3)
            finally:
                self._restore(); app.store.close()


def tearDownModule():
    # 还原 reload 引入的全局单例，避免污染其它测试模块
    import importlib
    store_mod.DEFAULT_DB = store_mod.Path(
        store_mod.os.environ.get("OZON_WEBUI_DB")
        or (store_mod.Path(__file__).resolve().parents[1] / "data" / "products.db"))
    import webui.app_service as _svc; importlib.reload(_svc)
    import webui.main as _main; importlib.reload(_main)


if __name__ == "__main__":
    unittest.main()
