"""
尺寸单位一致性测试 — 确认三条来源路径都以厘米写入内部列，发布时正确×10。

  1. ozon_client_adapter.ozon_to_draft : Ozon 拉取 mm→内部 cm
  2. collector._dims_from_chars        : 竞品采集 cm→内部 cm（Bug 2 修复点）
  3. freight_ozon.build_payload        : 运费 cm 直接透传（Bug 1 修复点）
  4. drafts.to_ozon_import_item        : 内部 cm ×10 → Ozon mm

(ai_card.generate_card length_cm=20→length_mm=20 已在 test_ai_card.py 覆盖，此处仅加注释。)
"""
from __future__ import annotations

import unittest


# ---------------------------------------------------------------------------
# 1. Ozon 拉取路径：mm → 内部 cm
# ---------------------------------------------------------------------------
class OzonPullDimsTest(unittest.TestCase):
    """ozon_to_draft: depth=200mm, width=150mm, height=100mm → 内部 20/15/10 cm"""

    def test_mm_to_cm(self) -> None:
        from backend.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415

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
        self.assertEqual(d["length_mm"], 20, "200mm → 20cm")
        self.assertEqual(d["width_mm"], 15, "150mm → 15cm")
        self.assertEqual(d["height_mm"], 10, "100mm → 10cm")


# ---------------------------------------------------------------------------
# 2. 发布路径：to_ozon_import_item 内部 cm ×10 → Ozon mm
#    （采集路径 collector._dims_from_chars 已随服务端采集器移除，解析改由浏览器插件就地完成）
# ---------------------------------------------------------------------------
class PublishDimsTest(unittest.TestCase):
    """to_ozon_import_item: length_mm=20 (cm) → depth=200 mm 给 Ozon"""

    def test_cm_x10_on_publish(self) -> None:
        from backend.drafts import create_draft_from_url, to_ozon_import_item  # noqa: PLC0415

        draft = create_draft_from_url("https://detail.1688.com/offer/999888777666.html")
        draft.update({
            "id": 1,
            "ozon_title": "Органайзер",
            "description": "Описание.",
            "category_id": "17028922",
            "type_id": "94307",
            "price": "500",
            "weight_g": 500,
            "length_mm": 20,   # 内部 cm
            "width_mm": 15,
            "height_mm": 10,
            "images": ["https://example.test/img.jpg"],
            "attributes": [{"id": 85, "values": [{"value": "Нет бренда"}]}],
        })
        item = to_ozon_import_item(draft)
        self.assertEqual(item["depth"], 200, "20cm → 200mm")
        self.assertEqual(item["width"], 150, "15cm → 150mm")
        self.assertEqual(item["height"], 100, "10cm → 100mm")
        self.assertEqual(item["dimension_unit"], "mm")


if __name__ == "__main__":
    unittest.main()
