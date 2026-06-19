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


if __name__ == "__main__":
    unittest.main()
