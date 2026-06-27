"""Analytics service 单测 —— 纯函数 + 编排（mock client）。"""
from __future__ import annotations

import unittest


class FakeClient:
    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list[tuple] = []

    def request(self, path: str, payload: dict):
        self.calls.append((path, payload))
        return self.responses.get(path, {})


# ---------- build_dashboard_rows ----------

class BuildDashboardRowsTest(unittest.TestCase):
    def _call(self, infos, funnel):
        from webui.services.analytics_service import build_dashboard_rows
        return build_dashboard_rows(infos, funnel)

    def test_merges_info_and_funnel(self):
        infos = {"OFF1": {"sku": "101", "title": "杯子", "price": "100", "stock": 5}}
        funnel = {"101": {"exposure": 300, "sessions": 50, "cart": 10, "ordered_units": 3, "revenue": 300.0}}
        rows = self._call(infos, funnel)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(str(r["sku"]), "101")
        self.assertEqual(r["exposure"], 300)
        self.assertEqual(r["sessions"], 50)
        self.assertEqual(r["cart"], 10)
        self.assertEqual(r["ordered_units"], 3)
        self.assertAlmostEqual(r["conv_cart_pct"], 20.0)
        self.assertEqual(r["title"], "杯子")

    def test_diagnosis_que_huo(self):
        """stock=0 → '缺货'。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 0}}
        funnel = {"101": {"exposure": 500, "sessions": 0, "cart": 0, "ordered_units": 0, "revenue": 0}}
        rows = self._call(infos, funnel)
        r = rows[0]
        self.assertIn("缺货", r["diagnostics"])

    def test_diagnosis_zero_exposure(self):
        """exposure=0 → '0曝光'。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 5}}
        funnel = {}  # 无漏斗数据 → 曝光=0
        rows = self._call(infos, funnel)
        r = rows[0]
        self.assertIn("0曝光", r["diagnostics"])
        self.assertEqual(r["conv_cart_pct"], 0)

    def test_diagnosis_high_exposure_no_order(self):
        """高曝光（>200）+ 下单=0 → '高曝光0转化'。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 5}}
        funnel = {"101": {"exposure": 500, "sessions": 0, "cart": 0, "ordered_units": 0, "revenue": 0}}
        rows = self._call(infos, funnel)
        r = rows[0]
        self.assertIn("高曝光0转化", r["diagnostics"])
        # 同时满足"缺货"（stock=5→不缺）但 sessions=0 → 不触发加购未转化
        self.assertNotIn("缺货", r["diagnostics"])

    def test_diagnosis_cart_no_order(self):
        """加购>0 + 下单=0 → '加购未转化'。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 10}}
        funnel = {"101": {"exposure": 100, "sessions": 50, "cart": 5, "ordered_units": 0, "revenue": 0}}
        rows = self._call(infos, funnel)
        r = rows[0]
        self.assertIn("加购未转化", r["diagnostics"])

    def test_no_diagnosis_when_healthy(self):
        """有库存、有订单、正常曝光 → 无诊断标签。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 10}}
        funnel = {"101": {"exposure": 300, "sessions": 100, "cart": 20, "ordered_units": 5, "revenue": 500.0}}
        rows = self._call(infos, funnel)
        r = rows[0]
        self.assertEqual(r["diagnostics"], [])

    def test_conv_cart_pct_zero_sessions(self):
        """sessions=0 时 conv_cart_pct=0（不抛除零错误）。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 5}}
        funnel = {"101": {"exposure": 500, "sessions": 0, "cart": 0, "ordered_units": 0, "revenue": 0}}
        rows = self._call(infos, funnel)
        self.assertEqual(rows[0]["conv_cart_pct"], 0)

    def test_conv_cart_pct_calculation(self):
        """conv_cart_pct = cart/sessions*100，精确到 2 位小数。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 5}}
        funnel = {"101": {"exposure": 100, "sessions": 3, "cart": 1, "ordered_units": 1, "revenue": 100.0}}
        rows = self._call(infos, funnel)
        self.assertAlmostEqual(rows[0]["conv_cart_pct"], round(1 / 3 * 100, 2))

    def test_sorted_by_exposure_desc(self):
        """结果按曝光量降序。"""
        infos = {
            "OFF1": {"sku": "101", "title": "低曝光", "price": 100, "stock": 5},
            "OFF2": {"sku": "102", "title": "高曝光", "price": 200, "stock": 5},
        }
        funnel = {
            "101": {"exposure": 50, "sessions": 10, "cart": 2, "ordered_units": 1, "revenue": 100.0},
            "102": {"exposure": 500, "sessions": 100, "cart": 20, "ordered_units": 5, "revenue": 1000.0},
        }
        rows = self._call(infos, funnel)
        self.assertEqual(str(rows[0]["sku"]), "102")
        self.assertEqual(str(rows[1]["sku"]), "101")

    def test_funnel_int_sku_key(self):
        """funnel key 为 int（如从真实 API）也能匹配。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 5}}
        funnel = {101: {"exposure": 200, "sessions": 50, "cart": 5, "ordered_units": 2, "revenue": 200.0}}
        rows = self._call(infos, funnel)
        self.assertEqual(rows[0]["exposure"], 200)

    def test_multiple_diagnostics(self):
        """stock=0 且 exposure=0 → 两个标签同时出现。"""
        infos = {"OFF1": {"sku": "101", "title": "杯", "price": 100, "stock": 0}}
        funnel = {}
        rows = self._call(infos, funnel)
        r = rows[0]
        self.assertIn("缺货", r["diagnostics"])
        self.assertIn("0曝光", r["diagnostics"])

    def test_build_dashboard_rows_plan_scenario(self):
        """计划中的示例场景：stock=0 + 高曝光 + 0访问。"""
        from webui.services.analytics_service import build_dashboard_rows
        infos = {"OFF1": {"sku": 101, "title": "杯", "price": 100, "stock": 0}}
        funnel = {101: {"exposure": 500, "sessions": 0, "cart": 0, "ordered_units": 0, "revenue": 0}}
        rows = build_dashboard_rows(infos, funnel)
        r = rows[0]
        self.assertEqual(str(r["sku"]), "101")
        self.assertIn("缺货", r["diagnostics"])
        self.assertEqual(r["conv_cart_pct"], 0)
        # 高曝光 0 下单
        self.assertTrue(any("曝光" in d or "转化" in d for d in r["diagnostics"]))


