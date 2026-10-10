from __future__ import annotations

import json
import importlib
import tempfile
import unittest
from pathlib import Path

from webui.drafts import RICH_CONTENT_ATTR_ID, create_draft_from_url, to_ozon_import_item


def _make_draft(**overrides):
    """最小合法草稿，所有 validate_draft 必填字段均满足。"""
    base = {
        "id": 1,
        "ozon_title": "Органайзер для дома",
        "description": "Практичный органайзер для хранения.",
        "category_id": "17028922",
        "type_id": "94307",
        "price": "799",
        "old_price": "999",
        "weight_g": 500,
        "length_mm": 30,
        "width_mm": 20,
        "height_mm": 10,
        "images": ["https://example.test/a.jpg"],
        "source_url": "https://www.ozon.ru/product/test-123/",
        "source_offer_id": "123",
    }
    base.update(overrides)
    return base


class TestRichContentAttr(unittest.TestCase):
    """to_ozon_import_item 在 source_raw.rich_content_json 存在时追加 id=11254 属性。"""

    def test_rich_content_attr_present_when_source_raw_has_rcj(self):
        rcj = {"content": [{"blocks": [{"text": {"items": [{"content": "Привет", "type": "text"}]}}]}]}
        draft = _make_draft(source_raw={"rich_content_json": rcj})
        item = to_ozon_import_item(draft)
        attrs = item["attributes"]
        rich_attrs = [a for a in attrs if a.get("id") == RICH_CONTENT_ATTR_ID]
        self.assertEqual(len(rich_attrs), 1, "应有一个 id=11254 属性")
        attr = rich_attrs[0]
        self.assertEqual(attr["complex_id"], 0)
        value_str = attr["values"][0]["value"]
        # 值应是 JSON 字符串，且能被反序列化回原对象
        self.assertEqual(json.loads(value_str), rcj)

    def test_rich_content_attr_absent_when_no_source_raw(self):
        draft = _make_draft()  # 无 source_raw
        item = to_ozon_import_item(draft)
        rich_attrs = [a for a in item["attributes"] if a.get("id") == RICH_CONTENT_ATTR_ID]
        self.assertEqual(len(rich_attrs), 0, "无 source_raw 时不应出现 id=11254 属性")

    def test_rich_content_attr_absent_when_source_raw_has_no_rcj(self):
        draft = _make_draft(source_raw={"detail_images": ["https://ir.ozone.ru/d1.jpg"]})
        item = to_ozon_import_item(draft)
        rich_attrs = [a for a in item["attributes"] if a.get("id") == RICH_CONTENT_ATTR_ID]
        self.assertEqual(len(rich_attrs), 0, "source_raw 无 rich_content_json 时不应出现 id=11254 属性")

    def test_rich_content_json_is_compact_json_string(self):
        """值必须是 JSON 字符串（Ozon 校验 rich content JSON 作为字符串值传入）。"""
        rcj = {"content": [{"blocks": []}]}
        draft = _make_draft(source_raw={"rich_content_json": rcj, "detail_images": []})
        item = to_ozon_import_item(draft)
        attr = next(a for a in item["attributes"] if a.get("id") == RICH_CONTENT_ATTR_ID)
        value_str = attr["values"][0]["value"]
        self.assertIsInstance(value_str, str)
        # 应为紧凑格式（dumps_json 用 separators=(",", ":")）
        self.assertNotIn(" ", value_str)

    def test_source_raw_as_json_string_also_works(self):
        """store 可能把 source_raw 序列化为 JSON 字符串存储，loads_json 应能处理。"""
        rcj = {"content": []}
        import json as _json
        draft = _make_draft(source_raw=_json.dumps({"rich_content_json": rcj}))
        item = to_ozon_import_item(draft)
        rich_attrs = [a for a in item["attributes"] if a.get("id") == RICH_CONTENT_ATTR_ID]
        self.assertEqual(len(rich_attrs), 1)
        self.assertEqual(json.loads(rich_attrs[0]["values"][0]["value"]), rcj)


class TestMakeRichContent(unittest.TestCase):
    def test_wb_make_rich_content_uses_all_gallery_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            import webui.store as store_mod
            store_mod.DEFAULT_DB = Path(tmp) / "rich.db"
            import webui.app_service as svc
            importlib.reload(svc)
            app = svc.App()
            try:
                draft = create_draft_from_url(
                    "https://www.wildberries.ru/catalog/95070213/detail.aspx",
                    source_platform="wb",
                )
                draft.update({
                    "ozon_title": "WB 褌芯胁邪褉",
                    "description": "袨锌懈褋邪薪懈械",
                    "category_id": "17028922",
                    "type_id": "94307",
                    "price": "100",
                    "images": [],
                })
                saved = app.store.insert_draft(draft)
                images = [
                    "https://basket-05.wbbasket.ru/vol950/part95070/95070213/images/big/1.webp",
                    "https://basket-05.wbbasket.ru/vol950/part95070/95070213/images/big/2.webp",
                    "https://basket-05.wbbasket.ru/vol950/part95070/95070213/images/big/3.webp",
                ]
                for url in images:
                    app.store.add_draft_image(saved["id"], url, source="collected", in_gallery=1)

                result = app.make_rich_content(saved["id"])

                self.assertEqual(result["blocks"], 3)
                rich = result["draft"]["source_raw"]["rich_content_json"]
                got = [item["blocks"][0]["img"]["src"] for item in rich["content"]]
                self.assertEqual(got, images)
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
