from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webui.understand import (  # noqa: E402
    SYS_UNDERSTAND,
    build_understand_input,
    parse_understanding,
    understand,
)

DRAFT = {
    "source_title": "加厚铁油桶 15L",
    "description": "便携油桶",
    "source_raw": {
        "title": "加厚铁油桶 15L",
        "params": [{"k": "材质", "v": "镀锌钢"}, {"k": "容量", "v": "15L"}],
        "description_text": "便携油桶,加厚防漏",
        "detail_images": ["https://d/1.jpg", "https://d/2.jpg"],
    },
    "images": ["https://m/main.jpg", "https://d/1.jpg"],  # 主图 + 与详情图重复一张
}


class BuildInputTest(unittest.TestCase):
    def test_text_has_title_params_desc(self) -> None:
        user, imgs = build_understand_input(DRAFT)
        self.assertIn("Title: 加厚铁油桶 15L", user)
        self.assertIn("材质: 镀锌钢", user)
        self.assertIn("容量: 15L", user)
        self.assertIn("便携油桶", user)

    def test_images_detail_first_main_after_deduped_capped(self) -> None:
        _user, imgs = build_understand_input(DRAFT)
        self.assertEqual(imgs, ["https://d/1.jpg", "https://d/2.jpg", "https://m/main.jpg"])

    def test_cap(self) -> None:
        d = {"source_raw": {"detail_images": [f"https://d/{i}.jpg" for i in range(10)]}}
        _u, imgs = build_understand_input(d, max_images=3)
        self.assertEqual(len(imgs), 3)


class ParseTest(unittest.TestCase):
    def test_parse_with_fence_and_defaults(self) -> None:
        out = parse_understanding('```json\n{"type":"油桶","specs":{"容量":"15л"}}\n```')
        self.assertEqual(out["type"], "油桶")
        self.assertEqual(out["specs"], {"容量": "15л"})
        self.assertEqual(out["points"], [])      # 默认补齐
        self.assertEqual(out["images"], [])
        self.assertEqual(out["copy_seed"], {})

    def test_parse_noise_around_json(self) -> None:
        out = parse_understanding('好的:\n{"type":"x"} 完成')
        self.assertEqual(out["type"], "x")

    def test_bad_input_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_understanding("没有 JSON")


class UnderstandTest(unittest.TestCase):
    def test_calls_chat_with_images_and_parses(self) -> None:
        calls = []

        def fake_chat(system, user, images):
            calls.append({"system": system, "user": user, "images": images})
            return '{"type":"油桶","points":["加厚防漏"],"images":[{"idx":0,"role":"整体"}]}'

        u = understand(DRAFT, fake_chat)
        self.assertEqual(u["type"], "油桶")
        self.assertEqual(u["points"], ["加厚防漏"])
        self.assertEqual(calls[0]["system"], SYS_UNDERSTAND)
        self.assertEqual(calls[0]["images"], ["https://d/1.jpg", "https://d/2.jpg", "https://m/main.jpg"])

    def test_resolve_image_applied_and_failures_skipped(self) -> None:
        def fake_chat(system, user, images):
            return '{"type":"x"}'

        seen = {}

        def resolver(u):
            if u.endswith("2.jpg"):
                raise ValueError("取不到")     # 这张跳过
            return "RESOLVED:" + u

        def chat(system, user, images):
            seen["images"] = images
            return '{"type":"x"}'

        understand(DRAFT, chat, resolve_image=resolver)
        self.assertEqual(seen["images"], ["RESOLVED:https://d/1.jpg", "RESOLVED:https://m/main.jpg"])


if __name__ == "__main__":
    unittest.main()
