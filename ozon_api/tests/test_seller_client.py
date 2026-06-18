from __future__ import annotations

import unittest

from ozon_api.client import OzonApiError, OzonSellerClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


class FakeTransport:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.response = response or FakeResponse(200, {"result": "ok"})
        self.calls: list[dict] = []

    def request(self, *, method: str, url: str, headers: dict, json: dict, timeout: float) -> FakeResponse:
        self.calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return self.response


class OzonSellerClientTest(unittest.TestCase):
    def test_request_posts_json_with_ozon_auth_headers(self) -> None:
        transport = FakeTransport(FakeResponse(200, {"result": {"ok": True}}))
        client = OzonSellerClient("123", "secret", transport=transport, base_url="https://example.test")

        result = client.request("/v1/warehouse/list", {"hello": "world"})

        self.assertEqual(result, {"result": {"ok": True}})
        self.assertEqual(transport.calls, [{
            "method": "POST",
            "url": "https://example.test/v1/warehouse/list",
            "headers": {
                "Client-Id": "123",
                "Api-Key": "secret",
                "Content-Type": "application/json",
            },
            "json": {"hello": "world"},
            "timeout": 30.0,
        }])

    def test_request_raises_api_error_with_status_and_body(self) -> None:
        transport = FakeTransport(FakeResponse(403, {"message": "bad key"}, text="forbidden"))
        client = OzonSellerClient("123", "bad", transport=transport)

        with self.assertRaises(OzonApiError) as ctx:
            client.request("/v1/warehouse/list", {})

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.payload, {"message": "bad key"})
        self.assertIn("403", str(ctx.exception))
        self.assertIn("bad key", str(ctx.exception))

    def test_import_products_wraps_items_for_product_import(self) -> None:
        transport = FakeTransport()
        client = OzonSellerClient("123", "secret", transport=transport)

        client.import_products([{"offer_id": "A1", "name": "Test"}])

        self.assertTrue(transport.calls[0]["url"].endswith("/v3/product/import"))
        self.assertEqual(transport.calls[0]["json"], {"items": [{"offer_id": "A1", "name": "Test"}]})

    def test_list_unfulfilled_fbs_builds_filter_payload(self) -> None:
        transport = FakeTransport()
        client = OzonSellerClient("123", "secret", transport=transport)

        client.list_unfulfilled_fbs(
            limit=50,
            offset=100,
            status="awaiting_deliver",
            since="2026-05-01T00:00:00Z",
            to="2026-05-29T23:59:59Z",
        )

        self.assertTrue(transport.calls[0]["url"].endswith("/v3/posting/fbs/unfulfilled/list"))
        self.assertEqual(transport.calls[0]["json"], {
            "dir": "ASC",
            "filter": {
                "cutoff_from": "2026-05-01T00:00:00Z",
                "cutoff_to": "2026-05-29T23:59:59Z",
                "status": "awaiting_deliver",
            },
            "limit": 50,
            "offset": 100,
            "with": {
                "analytics_data": True,
                "barcodes": True,
                "financial_data": True,
                "translit": True,
            },
        })

    def test_convenience_methods_target_first_phase_endpoints(self) -> None:
        transport = FakeTransport()
        client = OzonSellerClient("123", "secret", transport=transport)

        client.list_warehouses()
        client.update_stocks([{"offer_id": "A1", "stock": 5, "warehouse_id": 10}])
        client.import_prices([{"offer_id": "A1", "price": "999"}])
        client.get_fbs_posting("123-1")
        client.ship_fbs({"posting_number": "123-1", "packages": []})
        client.get_fbs_package_label(["123-1"])
        client.cancel_fbs_posting("123-1", cancel_reason_id=352)

        self.assertEqual(
            [call["url"].removeprefix("https://api-seller.ozon.ru") for call in transport.calls],
            [
                "/v2/warehouse/list",
                "/v2/products/stocks",
                "/v1/product/import/prices",
                "/v3/posting/fbs/get",
                "/v2/posting/fbs/ship",
                "/v2/posting/fbs/package-label",
                "/v2/posting/fbs/cancel",
            ],
        )


if __name__ == "__main__":
    unittest.main()
