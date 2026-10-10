from __future__ import annotations
import unittest
from ozon_api.client import OzonSellerClient


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses  # path -> dict
        self.calls = []
    def request(self, *, method, url, headers, json, timeout):
        path = url.split("ozon.ru")[-1]
        self.calls.append((path, json))
        from ozon_api.client import SimpleResponse
        import json as J
        return SimpleResponse(status_code=200, text=J.dumps(self.responses.get(path, {})))


class ProductPullTest(unittest.TestCase):
    def _client(self, responses):
        return OzonSellerClient("cid", "key", transport=FakeTransport(responses))

    def test_list_products_payload_and_parse(self):
        c = self._client({"/v3/product/list": {"result": {"items": [
            {"product_id": 1, "offer_id": "A"}], "last_id": "L1", "total": 1}}})
        r = c.list_products(visibility="ALL", last_id="", limit=100)
        self.assertEqual(r["result"]["items"][0]["offer_id"], "A")
        # 校验请求体
        path, body = c.transport.calls[0]
        self.assertEqual(path, "/v3/product/list")
        self.assertEqual(body["filter"]["visibility"], "ALL")
        self.assertEqual(body["limit"], 100)

    def test_get_products_info_by_offer_ids(self):
        c = self._client({"/v3/product/info/list": {"items": [{"offer_id": "A", "name": "Товар"}]}})
        r = c.get_products_info(offer_ids=["A"])
        self.assertEqual(r["items"][0]["name"], "Товар")
        self.assertEqual(c.transport.calls[0][1], {"offer_id": ["A"]})

    def test_get_products_attributes_by_offer_ids(self):
        c = self._client({"/v4/product/info/attributes": {"result": [
            {"offer_id": "A", "weight": 500, "attributes": []}], "last_id": "", "total": "1"}})
        r = c.get_products_attributes(offer_ids=["A"], last_id="", limit=100)
        self.assertEqual(r["result"][0]["weight"], 500)
        path, body = c.transport.calls[0]
        self.assertEqual(path, "/v4/product/info/attributes")
        self.assertEqual(body["filter"]["offer_id"], ["A"])


if __name__ == "__main__":
    unittest.main()


class ListWarehousesPathTest(unittest.TestCase):
    def test_uses_v2_endpoint(self) -> None:
        # /v1 已废弃（obsolete method）→ 必须打 /v2/warehouse/list
        c = OzonSellerClient("cid", "key", transport=FakeTransport(
            {"/v2/warehouse/list": {"result": []}}))
        c.list_warehouses()
        self.assertEqual(c.transport.calls[0][0], "/v2/warehouse/list")