# ---------- grand_total ----------

class GrandTotalTest(unittest.TestCase):
    def _call(self, rows):
        from webui.services.analytics_service import grand_total
        return grand_total(rows)

    def test_empty_rows(self):
        gt = self._call([])
        self.assertEqual(gt["sku_count"], 0)
        self.assertEqual(gt["exposure"], 0)
        self.assertEqual(gt["conv_cart_pct"], 0)

    def test_aggregates_correctly(self):
        rows = [
            {"exposure": 300, "sessions": 100, "cart": 20, "ordered_units": 5, "revenue": 500.0},
            {"exposure": 200, "sessions": 50, "cart": 5, "ordered_units": 2, "revenue": 200.0},
        ]
        gt = self._call(rows)
        self.assertEqual(gt["sku_count"], 2)
        self.assertEqual(gt["exposure"], 500)
        self.assertEqual(gt["sessions"], 150)
        self.assertEqual(gt["cart"], 25)
        self.assertEqual(gt["ordered_units"], 7)
        self.assertAlmostEqual(gt["revenue"], 700.0)
        self.assertAlmostEqual(gt["conv_cart_pct"], round(25 / 150 * 100, 2))

    def test_sku_with_traffic_count(self):
        rows = [
            {"exposure": 0, "sessions": 0, "cart": 0, "ordered_units": 0, "revenue": 0},
            {"exposure": 100, "sessions": 10, "cart": 2, "ordered_units": 1, "revenue": 100.0},
        ]
        gt = self._call(rows)
        self.assertEqual(gt["sku_with_traffic"], 1)

    def test_single_row(self):
        rows = [{"exposure": 100, "sessions": 30, "cart": 6, "ordered_units": 2, "revenue": 200.0}]
        gt = self._call(rows)
        self.assertEqual(gt["sku_count"], 1)
        self.assertAlmostEqual(gt["conv_cart_pct"], round(6 / 30 * 100, 2))


# ---------- 缓存 TTL ----------

class CacheTTLTest(unittest.TestCase):
    def test_cache_hit_returns_same_object(self):
        """同 key 两次调用返回同一对象（缓存命中）。"""
        from webui.services import analytics_service
        analytics_service._cache.clear()
        key = ("test_cid", "dashboard", "2026-06-01", "2026-06-07")
        analytics_service._cache_set(key, {"rows": [1, 2, 3]}, ttl=3600)
        result = analytics_service._cache_get(key)
        self.assertEqual(result, {"rows": [1, 2, 3]})

    def test_cache_miss_after_expiry(self):
        """TTL 过期后 _cache_get 返回 None。"""
        from webui.services import analytics_service
        analytics_service._cache.clear()
        key = ("test_cid", "dashboard", "2026-06-01", "2026-06-07")
        analytics_service._cache_set(key, {"rows": []}, ttl=-1)  # 已过期
        result = analytics_service._cache_get(key)
        self.assertIsNone(result)


