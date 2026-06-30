import unittest

from webui.translate import RemoteEngine, get_engine


class AiTextConfigTest(unittest.TestCase):
    def test_remote_engine_reads_ai_text_block(self):
        s = {"ai_text": {"engine": "openai", "api_base": "https://b", "api_key": "k", "model": "m"}}
        eng = get_engine("ai", s)
        self.assertIsInstance(eng, RemoteEngine)
        self.assertEqual(eng.base, "https://b")
        self.assertEqual(eng.key, "k")
        self.assertEqual(eng.model, "m")

    def test_manual_mode_still_manual(self):
        self.assertEqual(get_engine("manual", {}).name, "manual")

    def test_legacy_translate_fields_still_resolve(self):
        s = {"translate_api_base": "https://legacy", "translate_api_key": "lk", "translate_model": "lm"}
        eng = get_engine("ai", s)
        self.assertEqual(eng.base, "https://legacy")
        self.assertEqual(eng.key, "lk")


if __name__ == "__main__":
    unittest.main()
