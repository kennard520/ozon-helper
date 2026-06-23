from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from backend.image_compose import (  # noqa: E402
    add_watermark, compose_infographic, compose_main_white, wrap_text,
)

_FONT = Path(__file__).resolve().parents[2] / "outputs" / "fonts" / "Montserrat-VF.ttf"
FONT_PATH = str(_FONT) if _FONT.exists() else None


def _png(size, color, alpha=255) -> bytes:
    img = Image.new("RGBA", size, (color[0], color[1], color[2], alpha))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class ComposeMainWhiteTest(unittest.TestCase):
    def test_output_canvas_size_and_jpeg(self) -> None:
        out = compose_main_white(_png((200, 200), (255, 0, 0)), canvas=(1024, 1536))
        img = Image.open(io.BytesIO(out))
        self.assertEqual(img.size, (1024, 1536))
        self.assertEqual(img.format, "JPEG")

    def test_center_has_product_corners_white(self) -> None:
        out = compose_main_white(_png((200, 200), (255, 0, 0)), canvas=(1024, 1536))
        img = Image.open(io.BytesIO(out)).convert("RGB")
        cr, cg, cb = img.getpixel((512, 768))      # 中心 = 产品（红）
        self.assertTrue(cr > 200 and cg < 60 and cb < 60, f"center={cr,cg,cb}")
        wr, wg, wb = img.getpixel((3, 3))          # 角落 = 白底
        self.assertTrue(wr > 240 and wg > 240 and wb > 240, f"corner={wr,wg,wb}")

    def test_product_stays_within_margin(self) -> None:
        # 12% 边距：x<120 的列应当全是白底（产品不越界到安全边外）
        out = compose_main_white(_png((400, 400), (0, 0, 255)), canvas=(1000, 1500), margin_ratio=0.12)
        img = Image.open(io.BytesIO(out)).convert("RGB")
        for y in range(0, 1500, 150):
            r, g, b = img.getpixel((40, y))
            self.assertTrue(r > 240 and g > 240 and b > 240, f"边距内出现非白 @({40},{y})={r,g,b}")


class AddWatermarkTest(unittest.TestCase):
    def _solid_png(self, size=(400, 400), color=(100, 100, 100)) -> bytes:
        img = Image.new("RGB", size, color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_bottom_right_region_changes(self) -> None:
        base = self._solid_png()
        marked = add_watermark(base, "MyShop", fmt="PNG", color=(255, 255, 255), opacity=220)
        a = Image.open(io.BytesIO(base)).convert("RGB")
        b = Image.open(io.BytesIO(marked)).convert("RGB")
        # 右下角区域应被改动（出现水印像素）
        crop_a = a.crop((250, 350, 400, 400)).tobytes()
        crop_b = b.crop((250, 350, 400, 400)).tobytes()
        self.assertNotEqual(crop_a, crop_b)
        # 左上角不该被动
        self.assertEqual(a.crop((0, 0, 100, 100)).tobytes(), b.crop((0, 0, 100, 100)).tobytes())

    def test_returns_jpeg_by_default(self) -> None:
        out = add_watermark(self._solid_png(), "Shop")
        self.assertEqual(Image.open(io.BytesIO(out)).format, "JPEG")


class WrapTextTest(unittest.TestCase):
    def test_wraps_to_fit_width(self) -> None:
        img = Image.new("RGB", (10, 10))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        lines = wrap_text(draw, "слово " * 20, font, max_width=120)
        self.assertGreater(len(lines), 1)
        for ln in lines:
            self.assertLessEqual(draw.textlength(ln, font=font), 120 + 40)  # 容差：单词边界

    def test_empty_returns_one_line(self) -> None:
        img = Image.new("RGB", (10, 10))
        self.assertEqual(wrap_text(ImageDraw.Draw(img), "", ImageFont.load_default(), 100), [""])


class ComposeInfographicTest(unittest.TestCase):
    def test_size_format_and_bottom_panel_drawn(self) -> None:
        out = compose_infographic(
            None, canvas=(800, 1200), heading="Гарантия качества",
            bullets=["Водостойкий материал", "Удобный размер", "Быстрая доставка"],
            font_path=FONT_PATH)
        img = Image.open(io.BytesIO(out))
        self.assertEqual(img.size, (800, 1200))
        self.assertEqual(img.format, "JPEG")
        rgb = img.convert("RGB")
        # 顶部仍是浅灰底（面板在底部）
        tr, tg, tb = rgb.getpixel((20, 20))
        self.assertTrue(tr > 220 and tg > 220 and tb > 220, f"top={tr,tg,tb}")
        # 底部面板区明显变暗（半透明深色面板叠上去；base 浅底每通道 240+）
        bottom = rgb.crop((0, 1100, 800, 1200))
        min_per_channel = min(band[0] for band in bottom.getextrema())
        self.assertLess(min_per_channel, 180, "底部应有深色面板")


if __name__ == "__main__":
    unittest.main()
