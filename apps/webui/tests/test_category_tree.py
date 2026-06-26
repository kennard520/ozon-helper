from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from webui.store import Store


class TestCatalogTreeCache(unittest.TestCase):
    def test_save_load_tree_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            self.assertIsNone(store.load_catalog_tree("ZH_HANS"))
            raw = [{"description_category_id": 1, "category_name": "家居",
                    "children": [{"type_id": 10, "type_name": "收纳箱"}]}]
            store.save_catalog_tree("ZH_HANS", raw)
            got = store.load_catalog_tree("ZH_HANS")
            self.assertEqual(got, raw)
            store.close()


from webui.catalog import Catalog


class _FakeStore:
    """最小 store 桩：记录 save/load 的拍平叶子与原始树。"""
    def __init__(self):
        self.leaves = None
        self.tree = None
    def load_catalog_leaves(self, lang): return self.leaves
    def save_catalog_leaves(self, lang, v): self.leaves = v
    def load_catalog_tree(self, lang): return self.tree
    def save_catalog_tree(self, lang, v): self.tree = v


class _FakeClient:
    def __init__(self, root): self._root = root; self.calls = 0
    def get_category_tree(self, language="ZH_HANS"):
        self.calls += 1
        return {"result": self._root}


SAMPLE_ROOT = [{
    "description_category_id": 1, "category_name": "家居",
    "children": [
        {"type_id": 10, "type_name": "收纳箱"},
        {"type_id": 11, "type_name": "停产", "disabled": True},
        {"description_category_id": 2, "category_name": "厨房",
         "children": [{"type_id": 20, "type_name": "餐具"}]},
    ],
}]


class TestCatalogTree(unittest.TestCase):
    def test_load_double_caches_tree_and_leaves(self):
        store = _FakeStore()
        client = _FakeClient(SAMPLE_ROOT)
        cat = Catalog(store=store, language="ZH_HANS")
        cat.load(client)
        self.assertIsNotNone(store.leaves)
        self.assertEqual(store.tree, SAMPLE_ROOT)
        self.assertEqual(client.calls, 1)

    def test_tree_builds_selectable_nodes(self):
        store = _FakeStore()
        client = _FakeClient(SAMPLE_ROOT)
        cat = Catalog(store=store, language="ZH_HANS")
        tree = cat.tree(client)
        home = tree[0]
        self.assertEqual(home["label"], "家居")
        self.assertTrue(home["disabled"])
        leaf = next(c for c in home["children"] if c["label"] == "收纳箱")
        self.assertEqual(leaf["value"], "1-10")
        self.assertFalse(leaf.get("disabled"))
        self.assertFalse(any(c["label"] == "停产" for c in home["children"]))
        kitchen = next(c for c in home["children"] if c["label"] == "厨房")
        self.assertEqual(kitchen["children"][0]["value"], "2-20")

    def test_tree_uses_cache_no_client(self):
        store = _FakeStore()
        store.tree = SAMPLE_ROOT
        cat = Catalog(store=store, language="ZH_HANS")
        self.assertTrue(cat.has_tree_cache())
        tree = cat.tree(None)
        self.assertEqual(tree[0]["label"], "家居")

    def test_tree_fetches_even_when_leaves_cached(self):
        # 回归：老用户已有叶子缓存但无树缓存时，tree() 必须强制拉取（否则 load 短路 → 返回空树）
        store = _FakeStore()
        store.leaves = [{"description_category_id": 1, "type_id": 10, "type_name": "x",
                         "path": "家居 / x", "disabled": False}]   # 预置叶子缓存
        # store.tree 仍为 None（无树缓存）
        client = _FakeClient(SAMPLE_ROOT)
        cat = Catalog(store=store, language="ZH_HANS")
        tree = cat.tree(client)
        self.assertTrue(len(tree) > 0)                 # 不能是空树
        self.assertEqual(tree[0]["label"], "家居")
        self.assertEqual(client.calls, 1)              # 确实拉了一次
        self.assertEqual(store.tree, SAMPLE_ROOT)      # 树缓存被回填


class TestCategoryTreeRoute(unittest.TestCase):
    def test_route_returns_tree(self):
        import importlib
        import shutil

        from fastapi.testclient import TestClient

        import webui.store as store_mod
        tmp = tempfile.mkdtemp()
        store_mod.DEFAULT_DB = Path(tmp) / "r.db"
        import webui.app_service as svc; importlib.reload(svc)
        import webui.main as main_mod; importlib.reload(main_mod)
        client = TestClient(main_mod.app)
        try:
            main_mod.APP.store.save_catalog_tree("ZH_HANS", [
                {"description_category_id": 1, "category_name": "家居",
                 "children": [{"type_id": 10, "type_name": "收纳箱"}]}])
            r = client.get("/api/category/tree")
            self.assertEqual(r.status_code, 200)
            tree = r.json()["tree"]
            self.assertEqual(tree[0]["label"], "家居")
            self.assertEqual(tree[0]["children"][0]["value"], "1-10")
        finally:
            main_mod.APP.store.close()
            shutil.rmtree(tmp, ignore_errors=True)
            store_mod.DEFAULT_DB = store_mod.Path(
                store_mod.os.environ.get("OZON_WEBUI_DB")
                or (store_mod.Path(__file__).resolve().parents[1] / "data" / "products.db"))
            importlib.reload(svc); importlib.reload(main_mod)


if __name__ == "__main__":
    unittest.main()
