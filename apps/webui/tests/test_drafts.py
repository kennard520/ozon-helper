from __future__ import annotations

import unittest

from webui.drafts import (
    BRAND_ATTR_ID,
    NO_BRAND,
    create_draft_from_url,
    dimension_warnings,
    extract_offer_id,
    offer_id_for,
    to_ozon_import_item,
    validate_draft,
)


class DimensionSoftCheckTest(unittest.TestCase):
    _BASE = {"ozon_title": "Товар", "description": "D", "category_id": "1", "type_id": "2",
             "price": "10", "stock": 1, "images": ["https://x/a.jpg"]}

    def test_validate_draft_does_not_block_on_missing_dims(self):
        # 无克重/尺寸 → validate_draft 不再报错（改软警告）
        self.assertEqual(validate_draft(self._BASE), [])

    def test_dimension_warnings_flag_missing(self):
        ws = dimension_warnings(self._BASE)
        self.assertTrue(any("克重" in w for w in ws))
        self.assertTrue(any("长" in w for w in ws))

    def test_dimension_warnings_empty_when_filled(self):
        full = {**self._BASE, "weight_g": 100, "length_mm": 100, "width_mm": 100, "height_mm": 100}
        self.assertEqual(dimension_warnings(full), [])


class OfferIdForTest(unittest.TestCase):
    def test_prefers_explicit_offer_id_column(self) -> None:
        # 已存的 offer_id 列优先（发布后会回写，功能⑤按它 JOIN）
        self.assertEqual(
            offer_id_for({"offer_id": "SKU-1", "source_offer_id": "999", "id": 7}),
            "SKU-1",
        )

    def test_falls_back_to_source_offer_id(self) -> None:
        self.assertEqual(offer_id_for({"offer_id": "", "source_offer_id": "999", "id": 7}), "999")

    def test_falls_back_to_manual_id(self) -> None:
        self.assertEqual(offer_id_for({"id": 7}), "manual-7")


