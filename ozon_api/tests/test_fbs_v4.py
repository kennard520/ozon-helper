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


class FbsV4Test(unittest.TestCase):
    def _client(self, responses):
        return OzonSellerClient("cid", "key", transport=FakeTransport(responses))

    def test_list_unfulfilled_fbs_v4_payload_and_parse(self):
        c = self._client({"/v4/posting/fbs/unfulfilled/list": {"result": {"postings": [
            {"posting_number": "P-1", "products": [
                {"offer_id": "A", "sku": 123, "quantity": 2}]}]}}})
        r = c.list_unfulfilled_fbs_v4(
            cutoff_from="2026-05-29T00:00:00.000Z",
            cutoff_to="2026-06-12T00:00:00.000Z",
        )
        postings = r["result"]["postings"]
        self.assertEqual(postings[0]["posting_number"], "P-1")
        self.assertEqual(postings[0]["products"][0]["sku"], 123)
        path, body = c.transport.calls[0]
        self.assertEqual(path, "/v4/posting/fbs/unfulfilled/list")
        self.assertEqual(body["filter"]["cutoff_from"], "2026-05-29T00:00:00.000Z")
        self.assertEqual(body["filter"]["cutoff_to"], "2026-06-12T00:00:00.000Z")
        self.assertEqual(body["filter"]["status"], "awaiting_packaging")
        self.assertNotIn("cursor", body)

    def test_list_unfulfilled_fbs_v4_adds_cursor(self):
        c = self._client({"/v4/posting/fbs/unfulfilled/list": {"result": {"postings": []}}})
        c.list_unfulfilled_fbs_v4(
            cutoff_from="2026-05-29T00:00:00.000Z",
            cutoff_to="2026-06-12T00:00:00.000Z",
            cursor="CUR-1",
        )
        _, body = c.transport.calls[0]
        self.assertEqual(body["cursor"], "CUR-1")

    def test_ship_fbs_v4_payload(self):
        c = self._client({"/v4/posting/fbs/ship": {"result": ["P-1"]}})
        packages = [{"products": [{"product_id": 123, "quantity": 2}]}]
        r = c.ship_fbs_v4("P-1", packages)
        self.assertEqual(r["result"], ["P-1"])
        path, body = c.transport.calls[0]
        self.assertEqual(path, "/v4/posting/fbs/ship")
        self.assertEqual(body["posting_number"], "P-1")
        self.assertEqual(body["packages"][0]["products"][0]["product_id"], 123)
        self.assertTrue(body["with"]["additional_data"])

    def test_get_package_label_pdf_returns_bytes(self):
        c = self._client({})
        captured = {}

        def fake_raw(path, payload):
            captured["path"] = path
            captured["payload"] = payload
            return b"%PDF-1.4 fake"

        c._raw_post = fake_raw
        pdf = c.get_package_label_pdf(["P-1"])
        self.assertEqual(pdf, b"%PDF-1.4 fake")
        self.assertEqual(captured["path"], "/v2/posting/fbs/package-label")
        self.assertEqual(captured["payload"], {"posting_number": ["P-1"]})


    def test_get_package_label_pdf_raises_on_non_pdf(self):
        """面单未就绪时 Ozon 返回 JSON（非 PDF），应抛出 OzonApiError 而非返回乱码字节。"""
        from ozon_api.client import OzonApiError  # noqa: PLC0415
        c = self._client({})
        c._raw_post = lambda path, payload: b'{"error":"not ready"}'
        with self.assertRaises((OzonApiError, RuntimeError)):
            c.get_package_label_pdf(["P-1"])

    def test_get_package_label_pdf_valid_pdf_passes(self):
        """正常 %PDF 响应仍原样返回不抛异常。"""
        c = self._client({})
        c._raw_post = lambda path, payload: b"%PDF-1.4 fake"
        result = c.get_package_label_pdf(["P-1"])
        self.assertEqual(result, b"%PDF-1.4 fake")


if __name__ == "__main__":
    unittest.main()


class V4LimitClampTest(unittest.TestCase):
    def test_limit_clamped_to_100(self) -> None:
        c = OzonSellerClient("cid", "key", transport=FakeTransport(
            {"/v4/posting/fbs/unfulfilled/list": {"result": {"postings": []}}}))
        c.list_unfulfilled_fbs_v4(cutoff_from="a", cutoff_to="b", limit=1000)
        body = c.transport.calls[0][1]
        self.assertEqual(body["limit"], 100)   # v4 上限 100，超了要夹住
