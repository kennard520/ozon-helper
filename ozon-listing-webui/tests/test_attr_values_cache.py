from __future__ import annotations
import sys
import unittest
from pathlib import Path

# 让 `import ozon_api` 可用（ozon_api 在仓库根 = tests 的 parents[2]）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ozon_api.client import OzonSellerClient, SimpleResponse  # noqa: E402


class _FakeTransport:
    """记录每次请求并按顺序返回预设 JSON。"""
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls: list[dict] = []

    def request(self, *, method, url, headers, json, timeout):
        import json as _j
        self.calls.append({"url": url, "json": json})
        body = self.pages[len(self.calls) - 1]
        return SimpleResponse(status_code=200, text=_j.dumps(body))


class GetAttributeValuesTest(unittest.TestCase):
    def test_paginates_until_no_next(self):
        transport = _FakeTransport([
            {"result": [{"id": 1, "value": "красный"}, {"id": 2, "value": "синий"}], "has_next": True},
            {"result": [{"id": 3, "value": "зелёный"}], "has_next": False},
        ])
        c = OzonSellerClient("1", "k", transport=transport)
        out = c.get_attribute_values(100, 22, 99, language="RU", page_size=2, max_total=2000)
        self.assertFalse(out["oversized"])
        self.assertEqual([v["value"] for v in out["values"]], ["красный", "синий", "зелёный"])
        self.assertEqual([v["id"] for v in out["values"]], [1, 2, 3])
        self.assertTrue(transport.calls[0]["url"].endswith("/v1/description-category/attribute/values"))
        self.assertEqual(transport.calls[0]["json"]["last_value_id"], 0)
        self.assertEqual(transport.calls[1]["json"]["last_value_id"], 2)

    def test_oversized_stops_early(self):
        transport = _FakeTransport([
            {"result": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}, {"id": 3, "value": "c"}], "has_next": True},
        ])
        c = OzonSellerClient("1", "k", transport=transport)
        out = c.get_attribute_values(100, 22, 99, language="RU", page_size=100, max_total=2)
        self.assertTrue(out["oversized"])
        self.assertLessEqual(len(out["values"]), 2)  # 截断到 max_total，不返回超额

    def test_empty_attribute_single_call(self):
        transport = _FakeTransport([{"result": [], "has_next": False}])
        c = OzonSellerClient("1", "k", transport=transport)
        out = c.get_attribute_values(100, 22, 99, language="RU")
        self.assertEqual(out["values"], [])
        self.assertFalse(out["oversized"])
        self.assertEqual(len(transport.calls), 1)

    def test_single_page(self):
        transport = _FakeTransport([
            {"result": [{"id": 7, "value": "хлопок"}], "has_next": False},
        ])
        c = OzonSellerClient("1", "k", transport=transport)
        out = c.get_attribute_values(100, 22, 99, language="RU")
        self.assertEqual(out["values"], [{"id": 7, "value": "хлопок"}])
        self.assertFalse(out["oversized"])
        self.assertEqual(len(transport.calls), 1)


import backend.ozon_client_adapter as adapter  # noqa: E402


class AdapterGetAttributeValuesTest(unittest.TestCase):
    def test_forwards_to_client(self):
        captured = {}

        class _C:
            def get_attribute_values(self, cat, typ, aid, *, language, max_total):
                captured.update(cat=cat, typ=typ, aid=aid, language=language, max_total=max_total)
                return {"values": [{"id": 5, "value": "x"}], "oversized": False}

        orig = adapter._client
        adapter._client = lambda settings: _C()
        try:
            out = adapter.get_attribute_values({"ozon_client_id": "1", "ozon_api_key": "k"},
                                               100, 22, 99, language="RU", max_total=2000)
        finally:
            adapter._client = orig
        self.assertEqual(out["values"][0]["id"], 5)
        self.assertEqual(captured, {"cat": 100, "typ": 22, "aid": 99, "language": "RU", "max_total": 2000})


import tempfile  # noqa: E402
from backend.store import Store  # noqa: E402


