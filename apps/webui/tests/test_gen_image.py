from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 让 `import ozon_common.gen_image` 可用（backend 在 ozon-listing-webui = tests 的 parents[1]）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ozon_common.gen_image import (  # noqa: E402
    LOCALIZE_PROMPT,
    SCENE_PROMPT,
    WHITE_MAIN_PROMPT,
    GenImageConfig,
    build_create_payload,
    build_edit_request,
    build_infographic_prompt,
    create_image,
    edit_image,
    generate_main,
    images_from_response,
    serialize_multipart,
)

CFG = GenImageConfig(api_key="k", base_url="https://gw.test/v1", model="gpt-image-1.5", image_field="image")


def _canned(b64_bytes: bytes = b"PNGDATA") -> dict:
    return {"data": [{"b64_json": base64.b64encode(b64_bytes).decode()}]}


class FakePoster:
    def __init__(self, response: dict | None = None) -> None:
        self.response = response if response is not None else _canned()
        self.calls: list[dict] = []

    def __call__(self, url: str, headers: dict, body: bytes) -> dict:
        self.calls.append({"url": url, "headers": headers, "body": body})
        return self.response


class BuildPayloadTest(unittest.TestCase):
    def test_create_payload_minimal_and_optional(self) -> None:
        self.assertEqual(
            build_create_payload(CFG, "hi", n=2, size=None, quality=None, output_format=None, background=None),
            {"model": "gpt-image-1.5", "prompt": "hi", "n": 2})
        p = build_create_payload(CFG, "hi", size="1024x1536", background="transparent", output_format="png")
        self.assertEqual(p["size"], "1024x1536")
        self.assertEqual(p["background"], "transparent")
        self.assertEqual(p["output_format"], "png")

    def test_edit_request_url_fields_files(self) -> None:
        url, fields, files = build_edit_request(
            CFG, "do", ["a.png", "b.png"], mask_path="m.png", background="transparent", output_format="png")
        self.assertEqual(url, "https://gw.test/v1/images/edits")
        d = dict(fields)
        self.assertEqual(d["model"], "gpt-image-1.5")
        self.assertEqual(d["prompt"], "do")
        self.assertEqual(d["background"], "transparent")
        self.assertEqual(d["output_format"], "png")
        self.assertEqual(files, [("image", "a.png"), ("image", "b.png"), ("mask", "m.png")])


class SerializeTest(unittest.TestCase):
    def test_multipart_has_boundary_field_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "src.png")
            with open(fp, "wb") as fh:
                fh.write(b"\x89PNGfake")
            body, ct = serialize_multipart([("prompt", "hi"), ("background", "transparent")],
                                           [("image", fp)])
        self.assertTrue(ct.startswith("multipart/form-data; boundary="))
        self.assertIn(b'name="prompt"', body)
        self.assertIn(b"transparent", body)
        self.assertIn(b'filename="src.png"', body)
        self.assertIn(b"\x89PNGfake", body)


class ImagesFromResponseTest(unittest.TestCase):
    def test_decodes_b64(self) -> None:
        self.assertEqual(images_from_response(_canned(b"hello")), [b"hello"])

    def test_falls_back_to_url_via_fetch(self) -> None:
        resp = {"data": [{"url": "https://img.test/x.png"}]}
        out = images_from_response(resp, fetch=lambda u: b"FETCHED:" + u.encode())
        self.assertEqual(out, [b"FETCHED:https://img.test/x.png"])


class OrchestrationTest(unittest.TestCase):
    def test_create_image_posts_json_to_generations(self) -> None:
        post = FakePoster()
        create_image(CFG, "scene", size="1024x1536", http_post=post)
        self.assertEqual(post.calls[0]["url"], "https://gw.test/v1/images/generations")
        self.assertEqual(post.calls[0]["headers"]["Content-Type"], "application/json")
        self.assertIn(b'"model"', post.calls[0]["body"])

    def test_edit_image_posts_multipart_to_edits(self) -> None:
        post = FakePoster()
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "p.png")
            with open(fp, "wb") as fh:
                fh.write(b"img")
            edit_image(CFG, "redo", [fp], background="transparent", output_format="png", http_post=post)
        self.assertEqual(post.calls[0]["url"], "https://gw.test/v1/images/edits")
        self.assertTrue(post.calls[0]["headers"]["Content-Type"].startswith("multipart/form-data"))

    def test_generate_main_uses_white_prompt_returns_bytes_no_transparent(self) -> None:
        post = FakePoster(_canned(b"MAIN"))
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "src.png")
            with open(fp, "wb") as fh:
                fh.write(b"img")
            out = generate_main(fp, cfg=CFG, http_post=post)
        self.assertEqual(out, b"MAIN")
        body = post.calls[0]["body"]
        self.assertEqual(post.calls[0]["url"], "https://gw.test/v1/images/edits")
        self.assertIn(b"#FFFFFF", body)                       # 白底提示词
        self.assertIn(WHITE_MAIN_PROMPT.encode("utf-8")[:20], body)
        self.assertNotIn(b"transparent", body)                # 不再走透明（模型不支持）


class PromptTest(unittest.TestCase):
    def test_localize_prompt_translates_and_strips_nonproduct(self) -> None:
        self.assertIn("translate", LOCALIZE_PROMPT.lower())
        self.assertIn("Russian", LOCALIZE_PROMPT)
        self.assertIn("REMOVE", LOCALIZE_PROMPT)      # 剔除非产品内容
        self.assertIn("OEM", LOCALIZE_PROMPT)
        self.assertIn("product-relevant", LOCALIZE_PROMPT)
        self.assertIn("factory audit", LOCALIZE_PROMPT)
        self.assertIn("complete certifications", LOCALIZE_PROMPT)
        self.assertIn("CE/FCC/RoHS", LOCALIZE_PROMPT)
        self.assertIn("fast/lightning shipping", LOCALIZE_PROMPT)

    def test_infographic_prompt_embeds_russian_and_forbids_other_text(self) -> None:
        p = build_infographic_prompt(role="尺寸图", heading="Размеры", bullets=["36 см", "15 л"])
        self.assertIn("尺寸图", p)
        self.assertIn("Размеры", p)
        self.assertIn("36 см", p)
        self.assertIn("15 л", p)
        self.assertIn("NO other text", p)
        self.assertIn("No Chinese", p)

    def test_infographic_prompt_no_text_when_empty(self) -> None:
        p = build_infographic_prompt(role="主图")
        self.assertIn("No text on the image.", p)

    def test_scene_prompt_keeps_product_strips_nonproduct(self) -> None:
        self.assertIn("identical", SCENE_PROMPT.lower())   # 保产品一致
        self.assertIn("REMOVE", SCENE_PROMPT)              # 剔除非产品内容
        self.assertIn("No text", SCENE_PROMPT)


if __name__ == "__main__":
    unittest.main()
