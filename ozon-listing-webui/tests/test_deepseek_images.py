import json, unittest
from unittest.mock import patch
from backend import ai_card


class DeepseekImagesTest(unittest.TestCase):
    def _capture(self, **kw):
        s = {"ai_text": {"engine": "openai", "api_base": "https://b", "api_key": "k", "model": "m"}}
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

    def test_vision_content_blocks_with_images(self):
        body = self._capture(images=["https://img/x.jpg"])
        content = body["messages"][1]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0], {"type": "text", "text": "hello"})
        self.assertEqual(content[1], {"type": "image_url", "image_url": {"url": "https://img/x.jpg"}})


if __name__ == "__main__":
    unittest.main()
