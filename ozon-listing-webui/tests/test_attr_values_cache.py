from __future__ import annotations
import sys, unittest
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


if __name__ == "__main__":
    unittest.main()
