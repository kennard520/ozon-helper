from __future__ import annotations
import importlib
import tempfile
import unittest
from pathlib import Path


def _make_app(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import backend.app_service as svc
    importlib.reload(svc)
    return svc.App()


META = [{"id": 9048, "name": "Модель"}, {"id": 4180, "name": "Тип"}]


class FillModelNameTest(unittest.TestCase):
    def test_fills_unique_random_for_single(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = _make_app(tmp)
            try:
                pub, mapped = {}, []
                app._fill_model_name(META, {"source_raw": {}}, pub, mapped)
                self.assertIn(9048, pub)
                val = pub[9048]["values"][0]["value"]
                self.assertTrue(val.startswith("M-"))
                self.assertTrue(any(m["id"] == 9048 for m in mapped))
            finally:
                app.store.close()

    def test_two_singles_get_different_values(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = _make_app(tmp)
            try:
                p1, p2 = {}, {}
                app._fill_model_name(META, {"source_raw": {}}, p1, [])
                app._fill_model_name(META, {"source_raw": {}}, p2, [])
                self.assertNotEqual(p1[9048]["values"][0]["value"], p2[9048]["values"][0]["value"])
            finally:
                app.store.close()

    def test_skips_when_already_set(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = _make_app(tmp)
            try:
                pub = {9048: {"id": 9048, "values": [{"value": "KEEP"}]}}
                app._fill_model_name(META, {"source_raw": {}}, pub, [])
                self.assertEqual(pub[9048]["values"][0]["value"], "KEEP")  # 不覆盖
            finally:
                app.store.close()

    def test_skips_variant_group(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = _make_app(tmp)
            try:
                pub, mapped = {}, []
                app._fill_model_name(META, {"source_raw": {"variant_group": "SKU123"}}, pub, mapped)
                self.assertNotIn(9048, pub)  # 变体组不填，留给合并发布统一填
            finally:
                app.store.close()

    def test_skips_when_category_lacks_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = _make_app(tmp)
            try:
                pub = {}
                app._fill_model_name([{"id": 4180, "name": "Тип"}], {"source_raw": {}}, pub, [])
                self.assertNotIn(9048, pub)  # 类目没有 9048 → 不塞
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
