from __future__ import annotations

import unittest

from ozon_api.client import OzonApiError
from ozon_api.performance import OzonPerformanceClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


class FakeTransport:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def request(self, *, method: str, url: str, headers: dict, json: dict | None, timeout: float) -> FakeResponse:
        self.calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return self.responses.pop(0)


class OzonPerformanceClientTest(unittest.TestCase):
    def test_get_request_fetches_token_once_and_uses_bearer_header(self) -> None:
        transport = FakeTransport([
            FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
            FakeResponse(200, {"list": [{"id": "10"}]}),
            FakeResponse(200, {"products": [{"sku": "123"}]}),
        ])
        client = OzonPerformanceClient("cid", "sec", base_url="https://perf.test", transport=transport)

        self.assertEqual(client.list_campaigns(), {"list": [{"id": "10"}]})
        self.assertEqual(client.campaign_products("10"), {"products": [{"sku": "123"}]})

        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[0]["method"], "POST")
        self.assertEqual(transport.calls[0]["url"], "https://perf.test/api/client/token")
        self.assertEqual(transport.calls[0]["json"], {
            "client_id": "cid",
            "client_secret": "sec",
            "grant_type": "client_credentials",
        })
        self.assertEqual(transport.calls[1]["method"], "GET")
        self.assertEqual(transport.calls[1]["headers"]["Authorization"], "Bearer tok")
        self.assertEqual(transport.calls[2]["headers"]["Authorization"], "Bearer tok")

    def test_post_methods_target_campaign_and_search_promo_endpoints(self) -> None:
        transport = FakeTransport([
            FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
            FakeResponse(200, {"ok": True}),
            FakeResponse(200, {"ok": True}),
            FakeResponse(200, {"ok": True}),
        ])
        client = OzonPerformanceClient("cid", "sec", base_url="https://perf.test", transport=transport)

        client.add_campaign_products("11", [{"sku": "1"}])
        client.delete_campaign_products("11", [{"sku": "2"}])
        client.disable_search_promo([{"sku": "3"}])

        self.assertEqual(
            [call["url"].removeprefix("https://perf.test") for call in transport.calls[1:]],
            [
                "/api/client/campaign/11/products",
                "/api/client/campaign/11/products/delete",
                "/api/client/search_promo/product/disable",
            ],
        )
        self.assertEqual(transport.calls[1]["method"], "POST")
        self.assertEqual(transport.calls[1]["json"], {"products": [{"sku": "1"}]})
        self.assertEqual(transport.calls[3]["json"], {"products": [{"sku": "3"}]})

    def test_http_error_raises_api_error(self) -> None:
        transport = FakeTransport([
            FakeResponse(200, {"access_token": "tok", "expires_in": 3600}),
            FakeResponse(403, {"message": "forbidden"}, text="forbidden"),
        ])
        client = OzonPerformanceClient("cid", "sec", base_url="https://perf.test", transport=transport)

        with self.assertRaises(OzonApiError) as ctx:
            client.list_campaigns()

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.payload, {"message": "forbidden"})


if __name__ == "__main__":
    unittest.main()
