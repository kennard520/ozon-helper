"""backend/agnes.py 纯客户端单测：HTTP 全部经 agnes._http_json 注入，离线跑。
规格依据 specs/agnes-api/README.md（2026-06-11）。"""
from __future__ import annotations

import unittest

import backend.agnes as agnes

SETTINGS = {"agnes_api_key": "K"}


class FakeHttp:
    """记录请求并按序回放响应。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, *, key, payload=None, timeout=60):
        self.calls.append({"url": url, "key": key, "payload": payload, "timeout": timeout})
        return self.responses.pop(0)


class ConfTest(unittest.TestCase):
    def test_missing_key_raises(self):
        with self.assertRaises(RuntimeError):
            agnes._conf({})

    def test_base_normalization(self):
        # 用户粘贴 /v1 或尾斜杠都容忍，统一裁掉（视频查询端点不带 /v1）
        for base in ("https://x.com", "https://x.com/", "https://x.com/v1", "https://x.com/v1/"):
            b, k = agnes._conf({"agnes_api_key": "K", "agnes_api_base": base})
            self.assertEqual(b, "https://x.com")
            self.assertEqual(k, "K")

    def test_default_base(self):
        b, _ = agnes._conf(SETTINGS)
        self.assertEqual(b, "https://apihub.agnes-ai.com")


class ChatTest(unittest.TestCase):
    def setUp(self):
        self._orig = agnes._http_json

    def tearDown(self):
        agnes._http_json = self._orig

    def test_plain_chat_body(self):
        fake = FakeHttp([{"choices": [{"message": {"content": " hi "}}]}])
        agnes._http_json = fake
        out = agnes.agnes_chat(SETTINGS, "SYS", "USER")
        self.assertEqual(out, "hi")
        call = fake.calls[0]
        self.assertEqual(call["url"], "https://apihub.agnes-ai.com/v1/chat/completions")
        body = call["payload"]
        self.assertEqual(body["model"], "agnes-2.0-flash")
        self.assertEqual(body["messages"][0], {"role": "system", "content": "SYS"})
        self.assertEqual(body["messages"][1], {"role": "user", "content": "USER"})
        # 编码/推理任务按文档开 thinking（OpenAI 兼容写法）
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": True})

    def test_vision_content_blocks(self):
        fake = FakeHttp([{"choices": [{"message": {"content": "ok"}}]}])
        agnes._http_json = fake
        agnes.agnes_chat(SETTINGS, "S", "U", images=["https://a/1.jpg", "https://a/2.jpg"])
        content = fake.calls[0]["payload"]["messages"][1]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "U"})
        self.assertEqual(content[1], {"type": "image_url", "image_url": {"url": "https://a/1.jpg"}})
        self.assertEqual(len(content), 3)

    def test_vision_caps_at_4_images(self):
        fake = FakeHttp([{"choices": [{"message": {"content": "ok"}}]}])
        agnes._http_json = fake
        agnes.agnes_chat(SETTINGS, "S", "U", images=[f"https://a/{i}.jpg" for i in range(9)])
        content = fake.calls[0]["payload"]["messages"][1]["content"]
        self.assertEqual(len(content), 1 + 4)

    def test_custom_model_setting(self):
        fake = FakeHttp([{"choices": [{"message": {"content": "ok"}}]}])
        agnes._http_json = fake
        agnes.agnes_chat({**SETTINGS, "agnes_chat_model": "agnes-3"}, "S", "U")
        self.assertEqual(fake.calls[0]["payload"]["model"], "agnes-3")

    def test_malformed_response_becomes_runtime_error(self):
        # 别让裸 KeyError/IndexError 逃出去——路由会把 KeyError 映成 404（语义错）
        for bad in ({}, {"choices": []}, {"choices": [{"no_message": 1}]}):
            agnes._http_json = FakeHttp([bad])
            with self.assertRaises(RuntimeError):
                agnes.agnes_chat(SETTINGS, "S", "U")


class ImageTest(unittest.TestCase):
    def setUp(self):
        self._orig = agnes._http_json

    def tearDown(self):
        agnes._http_json = self._orig

    def test_text2img_payload(self):
        fake = FakeHttp([{"data": [{"url": "https://cdn/x.png"}]}])
        agnes._http_json = fake
        url = agnes.generate_image(SETTINGS, "a cat", size="1024x768")
        self.assertEqual(url, "https://cdn/x.png")
        body = fake.calls[0]["payload"]
        self.assertEqual(fake.calls[0]["url"], "https://apihub.agnes-ai.com/v1/images/generations")
        self.assertEqual(body["model"], "agnes-image-2.1-flash")
        self.assertEqual(body["size"], "1024x768")
        # 官方坑：response_format 必须在 extra_body，顶层会 400
        self.assertNotIn("response_format", body)
        self.assertEqual(body["extra_body"]["response_format"], "url")
        self.assertNotIn("image", body["extra_body"])

    def test_img2img_payload(self):
        fake = FakeHttp([{"data": [{"url": "https://cdn/y.png"}]}])
        agnes._http_json = fake
        agnes.generate_image(SETTINGS, "white bg", source_images=["https://src/1.jpg"])
        body = fake.calls[0]["payload"]
        self.assertEqual(body["extra_body"]["image"], ["https://src/1.jpg"])
        self.assertEqual(body["extra_body"]["response_format"], "url")

    def test_empty_prompt_raises(self):
        with self.assertRaises(ValueError):
            agnes.generate_image(SETTINGS, "  ")

    def test_missing_url_raises(self):
        agnes._http_json = FakeHttp([{"data": []}])
        with self.assertRaises(RuntimeError):
            agnes.generate_image(SETTINGS, "x")


class VideoTest(unittest.TestCase):
    def setUp(self):
        self._orig = agnes._http_json

    def tearDown(self):
        agnes._http_json = self._orig

    def test_snap_num_frames(self):
        # 约束：≤441 且 8n+1
        self.assertEqual(agnes.snap_num_frames(121), 121)
        self.assertEqual(agnes.snap_num_frames(120), 121)   # 120→120//8*8+1=121
        self.assertEqual(agnes.snap_num_frames(9999), 441)
        self.assertEqual(agnes.snap_num_frames(0), 9)
        self.assertEqual(agnes.snap_num_frames("bad"), 121)

    def test_create_task(self):
        fake = FakeHttp([{"video_id": "video_1", "task_id": "task_1", "status": "queued"}])
        agnes._http_json = fake
        r = agnes.create_video_task(SETTINGS, "spin", image="https://src/main.jpg")
        self.assertEqual(r["video_id"], "video_1")
        body = fake.calls[0]["payload"]
        self.assertEqual(fake.calls[0]["url"], "https://apihub.agnes-ai.com/v1/videos")
        self.assertEqual(body["model"], "agnes-video-v2.0")
        self.assertEqual(body["image"], "https://src/main.jpg")
        self.assertEqual(body["num_frames"], 121)
        self.assertEqual(body["frame_rate"], 24)

    def test_create_task_no_id_raises(self):
        agnes._http_json = FakeHttp([{"status": "queued"}])
        with self.assertRaises(RuntimeError):
            agnes.create_video_task(SETTINGS, "spin")

    def test_query_completed_url_in_remixed_field(self):
        # 官方文档：最终视频 URL 在 remixed_from_video_id（字段名怪但如此）
        fake = FakeHttp([{"status": "completed", "progress": 100,
                          "remixed_from_video_id": "https://storage.googleapis.com/a/v.mp4"}])
        agnes._http_json = fake
        r = agnes.query_video(SETTINGS, "video_1")
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["url"], "https://storage.googleapis.com/a/v.mp4")
        # 查询端点不带 /v1 前缀
        self.assertTrue(fake.calls[0]["url"].startswith("https://apihub.agnes-ai.com/agnesapi?"))
        self.assertIn("video_id=video_1", fake.calls[0]["url"])

    def test_query_failed(self):
        agnes._http_json = FakeHttp([{"status": "failed", "error": {"msg": "boom"}}])
        r = agnes.query_video(SETTINGS, "v")
        self.assertEqual(r["status"], "failed")
        self.assertTrue(r["error"])

    def test_query_ignores_non_url_remixed_value(self):
        # remixed_from_video_id 不是 http 开头（比如回填了个 ID）就不当 URL
        agnes._http_json = FakeHttp([{"status": "in_progress", "remixed_from_video_id": "video_2"}])
        r = agnes.query_video(SETTINGS, "v")
        self.assertEqual(r["url"], "")


class HelpersTest(unittest.TestCase):
    def test_to_data_uri(self):
        uri = agnes.to_data_uri(b"\x89PNG", "/media/draft-1/up-1.png")
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        uri2 = agnes.to_data_uri(b"\xff\xd8", "a.jpg")
        self.assertTrue(uri2.startswith("data:image/jpeg;base64,"))
        # 未知扩展名兜底 png
        self.assertTrue(agnes.to_data_uri(b"x", "noext").startswith("data:image/png;"))

    def test_pick_public_images(self):
        out = agnes.pick_public_images(
            ["/media/draft-1/01.jpg", "https://a/1.jpg", "https://a/1.jpg"],
            ["https://a/2.jpg", "https://a/3.jpg", "https://a/4.jpg"])
        # 本地副本跳过、去重、详情图补足、cap 3
        self.assertEqual(out, ["https://a/1.jpg", "https://a/2.jpg", "https://a/3.jpg"])
        self.assertEqual(agnes.pick_public_images(None, None), [])


if __name__ == "__main__":
    unittest.main()
