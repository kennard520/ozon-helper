from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webui.image_pipeline import upload_images  # noqa: E402
from webui.listing_build import (  # noqa: E402
    build_original_draft,
    build_rich_content,
    default_pricing,
    parse_dims_mm,
    parse_weight_g,
    random_offer_id,
    rich_billboard,
)


class UploadImagesTest(unittest.TestCase):
    def test_uploads_each_in_order(self) -> None:
        calls = []

        def fake_upload(b: bytes, ext: str) -> str:
            calls.append((b, ext))
            return f"https://oss.test/{hashlib.md5(b).hexdigest()}.{ext}"

        urls = upload_images([b"a", b"b", b"c"], fake_upload, ext="jpg")
        self.assertEqual(len(urls), 3)
        self.assertTrue(all(u.startswith("https://oss.test/") and u.endswith(".jpg") for u in urls))
        self.assertEqual([c[1] for c in calls], ["jpg", "jpg", "jpg"])


class RandomOfferIdTest(unittest.TestCase):
    def test_prefix_and_length(self) -> None:
        oid = random_offer_id(prefix="OZ", length=10)
        self.assertTrue(oid.startswith("OZ"))
        self.assertEqual(len(oid), 12)
        self.assertTrue(oid[2:].isalnum())

    def test_injected_rng_is_deterministic(self) -> None:
        self.assertEqual(random_offer_id(prefix="X", length=4, rng=lambda alpha: "A"), "XAAAA")

    def test_calls_vary(self) -> None:
        ids = {random_offer_id() for _ in range(8)}
        self.assertGreaterEqual(len(ids), 7)   # 基本不重复


class BuildOriginalDraftTest(unittest.TestCase):
    CARD = {
        "ozon_title": "Спрей от комаров 100 мл",
        "description": "Описание...",
        "category_id": "17027949", "type_id": "93308",
        "weight_g": 150, "length_mm": 12, "width_mm": 5, "height_mm": 5,
        "attributes": [{"id": 23171, "values": [{"value": "#спрей"}]}],
        "brand_name": "Нет бренда",
        "mapped": [{"id": 23171}], "unmapped": [],
    }

    def test_merges_card_images_and_meta(self) -> None:
        d = build_original_draft(
            {"title": "驱蚊喷雾"}, card=self.CARD,
            image_urls=["https://oss/1.jpg", "https://oss/2.jpg"],
            offer_id="OZABC123", source="1688", price=2300, old_price=2590, stock=99)
        self.assertEqual(d["offer_id"], "OZABC123")
        self.assertEqual(d["ozon_title"], "Спрей от комаров 100 мл")
        self.assertEqual(d["source_title"], "驱蚊喷雾")
        self.assertEqual(d["images"], ["https://oss/1.jpg", "https://oss/2.jpg"])
        self.assertEqual(d["category_id"], "17027949")
        self.assertEqual(d["price"], "2300")
        self.assertEqual(d["weight_g"], 150)
        self.assertEqual(d["brand_name"], "Нет бренда")
        self.assertEqual(d["status"], "ready")
        self.assertEqual(d["source"], "1688")

    def test_defaults_safe_on_minimal_card(self) -> None:
        d = build_original_draft({}, card={}, image_urls=[], offer_id="X1")
        self.assertEqual(d["images"], [])
        self.assertEqual(d["weight_g"], 0)
        self.assertEqual(d["brand_name"], "Нет бренда")
        self.assertEqual(d["status"], "ready")


class BuildRichContentTest(unittest.TestCase):
    def test_billboard_schema_matches_ozon(self) -> None:
        # 与生产 _set_richcontent.py 的 billboard() 逐字段一致
        self.assertEqual(rich_billboard("https://oss/x.jpg"), {
            "widgetName": "raShowcase", "type": "billboard",
            "blocks": [{"img": {"src": "https://oss/x.jpg", "srcMobile": "https://oss/x.jpg", "alt": ""}}]})

    def test_build_orders_images_and_sets_version(self) -> None:
        rc = build_rich_content(["https://oss/a.jpg", "https://oss/b.jpg"])
        self.assertEqual(rc["version"], 0.3)
        self.assertEqual(len(rc["content"]), 2)
        self.assertEqual(rc["content"][0]["blocks"][0]["img"]["src"], "https://oss/a.jpg")
        self.assertEqual(rc["content"][1]["blocks"][0]["img"]["src"], "https://oss/b.jpg")

    def test_skips_empty_urls(self) -> None:
        rc = build_rich_content(["https://oss/a.jpg", "", None, "  "])
        self.assertEqual(len(rc["content"]), 1)


class ParseDimsTest(unittest.TestCase):
    def test_mm_kept(self) -> None:
        self.assertEqual(parse_dims_mm("335*290*185mm"), (335, 290, 185))

    def test_cm_to_mm(self) -> None:
        self.assertEqual(parse_dims_mm("33.5×29×18.5 cm"), (335, 290, 185))

    def test_no_unit_large_assumed_mm(self) -> None:
        self.assertEqual(parse_dims_mm("335 x 290 x 185"), (335, 290, 185))

    def test_no_unit_small_assumed_cm(self) -> None:
        self.assertEqual(parse_dims_mm("34*29*19"), (340, 290, 190))

    def test_too_few_numbers(self) -> None:
        self.assertIsNone(parse_dims_mm("335mm"))
        self.assertIsNone(parse_dims_mm(""))


class ParseWeightTest(unittest.TestCase):
    def test_grams(self) -> None:
        self.assertEqual(parse_weight_g("1800g"), 1800)
        self.assertEqual(parse_weight_g("1800 克"), 1800)

    def test_kg(self) -> None:
        self.assertEqual(parse_weight_g("1.8kg"), 1800)
        self.assertEqual(parse_weight_g("1.8 кг"), 1800)

    def test_no_unit_small_is_kg(self) -> None:
        self.assertEqual(parse_weight_g("1.8"), 1800)

    def test_no_unit_large_is_grams(self) -> None:
        self.assertEqual(parse_weight_g("1800"), 1800)

    def test_invalid(self) -> None:
        self.assertIsNone(parse_weight_g("无"))


class DefaultPricingTest(unittest.TestCase):
    def test_sell_and_line(self) -> None:
        # 进价 100 → 售价 100×1.3×2=260 → 划线价 260×1.8=468
        self.assertEqual(default_pricing(100), (260.0, 468.0))

    def test_string_cost(self) -> None:
        self.assertEqual(default_pricing("50"), (130.0, 234.0))

    def test_invalid_cost(self) -> None:
        self.assertIsNone(default_pricing(0))
        self.assertIsNone(default_pricing(None))
        self.assertIsNone(default_pricing("abc"))


if __name__ == "__main__":
    unittest.main()