# ---------- ValueError 缺凭证 ----------

class MissingCredentialsTest(unittest.TestCase):
    def test_dashboard_raises_value_error_no_creds(self):
        from webui.services.analytics_service import dashboard
        with self.assertRaises(ValueError) as ctx:
            dashboard({}, "2026-06-01", "2026-06-07")
        self.assertIn("凭证", str(ctx.exception))

    def test_traffic_raises_value_error_no_creds(self):
        from webui.services.analytics_service import traffic
        with self.assertRaises(ValueError):
            traffic({}, "2026-06-01", "2026-06-07")

    def test_keywords_raises_value_error_no_creds(self):
        from webui.services.analytics_service import keywords
        with self.assertRaises(ValueError):
            keywords({}, "2026-06-01", "2026-06-07")


# ---------- adapter 纯函数测试 ----------

class FetchAnalyticsSkuTest(unittest.TestCase):
    """fetch_analytics_sku 纯函数逻辑（mock client.request）。"""

    def _make_response(self, rows_data):
        return {"result": {"data": rows_data}}

    def test_normal_response_parsed(self):
        from webui.ozon_client_adapter import fetch_analytics_sku
        client = FakeClient({
            "/v1/analytics/data": self._make_response([
                {"dimensions": [{"id": "101"}],
                 "metrics": [500, 80, 10, 5, 999.0]},
            ])
        })
        result = fetch_analytics_sku(client, "2026-06-01", "2026-06-07")
        self.assertFalse(result["degraded"])
        self.assertEqual(len(result["rows"]), 1)
        r = result["rows"][0]
        self.assertEqual(r["sku"], "101")
        self.assertEqual(r["exposure"], 500)
        self.assertEqual(r["sessions"], 80)
        self.assertEqual(r["cart"], 10)
        self.assertEqual(r["ordered_units"], 5)
        self.assertAlmostEqual(r["revenue"], 999.0)

    def test_403_degraded(self):
        """403 → 降级重试 ordered_units/revenue，degraded=True。"""
        from webui.ozon_client_adapter import fetch_analytics_sku

        class DegradedClient:
            def __init__(self):
                self.call_count = 0

            def request(self, path, payload):
                self.call_count += 1
                metrics = payload.get("metrics", [])
                if "hits_view" in metrics:
                    # 模拟 403
                    exc = Exception("forbidden")
                    exc.status_code = 403
                    raise exc
                # 降级：只返回 ordered_units/revenue
                return {"result": {"data": [
                    {"dimensions": [{"id": "101"}], "metrics": [3, 300.0]}
                ]}}

        client = DegradedClient()
        result = fetch_analytics_sku(client, "2026-06-01", "2026-06-07")
        self.assertTrue(result["degraded"])
        self.assertEqual(len(result["rows"]), 1)
        r = result["rows"][0]
        self.assertEqual(r["sku"], "101")
        self.assertEqual(r["ordered_units"], 3)
        self.assertAlmostEqual(r["revenue"], 300.0)
        self.assertEqual(r["exposure"], 0)   # 降级后无 exposure

    def test_empty_response(self):
        from webui.ozon_client_adapter import fetch_analytics_sku
        client = FakeClient({"/v1/analytics/data": {}})
        result = fetch_analytics_sku(client, "2026-06-01", "2026-06-07")
        self.assertEqual(result["rows"], [])
        self.assertFalse(result["degraded"])


class FetchAnalyticsTrafficTest(unittest.TestCase):
    def test_normal_response(self):
        from webui.ozon_client_adapter import fetch_analytics_traffic
        client = FakeClient({
            "/v1/analytics/data": {"result": {"data": [
                {"dimensions": [{"id": "101"}, {"id": "2026-06-01"}],
                 "metrics": [300, 50, 10, 5]},
            ]}}
        })
        result = fetch_analytics_traffic(client, "2026-06-01", "2026-06-07")
        self.assertEqual(len(result["rows"]), 1)
        r = result["rows"][0]
        self.assertEqual(r["sku"], "101")
        self.assertEqual(r["day"], "2026-06-01")
        self.assertEqual(r["hits_view"], 300)
        self.assertEqual(r["session_view"], 50)

    def test_403_returns_empty(self):
        from webui.ozon_client_adapter import fetch_analytics_traffic

        class ForbiddenClient:
            def request(self, path, payload):
                exc = Exception("forbidden")
                exc.status_code = 403
                raise exc

        result = fetch_analytics_traffic(ForbiddenClient(), "2026-06-01", "2026-06-07")
        self.assertEqual(result["rows"], [])


