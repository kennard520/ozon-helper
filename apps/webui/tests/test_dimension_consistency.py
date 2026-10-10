"""
尺寸单位一致性测试 — 确认各来源路径都以**毫米**写入内部列，发布时直发(不换算)。

  1. ozon_client_adapter.ozon_to_draft : Ozon 拉取 → 内部 mm（_to_mm 归一）
  2. 插件采集 1688/WB/Ozon              : 归一成 mm（见 ext 测试 parse-1688/wb/product-parse）
  3. drafts.to_ozon_import_item        : 内部 mm 直发 → Ozon mm（不再 ×10）

(ai_card.generate_card length_cm=20→length_mm=200 已在 test_ai_card.py 覆盖，此处仅加注释。)
"""
from __future__ import annotations

import unittest


# ---------------------------------------------------------------------------
# 1. Ozon 拉取路径：任意单位 → 内部 mm
# ---------------------------------------------------------------------------
class OzonPullDimsTest(unittest.TestCase):
    """ozon_to_draft: depth=200mm, width=150mm, height=100mm → 内部 200/150/100 mm"""

    def test_to_mm(self) -> None:
        from webui.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415

        info = {
            "id": 1, "offer_id": "X", "name": "Тест", "price": "100",
            "old_price": "120", "currency_code": "RUB",
            "description_category_id": 17028922, "type_id": 94307,
            "primary_image": ["https://img/p.jpg"], "images": [],
            "stocks": {"stocks": [{"present": 1, "reserved": 0}]},
        }
        attrs = {
            "id": 1, "offer_id": "X",
            "description_category_id": 17028922, "type_id": 94307,
            "weight": 500, "weight_unit": "g",
            "depth": 200, "width": 150, "height": 100,
            "dimension_unit": "mm",
            "attributes": [],
        }
        d = ozon_to_draft(info, attrs)
        self.assertEqual(d["length_mm"], 200, "200mm → 200mm")
        self.assertEqual(d["width_mm"], 150, "150mm → 150mm")
        self.assertEqual(d["height_mm"], 100, "100mm → 100mm")

    def test_cm_unit_to_mm(self) -> None:
        from webui.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415

        info = {
            "id": 1, "offer_id": "X", "name": "Тест", "price": "100",
            "currency_code": "RUB", "description_category_id": 1, "type_id": 1,
            "primary_image": ["https://img/p.jpg"], "images": [],
            "stocks": {"stocks": [{"present": 1, "reserved": 0}]},
        }
        attrs = {
            "id": 1, "offer_id": "X", "description_category_id": 1, "type_id": 1,
            "weight": 500, "weight_unit": "g",
            "depth": 20, "width": 15, "height": 10, "dimension_unit": "cm",
            "attributes": [],
        }
        d = ozon_to_draft(info, attrs)
        self.assertEqual(d["length_mm"], 200, "20cm → 200mm")


# ---------------------------------------------------------------------------
# 2. 发布路径：to_ozon_import_item 内部 mm 直发 → Ozon mm
# ---------------------------------------------------------------------------
class PublishDimsTest(unittest.TestCase):
    """to_ozon_import_item: length_mm=200 (mm) → depth=200 mm 给 Ozon（不换算）"""

    def test_mm_direct_on_publish(self) -> None:
        from webui.drafts import create_draft_from_url, to_ozon_import_item  # noqa: PLC0415

        draft = create_draft_from_url("https://detail.1688.com/offer/999888777666.html")
        draft.update({
            "id": 1,
            "ozon_title": "Органайзер",
            "description": "Описание.",
            "category_id": "17028922",
            "type_id": "94307",
            "price": "500",
            "weight_g": 500,
            "length_mm": 200,   # 内部 mm
            "width_mm": 150,
            "height_mm": 100,
            "images": ["https://example.test/img.jpg"],
            "attributes": [{"id": 85, "values": [{"value": "Нет бренда"}]}],
        })
        item = to_ozon_import_item(draft)
        self.assertEqual(item["depth"], 200, "200mm 直发")
        self.assertEqual(item["width"], 150)
        self.assertEqual(item["height"], 100)
        self.assertEqual(item["dimension_unit"], "mm")


if __name__ == "__main__":
    unittest.main()
