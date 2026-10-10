import importlib
import tempfile
import unittest
from pathlib import Path


class CardChatVisionTest(unittest.TestCase):
    def _app(self, tmp):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import webui.app_service as svc
        importlib.reload(svc)
        return svc

    def test_multimodal_passes_images(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp)
            app = svc.App()
            import webui.ai_card as ai_card
            orig = ai_card.deepseek_chat
            try:
                captured = {}
                ai_card.deepseek_chat = lambda s, sy, u, images=None: captured.update(images=images) or "ok"
                settings = {"ai_text": {"engine": "openai", "api_base": "b", "api_key": "k",
                                        "model": "m", "multimodal": True}}
                draft = {"images": ["https://ir.ozone.ru/a.jpg"], "source_raw": {}}
                app._card_chat(settings, draft)("sys", "user")
                self.assertEqual(captured["images"], ["https://ir.ozone.ru/a.jpg"])
            finally:
                ai_card.deepseek_chat = orig
                app.store.close()

    def test_text_only_when_not_multimodal(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp)
            app = svc.App()
            import webui.ai_card as ai_card
            orig = ai_card.deepseek_chat
            try:
                captured = {}
                ai_card.deepseek_chat = lambda s, sy, u, images=None: captured.update(images=images) or "ok"
                settings = {"ai_text": {"engine": "openai", "api_base": "b", "api_key": "k",
                                        "model": "m", "multimodal": False}}
                draft = {"images": ["https://ir.ozone.ru/a.jpg"], "source_raw": {}}
                app._card_chat(settings, draft)("sys", "user")
                self.assertIsNone(captured["images"])
            finally:
                ai_card.deepseek_chat = orig
                app.store.close()


if __name__ == "__main__":
    unittest.main()