class DraftsTest(unittest.TestCase):
    def test_extract_offer_id_from_1688_url(self) -> None:
        self.assertEqual(
            extract_offer_id("https://detail.1688.com/offer/123456789012.html"),
            "123456789012",
        )

    def test_extract_offer_id_from_ozon_url(self) -> None:
        # 纯数字 SKU 路径
        self.assertEqual(extract_offer_id("https://www.ozon.ru/product/4585365823/"), "4585365823")
        # slug + SKU 路径，取末尾数字段
        self.assertEqual(
            extract_offer_id("https://www.ozon.ru/product/renu-360-1117478728/"), "1117478728"
        )
        # slug 含中间数字 + query，仍取末尾 SKU
        self.assertEqual(
            extract_offer_id("https://www.ozon.ru/product/mylo-12-sht-120-g-1004954569690/?from=x"),
            "1004954569690",
        )

    def test_create_draft_from_ozon_url_captures_sku(self) -> None:
        draft = create_draft_from_url(
            "https://www.ozon.ru/product/renu-360-1117478728/", source_platform="ozon"
        )
        self.assertEqual(draft["source_offer_id"], "1117478728")
        self.assertEqual(draft["source_url"], "https://www.ozon.ru/product/renu-360-1117478728/")

    def test_create_draft_from_url_normalizes_and_preserves_offer_id(self) -> None:
        draft = create_draft_from_url("detail.1688.com/offer/123456789012.html", source_platform="1688")

        self.assertEqual(draft["source_url"], "https://detail.1688.com/offer/123456789012.html")
        self.assertEqual(draft["source_offer_id"], "123456789012")
        self.assertEqual(draft["source_platform"], "1688")
        self.assertEqual(draft["purchase_url"], "https://detail.1688.com/offer/123456789012.html")
        self.assertEqual(draft["purchase_note"], "")
        self.assertEqual(draft["status"], "draft")

    def test_create_draft_accepts_ozon_source_with_separate_purchase_url(self) -> None:
        draft = create_draft_from_url("https://www.ozon.ru/product/demo-123/", source_platform="ozon")

        self.assertEqual(draft["source_url"], "https://www.ozon.ru/product/demo-123/")
        self.assertIsNone(draft["source_offer_id"])
        self.assertEqual(draft["source_platform"], "ozon")
        self.assertEqual(draft["purchase_url"], "")
        self.assertEqual(draft["purchase_note"], "")

    def test_create_draft_always_defaults_to_no_brand(self) -> None:
        draft = create_draft_from_url(
            "https://detail.1688.com/offer/123456789012.html",
            scraped={"brand_name": "Nike", "brand_id": 123},
        )

        self.assertIsNone(draft["brand_id"])
        self.assertEqual(draft["brand_name"], NO_BRAND)

    def test_validate_draft_reports_required_fields(self) -> None:
        draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")

        self.assertIn("Ozon俄语标题不能为空", validate_draft(draft))

    def test_validate_draft_blocks_title_without_cyrillic(self) -> None:
        draft = {**DimensionSoftCheckTest._BASE, "ozon_title": "Wireless holder"}

        errors = validate_draft(draft)

        self.assertTrue(any("标题必须包含俄语西里尔字符" in e for e in errors))

    def test_validate_draft_blocks_forbidden_russian_ad_words(self) -> None:
        draft = {**DimensionSoftCheckTest._BASE, "ozon_title": "Лучший органайзер №1"}

        errors = validate_draft(draft)

        self.assertTrue(any("违禁广告词" in e and "лучший" in e for e in errors))
        self.assertTrue(any("违禁广告词" in e and "№1" in e for e in errors))

    def test_validate_draft_blocks_blacklisted_brand_in_title(self) -> None:
        draft = {**DimensionSoftCheckTest._BASE, "ozon_title": "Чехол для iPhone"}

        errors = validate_draft(draft)

        self.assertTrue(any("未授权品牌" in e and "iphone" in e.lower() for e in errors))
        self.assertTrue(any(NO_BRAND in e for e in errors))

    def test_validate_draft_blocks_any_non_no_brand_value(self) -> None:
        draft = {**DimensionSoftCheckTest._BASE, "brand_name": "Nike"}

        errors = validate_draft(draft)

        self.assertTrue(any("未授权品牌" in e and "Nike" in e for e in errors))

    def test_validate_draft_description_or_rich_content(self) -> None:
        base = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
        base.update({
            "ozon_title": "Чемодан",
            "category_id": "17028922",
            "type_id": "94307",
            "price": "799",
            "weight_g": 500,
            "length_mm": 30,
            "width_mm": 20,
            "height_mm": 10,
            "images": ["https://example.test/a.jpg"],
        })

        # 既无描述也无富文本 → 报错
        no_desc = dict(base, description="")
        self.assertTrue(any("描述" in e for e in validate_draft(no_desc)))

        # 无描述但有富文本(source_raw.rich_content_json) → 不报描述错
        with_rich = dict(base, description="", source_raw={"rich_content_json": {"content": [{"blocks": []}]}})
        self.assertFalse(any("描述" in e for e in validate_draft(with_rich)))

        # source_raw 以字符串形式存储也能识别
        with_rich_str = dict(base, description="", source_raw='{"rich_content_json": {"content": []}}')
        self.assertFalse(any("描述" in e for e in validate_draft(with_rich_str)))

    def test_to_ozon_import_item_converts_ready_draft(self) -> None:
        draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
        draft.update({
            "id": 1,
            "ozon_title": "Органайзер для дома",
            "description": "Практичный органайзер для хранения.",
            "category_id": "17028922",
            "type_id": "94307",
            "price": "799",
            "old_price": "999",
            "weight_g": 500,
            "length_mm": 300,   # 内部存毫米
            "width_mm": 200,
            "height_mm": 100,
            "images": ["https://example.test/a.jpg"],
            "attributes": [{"id": 85, "values": [{"value": "Нет бренда"}]}],
        })

        item = to_ozon_import_item(draft)

        self.assertEqual(item["offer_id"], "123456789012")
        self.assertEqual(item["name"], "Органайзер для дома")
        self.assertEqual(item["description_category_id"], 17028922)
        self.assertEqual(item["type_id"], 94307)
        self.assertEqual(item["weight"], 500)
        self.assertEqual(item["depth"], 300)   # 300mm 直发
        self.assertEqual(item["width"], 200)
        self.assertEqual(item["height"], 100)
        self.assertEqual(item["currency_code"], "RUB")
        self.assertEqual(item["dimension_unit"], "mm")
        self.assertEqual(item["images"], ["https://example.test/a.jpg"])
        # 无视频 → 不带 complex_attributes
        self.assertNotIn("complex_attributes", item)

    def test_to_ozon_import_item_includes_video_complex_attribute(self) -> None:
        draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
        draft.update({
            "id": 1, "ozon_title": "Микрофон", "description": "Опис",
            "category_id": "17028922", "type_id": "94307", "price": "799",
            "weight_g": 500, "length_mm": 300, "width_mm": 200, "height_mm": 100,
            "images": ["https://example.test/a.jpg"],
            "video_url": "https://cdn.example/v.mp4",
        })
        item = to_ozon_import_item(draft)
        ca = item["complex_attributes"][0]["attributes"]
        url_attr = next(a for a in ca if a["id"] == 21841)
        name_attr = next(a for a in ca if a["id"] == 21837)
        self.assertEqual(url_attr["complex_id"], 100001)
        self.assertEqual(url_attr["values"][0]["value"], "https://cdn.example/v.mp4")
        self.assertEqual(name_attr["values"][0]["value"], "Микрофон")

    def test_to_ozon_import_item_skips_known_low_res_wb_video(self) -> None:
        draft = create_draft_from_url("https://www.wildberries.ru/catalog/502312325/detail.aspx", source_platform="wb")
        draft.update({
            "id": 1, "ozon_title": "Детектор газа", "description": "Описание",
            "category_id": "17028922", "type_id": "94307", "price": "799",
            "weight_g": 500, "length_mm": 300, "width_mm": 200, "height_mm": 100,
            "images": ["https://example.test/a.jpg"],
            "video_url": "http://8.152.196.119:8585/oss/ozon-media/rehosted.mp4",
            "source_raw": {
                "video_url": "https://videonme-basket-11.wbbasket.ru/vol129/part90154/901541649/mp4/360p/1.mp4",
            },
        })

        item = to_ozon_import_item(draft)

        self.assertNotIn("complex_attributes", item)

    def test_to_ozon_import_item_does_not_passthrough_collected_brand_attr(self) -> None:
        draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
        draft.update({
            "id": 1,
            "ozon_title": "Органайзер",
            "description": "Описание",
            "category_id": "17028922",
            "type_id": "94307",
            "price": "799",
            "weight_g": 500,
            "length_mm": 300,
            "width_mm": 200,
            "height_mm": 100,
            "images": ["https://example.test/a.jpg"],
            "attributes": [
                {"id": BRAND_ATTR_ID, "values": [{"dictionary_value_id": 1, "value": "Nike"}]},
                {"id": 9048, "values": [{"value": "Model X"}]},
            ],
        })

        item = to_ozon_import_item(draft)

        published_ids = {a["id"] for a in item["attributes"]}
        self.assertNotIn(BRAND_ATTR_ID, published_ids)
        self.assertIn(9048, published_ids)

    def test_to_ozon_import_item_dedupes_duplicate_attribute_ids(self) -> None:
        draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
        draft.update({
            "id": 1,
            "ozon_title": DimensionSoftCheckTest._BASE["ozon_title"],
            "description": DimensionSoftCheckTest._BASE["description"],
            "category_id": "17028922",
            "type_id": "94307",
            "price": "799",
            "weight_g": 500,
            "length_mm": 300,
            "width_mm": 200,
            "height_mm": 100,
            "images": ["https://example.test/a.jpg"],
            "attributes": [
                {"id": 4191, "values": [{"value": "old intro"}]},
                {"id": 4191, "values": [{"value": "new intro"}]},
                {"id": 9048, "values": [{"value": "Model X"}]},
            ],
        })

        item = to_ozon_import_item(draft)

        intro_attrs = [a for a in item["attributes"] if a["id"] == 4191]
        self.assertEqual(len(intro_attrs), 1)
        self.assertEqual(intro_attrs[0]["values"][0]["value"], "new intro")


class TestWbExtractOfferId(unittest.TestCase):
    def test_wb_catalog_url(self):
        from webui.drafts import extract_offer_id
        self.assertEqual(
            extract_offer_id("https://www.wildberries.ru/catalog/306432960/detail.aspx"),
            "306432960",
        )

    def test_wb_platform_name(self):
        from webui.drafts import create_draft_from_url
        d = create_draft_from_url(
            "https://www.wildberries.ru/catalog/306432960/detail.aspx",
            source_platform="wb",
        )
        self.assertEqual(d["source_offer_id"], "306432960")
        self.assertEqual(d["purchase_url"], "")              # WB 非货源
        self.assertIn("WB", d["source_title"])               # 兜底名「WB商品 306432960」


if __name__ == "__main__":
    unittest.main()
