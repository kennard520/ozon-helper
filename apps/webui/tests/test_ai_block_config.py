import unittest

from webui import agnes


class AgnesBlockConfigTest(unittest.TestCase):
    def test_image_uses_ai_image_block(self):
        captured = {}
        s = {"ai_image": {"engine": "agnes", "api_base": "https://img", "api_key": "IK", "model": "img-m"}}

        def fake_http(url, *, key, payload, timeout):
            captured.update(url=url, key=key, model=payload["model"])
            return {"data": [{"url": "https://out/x.png"}]}

        orig = agnes._http_json
        agnes._http_json = fake_http
        try:
            out = agnes.generate_image(s, "hello")
        finally:
            agnes._http_json = orig
        self.assertEqual(out, "https://out/x.png")
        self.assertEqual(captured["key"], "IK")
        self.assertTrue(captured["url"].startswith("https://img"))
        self.assertEqual(captured["model"], "img-m")


if __name__ == "__main__":
    unittest.main()
