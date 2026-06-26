from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image  # noqa: E402

from webui.image_compose import compose_infographic  # noqa: E402
from webui.image_pipeline import assemble_images  # noqa: E402

_FONT = Path(__file__).resolve().parents[2] / "outputs" / "fonts" / "Montserrat-VF.ttf"
FONT_PATH = str(_FONT) if _FONT.exists() else None
CANVAS = (800, 1200)


def _jpeg(color=(230, 230, 230)) -> bytes:
    img = Image.new("RGB", CANVAS, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

MAIN = _jpeg((235, 235, 235))           # 假“白底主图”


def _fake_main(_ref: str) -> bytes:
    return MAIN


def _fake_scene(_ref: str, _prompt: str) -> bytes:
    return _jpeg((60, 90, 140))


class AssembleImagesTest(unittest.TestCase):
    def test_count_main_plus_infographics_plus_scenes(self) -> None:
        imgs = assemble_images(
            "src.jpg", shop_name="MyShop", make_main=_fake_main,
            infographics=[{"heading": "H1", "bullets": ["a"]}, {"heading": "H2", "bullets": ["b"]}],
            scenes=["s1", "s2", "s3"], make_scene=_fake_scene,
            font_path=FONT_PATH, canvas=CANVAS)
        self.assertEqual(len(imgs), 1 + 2 + 3)
        for b in imgs:
            im = Image.open(io.BytesIO(b))
            self.assertEqual(im.size, CANVAS)

    def test_main_image_is_make_main_output_unmodified(self) -> None:
        # 主图(索引0) 应与 make_main 产出逐字节一致（无水印、不二次处理）
        imgs = assemble_images("src.jpg", shop_name="MyShop", make_main=_fake_main,
                               infographics=[{"heading": "H", "bullets": ["a"]}], canvas=CANVAS)
        self.assertEqual(imgs[0], MAIN)

    def test_infographic_uses_main_as_bg_and_is_watermarked(self) -> None:
        imgs = assemble_images("src.jpg", shop_name="MyShop", make_main=_fake_main,
                               infographics=[{"heading": "H", "bullets": ["a", "b"]}],
                               font_path=FONT_PATH, canvas=CANVAS)
        plain = compose_infographic(MAIN, canvas=CANVAS, heading="H", bullets=["a", "b"],
                                    font_path=FONT_PATH, fmt="JPEG")
        # 副图(索引1) 加了水印 → 与未加水印版本不同
        self.assertNotEqual(imgs[1], plain)

    def test_no_scenes_when_make_scene_omitted(self) -> None:
        imgs = assemble_images("src.jpg", shop_name="S", make_main=_fake_main,
                               infographics=[], scenes=["x"], canvas=CANVAS)  # 无 make_scene
        self.assertEqual(len(imgs), 1)   # 只有主图


if __name__ == "__main__":
    unittest.main()
