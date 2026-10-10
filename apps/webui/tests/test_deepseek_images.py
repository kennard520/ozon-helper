import json
import unittest
from unittest.mock import patch

from webui import ai_card


class DeepseekImagesTest(unittest.TestCase):
    def _capture(self, **kw):
        s = kw.pop("settings", None) or {"ai_text": {"engine": "openai", "api_base": "https://b", "api_key": "k", "model": "m"}}
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode())
            return FakeResp()

        with patch("urllib.request.urlopen", fake_urlopen):
            ai_card.deepseek_chat(s, "sys", "hello", **kw)
        return captured["body"]

    def test_text_only_when_no_images(self):
        body = self._capture()
        self.assertEqual(body["messages"][1]["content"], "hello")

    def test_deepseek_disables_thinking(self):
        body = self._capture(settings={
            "ai_text": {"engine": "openai", "api_base": "https://api.deepseek.com/v1", "api_key": "k", "model": "deepseek-v4-flash"}
        })
        self.assertEqual(body["thinking"], {"type": "disabled"})

    def test_non_deepseek_does_not_send_thinking_param(self):
        body = self._capture(settings={
            "ai_text": {"engine": "openai", "api_base": "https://api.openai.test/v1", "api_key": "k", "model": "gpt-test"}
        })
        self.assertNotIn("thinking", body)

    def test_vision_content_blocks_with_images(self):
        body = self._capture(images=["https://img/x.jpg"])
        content = body["messages"][1]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0], {"type": "text", "text": "hello"})
        self.assertEqual(content[1], {"type": "image_url", "image_url": {"url": "https://img/x.jpg"}})

    def test_nvidia_engine_uses_nvidia_chat(self):
        s = {"ai_text": {"engine": "nvidia", "api_base": "https://ai.api.nvidia.com", "api_key": "k", "model": "nvidia/m"}}
        with patch("ozon_common.nvidia.nvidia_chat", return_value="NV") as chat:
            out = ai_card.deepseek_chat(s, "sys", "hello")
        self.assertEqual(out, "NV")
        chat.assert_called_once()
        self.assertEqual(chat.call_args.args[1:3], ("sys", "hello"))


if __name__ == "__main__":
    unittest.main()