class FetchProductQueriesTest(unittest.TestCase):
    def test_single_page(self):
        from webui.ozon_client_adapter import fetch_product_queries
        client = FakeClient({
            "/v1/analytics/product-queries/details": {
                "queries": [
                    {"sku": "101", "query": "стакан", "unique_search_users": 500,
                     "view_conversion": 2.5, "position": 3.0, "order_count": 5, "gmv": 500.0},
                ],
                "page_count": 1,
            }
        })
        result = fetch_product_queries(client, ["101"], "2026-06-01", "2026-06-07")
        by_sku = result["by_sku"]
        self.assertIn("101", by_sku)
        q = by_sku["101"][0]
        self.assertEqual(q["query"], "стакан")
        self.assertEqual(q["searches"], 500)
        self.assertAlmostEqual(q["ctr"], 2.5)
        self.assertEqual(q["orders"], 5)

    def test_empty_response(self):
        from webui.ozon_client_adapter import fetch_product_queries
        client = FakeClient({
            "/v1/analytics/product-queries/details": {"queries": [], "page_count": 1}
        })
        result = fetch_product_queries(client, ["101"], "2026-06-01", "2026-06-07")
        self.assertEqual(result["by_sku"], {})


class FetchPricesTest(unittest.TestCase):
    def test_normal(self):
        from webui.ozon_client_adapter import fetch_prices

        class PriceClient:
            def request(self, path, payload):
                return {"items": [
                    {"offer_id": "OFF1", "price": {
                        "marketing_seller_price": "90", "price": "100", "old_price": "120"
                    }}
                ], "cursor": ""}

        result = fetch_prices(PriceClient(), ["OFF1"])
        self.assertIn("OFF1", result)
        self.assertEqual(result["OFF1"]["marketing_seller_price"], "90")


class FetchStocksTest(unittest.TestCase):
    def test_sums_stocks(self):
        from webui.ozon_client_adapter import fetch_stocks

        class StockClient:
            def request(self, path, payload):
                return {
                    "items": [
                        {"offer_id": "OFF1", "stocks": [{"present": 10}, {"present": 5}]},
                    ],
                    "cursor": "",
                }

        result = fetch_stocks(StockClient(), ["OFF1"])
        self.assertEqual(result["OFF1"], 15)


# ---------- router 端点冒烟 ----------

class AnalyticsRouterTest(unittest.TestCase):
    """router 三端点：缺凭证 → 400（不 500）。"""

    def _app_client(self, tmp):
        from fastapi.testclient import TestClient
        from pathlib import Path
        import webui.store as store_mod
        import importlib
        store_mod.DEFAULT_DB = Path(tmp) / "analytics.db"
        import webui.app_service as svc
        importlib.reload(svc)
        import webui.main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app), main_mod

    def test_dashboard_no_creds_400(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client, main_mod = self._app_client(tmp)
            try:
                resp = client.post("/api/analytics/dashboard", json={
                    "date_from": "2026-06-01", "date_to": "2026-06-07"
                })
                self.assertEqual(resp.status_code, 400)
                self.assertIn("凭证", resp.json().get("detail", ""))
            finally:
                main_mod.APP.store.close()

    def test_traffic_no_creds_400(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client, main_mod = self._app_client(tmp)
            try:
                resp = client.post("/api/analytics/traffic", json={
                    "date_from": "2026-06-01", "date_to": "2026-06-07"
                })
                self.assertEqual(resp.status_code, 400)
            finally:
                main_mod.APP.store.close()

    def test_keywords_no_creds_400(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client, main_mod = self._app_client(tmp)
            try:
                resp = client.post("/api/analytics/keywords", json={
                    "date_from": "2026-06-01", "date_to": "2026-06-07"
                })
                self.assertEqual(resp.status_code, 400)
            finally:
                main_mod.APP.store.close()


if __name__ == "__main__":
    unittest.main()
