from __future__ import annotations

import json
import unittest


class NvidiaClientTest(unittest.TestCase):
    def test_posts_text_chat_to_integrate_endpoint(self) -> None:
        from ozon_common.nvidia import nvidia_chat

        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "TEXT"}}]}).encode()

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResp()

        out = nvidia_chat(
            {"base": "https://ai.api.nvidia.com", "key": "nv-key", "model": "nvidia/test"},
            "SYSTEM",
            "USER",
            opener=fake_urlopen,
        )

        self.assertEqual(out, "TEXT")
        self.assertEqual(captured["url"], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(captured["body"]["model"], "nvidia/test")
        self.assertEqual(captured["body"]["messages"][0], {"role": "system", "content": "SYSTEM"})

    def test_posts_paligemma_payload_with_first_image(self) -> None:
        from ozon_common.nvidia import nvidia_vlm_chat

        cfg = {"base": "https://ai.api.nvidia.com", "key": "nv-key", "model": "google/paligemma"}
        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{\"type\":\"dog\"}"}}]}).encode()

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResp()

        out = nvidia_vlm_chat(
            cfg,
            "SYSTEM",
            "Describe for Ozon",
            images=["data:image/jpeg;base64,QUJD", "data:image/png;base64,REVG"],
            opener=fake_urlopen,
        )

        self.assertEqual(out, '{"type":"dog"}')
        self.assertEqual(captured["url"], "https://ai.api.nvidia.com/v1/vlm/google/paligemma")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer nv-key")
        self.assertEqual(captured["headers"]["Accept"], "application/json")
        body = captured["body"]
        self.assertEqual(body["stream"], False)
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertIn("SYSTEM", body["messages"][0]["content"])
        self.assertIn("Describe for Ozon", body["messages"][0]["content"])
        self.assertIn('<img src="data:image/jpeg;base64,QUJD" />', body["messages"][0]["content"])
        self.assertNotIn("REVG", body["messages"][0]["content"])

    def test_vlm_falls_back_from_text_model_name_to_paligemma(self) -> None:
        from ozon_common.nvidia import nvidia_vlm_chat

        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            return FakeResp()

        nvidia_vlm_chat(
            {"base": "https://ai.api.nvidia.com", "key": "nv-key", "model": "nvidia/llama-3.1-nemotron-nano-8b-v1"},
            "S",
            "U",
            images=["data:image/jpeg;base64,QQ=="],
            opener=fake_urlopen,
        )

        self.assertEqual(captured["url"], "https://ai.api.nvidia.com/v1/vlm/google/paligemma")

    def test_downloads_http_image_before_posting(self) -> None:
        from ozon_common.nvidia import nvidia_vlm_chat

        cfg = {"base": "https://ai.api.nvidia.com/v1", "key": "nv-key", "model": ""}
        calls: list[str] = []
        captured: dict = {}

        class ImageResp:
            headers = {"Content-Type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return b"PNG"

        class ApiResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def fake_urlopen(req, timeout=0):
            url = req if isinstance(req, str) else req.full_url
            calls.append(url)
            if url == "https://img.test/a.png":
                return ImageResp()
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return ApiResp()

        self.assertEqual(
            nvidia_vlm_chat(cfg, "S", "U", images=["https://img.test/a.png"], opener=fake_urlopen),
            "ok",
        )

        self.assertEqual(calls[0], "https://img.test/a.png")
        self.assertEqual(calls[1], "https://ai.api.nvidia.com/v1/vlm/google/paligemma")
        self.assertIn(
            '<img src="data:image/png;base64,UE5H" />',
            captured["body"]["messages"][0]["content"],
        )

    def test_generates_image_with_native_genai_payload(self) -> None:
        from ozon_common.nvidia import nvidia_generate_image

        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"artifacts": [{"base64": "UE5H"}]}).encode()

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResp()

        resp = nvidia_generate_image(
            {"base": "https://integrate.api.nvidia.com/v1", "key": "nv-key", "model": ""},
            "make a product photo",
            size="1024x1536",
            opener=fake_urlopen,
        )

        self.assertEqual(captured["url"], "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-kontext-dev")
        self.assertEqual(captured["body"]["prompt"], "make a product photo")
        self.assertEqual(captured["body"]["width"], 1024)
        self.assertEqual(captured["body"]["height"], 1344)
        self.assertEqual(resp, {"data": [{"b64_json": "UE5H"}]})

    def test_generates_image_with_input_image_for_edit_models(self) -> None:
        from ozon_common.nvidia import nvidia_generate_image

        captured: dict = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return json.dumps({"data": [{"b64_json": "QQ=="}]}).encode()

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return FakeResp()

        nvidia_generate_image(
            {"base": "https://ai.api.nvidia.com", "key": "nv-key", "model": "black-forest-labs/flux.1-kontext-dev"},
            "edit it",
            image_data_uri="data:image/png;base64,UE5H",
            opener=fake_urlopen,
        )

        self.assertEqual(captured["body"]["image"], "data:image/png;base64,UE5H")


if __name__ == "__main__":
    unittest.main()
