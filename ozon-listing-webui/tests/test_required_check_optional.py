from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import backend.store as store_mod


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u", "source_offer_id": "1",
        "source_title": "t", "ozon_title": "Товар", "description": "d",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["x"], "attributes": {}, "status": "draft",
        "publish_response": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over)
    return d


# 模拟某类目的属性表：必填(型号名/品牌85) + 可选(颜色/材质)
FAKE_ATTRS = [
    {"id": 9048, "name": "Название модели", "is_required": True, "dictionary_id": 0},
    {"id": 85, "name": "Бренд", "is_required": True, "dictionary_id": 28732},
    {"id": 4194, "name": "Тип", "is_required": True, "dictionary_id": 91022},
    {"id": 10096, "name": "Цвет", "is_required": False, "dictionary_id": 12345},
    {"id": 8229, "name": "Материал", "is_required": False, "dictionary_id": 0},
]


class TestRequiredCheckOptional(unittest.TestCase):
    def _app(self, tmp: str):
        import importlib  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "rc.db"
        import backend.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        app = svc.App()
        app._category_attrs = lambda cat, typ, language="ZH_HANS": FAKE_ATTRS  # 桩掉网络
        return app

    def test_optional_returned_and_brand_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                res = app.required_check(d["id"])
                req_ids = {a["id"] for a in res["required"]}
                opt_ids = {a["id"] for a in res["optional"]}
                # 必填含型号名/类型；品牌(85)已从必填排除(写死"无品牌"，不让用户填)
                self.assertEqual(req_ids, {9048, 4194})
                # 可选含颜色/材质，且不含品牌(85)
                self.assertEqual(opt_ids, {10096, 8229})
                self.assertNotIn(85, opt_ids)
            finally:
                app.store.close()

    def test_no_category_returns_empty_optional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft(category_id="", type_id=""))
                res = app.required_check(d["id"])
                self.assertEqual(res["optional"], [])
                self.assertEqual(res["required"], [])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()


class TestCategoryDependentExcluded(unittest.TestCase):
    """category_dependent 属性（如"类型"，由 type_id 表达）不算必填缺失、不进展示。"""
    def _app(self, tmp):
        import importlib
        store_mod.DEFAULT_DB = Path(tmp) / "cd.db"
        import backend.app_service as svc
        importlib.reload(svc)
        app = svc.App()
        app._category_attrs = lambda cat, typ, language="ZH_HANS": [
            {"id": 8229, "name": "类型", "is_required": True, "dictionary_id": 1960, "category_dependent": True},
            {"id": 9048, "name": "型号名称", "is_required": True, "dictionary_id": 0, "category_dependent": False},
        ]
        return app

    def test_category_dependent_not_missing_not_shown(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                res = app.required_check(d["id"])
                req_ids = {a["id"] for a in res["required"]}
                miss_ids = {m["id"] for m in res["missing"]}
                self.assertNotIn(8229, req_ids)      # 类型不展示
                self.assertNotIn(8229, miss_ids)      # 类型不算缺失
                self.assertIn(9048, req_ids)          # 普通必填仍在
                self.assertIn(9048, miss_ids)         # 型号名未填仍报缺
            finally:
                app.store.close()