class AttrValuesStoreTest(unittest.TestCase):
    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            self.assertIsNone(store.load_attr_values(100, 22, 99))
            vals = [{"id": 1, "value": "красный"}, {"id": 2, "value": "синий"}]
            store.save_attr_values(100, 22, 99, vals, False)
            got = store.load_attr_values(100, 22, 99)
            self.assertEqual(got, (vals, False))
            store.close()

    def test_oversized_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            store.save_attr_values(100, 22, 99, [], True)
            self.assertEqual(store.load_attr_values(100, 22, 99), ([], True))
            store.close()


import importlib  # noqa: E402


def _make_app(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import backend.app_service as svc
    importlib.reload(svc)
    app = svc.App()
    app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k"})
    return svc, app


class EnsureAttrValuesTest(unittest.TestCase):
    def test_fetches_then_caches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                calls = []

                def fake_get(settings, cat, typ, aid, *, language="RU", max_total=2000):
                    calls.append((cat, typ, aid))
                    return {"values": [{"id": 7, "value": "хлопок"}], "oversized": False}

                svc.get_attribute_values = fake_get
                vals, over = app._ensure_attr_values(100, 22, 99)
                self.assertEqual(vals, [{"id": 7, "value": "хлопок"}])
                self.assertFalse(over)
                # 第二次走缓存，不再调 get
                vals2, _ = app._ensure_attr_values(100, 22, 99)
                self.assertEqual(vals2, [{"id": 7, "value": "хлопок"}])
                self.assertEqual(len(calls), 1)
            finally:
                app.store.close()

    def test_oversized_cached_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                svc.get_attribute_values = lambda *a, **k: {"values": [{"id": 1, "value": "x"}], "oversized": True}
                vals, over = app._ensure_attr_values(100, 22, 99)
                self.assertEqual(vals, [])
                self.assertTrue(over)
                self.assertEqual(app.store.load_attr_values(100, 22, 99), ([], True))
            finally:
                app.store.close()

    def test_fetch_error_returns_empty_not_cached(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                def boom(*a, **k):
                    raise RuntimeError("limit")
                svc.get_attribute_values = boom
                self.assertEqual(app._ensure_attr_values(100, 22, 99), ([], False))
                self.assertIsNone(app.store.load_attr_values(100, 22, 99))  # 失败不写缓存
            finally:
                app.store.close()


class LocalMatchTest(unittest.TestCase):
    def test_exact_case_insensitive(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                vals = [{"id": 1, "value": "Красный"}, {"id": 2, "value": "Синий"}]
                self.assertEqual(app._local_match_value(vals, "красный"),
                                 {"dictionary_value_id": 1, "value": "Красный"})
                self.assertEqual(app._local_match_value(vals, "  СИНИЙ "),
                                 {"dictionary_value_id": 2, "value": "Синий"})
                self.assertIsNone(app._local_match_value(vals, "зелёный"))
                self.assertIsNone(app._local_match_value(vals, "a"))  # <2 字符
            finally:
                app.store.close()


class ResolveValuesTest(unittest.TestCase):
    def test_resolves_via_live_search(self):
        # _resolve_values 现在只走实时搜(不用俄文本地缓存:AI出俄文值、中文字典不全)——即便有缓存也搜
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app.store.save_attr_values(100, 22, 99, [{"id": 5, "value": "Хлопок"}], False)
                calls = []

                def fake_search(settings, cat, typ, aid, value, language="RU"):
                    calls.append(value)
                    return {"result": [{"id": 5, "value": "Хлопок"}]}
                svc.search_attribute_values = fake_search
                out = app._resolve_values(100, 22, 99, ["хлопок"], False)
                self.assertEqual(out, [{"dictionary_value_id": 5, "value": "Хлопок"}])
                self.assertEqual(calls, ["хлопок"])
            finally:
                app.store.close()

    def test_local_miss_falls_back_to_search(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app.store.save_attr_values(100, 22, 99, [{"id": 5, "value": "Хлопок"}], False)
                calls = []

                def fake_search(settings, cat, typ, aid, value, language="RU"):
                    calls.append(value)
                    return {"result": [{"id": 8, "value": "Шёлк"}]}
                svc.search_attribute_values = fake_search
                out = app._resolve_values(100, 22, 99, ["шёлк"], False)
                self.assertEqual(out, [{"dictionary_value_id": 8, "value": "Шёлк"}])
                self.assertEqual(calls, ["шёлк"])
            finally:
                app.store.close()


class ResolvePairsConcurrentTest(unittest.TestCase):
    def test_resolves_each_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                ids = {"красный": 1, "малый": 2}

                def fake_search(settings, cat, typ, aid, value, language="RU"):
                    return {"result": [{"id": ids[value.lower()], "value": value.capitalize()}]}
                svc.search_attribute_values = fake_search
                res = app._resolve_pairs_concurrent(100, 22, [
                    (11, ["красный"], False),
                    (22, ["малый"], False),
                ])
                self.assertEqual(res[11], [{"dictionary_value_id": 1, "value": "Красный"}])
                self.assertEqual(res[22], [{"dictionary_value_id": 2, "value": "Малый"}])
            finally:
                app.store.close()

    def test_empty_tasks(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                self.assertEqual(app._resolve_pairs_concurrent(100, 22, []), {})
            finally:
                app.store.close()


class CollectTriggersAutoMapTest(unittest.TestCase):
    def test_ext_collect_parsed_calls_auto_map(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                seen = []
                app._auto_map_safe = lambda did: seen.append(did)
                # 跳过类目自动匹配的外部依赖
                app._auto_match_category = lambda scraped: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/x-1/",
                                              "data": {"title": "t"}})
                created = res.get("created") or []
                self.assertTrue(created)
                self.assertEqual(seen, [created[0]["id"]])  # 新建草稿后调了一次自动映射
            finally:
                app.store.close()


class ConcurrentContextVarTest(unittest.TestCase):
    def test_propagates_current_user_to_threads(self):
        # ThreadPoolExecutor 默认不传播 ContextVar；_resolve_pairs_concurrent 用 copy_context
        # 确保子线程能看到父线程设的 current_user_id（否则多用户下会用错 Ozon 凭证）。
        from backend.store import current_user_id  # noqa: PLC0415
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                seen = {}

                def fake_resolve(cat, typ, aid, texts, is_coll):
                    seen[aid] = current_user_id.get()
                    return []
                app._resolve_values = fake_resolve
                token = current_user_id.set(42)
                try:
                    app._resolve_pairs_concurrent(100, 22, [(11, ["x"], False), (22, ["y"], False)])
                finally:
                    current_user_id.reset(token)
                self.assertEqual(seen, {11: 42, 22: 42})  # 子线程看到父线程设的 user 42（非默认 1）
            finally:
                app.store.close()


class ForceCountryChinaTest(unittest.TestCase):
    def test_fills_china_when_category_has_country_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                def fake_resolve(cat, typ, aid, texts, is_coll):
                    if texts == ["Китай"]:
                        return [{"dictionary_value_id": 999, "value": "Китай"}]
                    return [{"dictionary_value_id": 1, "value": texts[0]}]
                app._resolve_values = fake_resolve
                meta = [{"id": 4389, "name": "Страна-изготовитель"}, {"id": 100, "name": "Цвет"}]
                publish, mapped = {}, []
                # 即使竞品已把原产国填成别的，也要被覆盖成中国
                publish[4389] = {"id": 4389, "values": [{"dictionary_value_id": 7, "value": "Россия"}]}
                app._force_country_to_china(100, 22, meta, publish, mapped)
                self.assertEqual(publish[4389], {"id": 4389, "values": [{"dictionary_value_id": 999, "value": "Китай"}]})
            finally:
                app.store.close()

    def test_noop_when_no_country_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._resolve_values = lambda *a, **k: [{"dictionary_value_id": 1, "value": "x"}]
                meta = [{"id": 100, "name": "Цвет"}]
                publish = {}
                app._force_country_to_china(100, 22, meta, publish, [])
                self.assertEqual(publish, {})
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
