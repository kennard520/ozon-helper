"""Fix 1: ship_posting network error → structured ValueError (not bare Exception)."""
from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


class ShipPostingNetworkErrorTest(unittest.TestCase):
    def _setup(self, tmp: str):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "ship.db"
        import webui.app_service as svc
        importlib.reload(svc)
        return svc

    def test_get_ozon_info_network_error_raises_value_error(self):
        """get_ozon_info 网络异常时 ship_posting 必须 raise ValueError，不能透传裸 Exception。"""
        import webui.ozon_client_adapter as adapter

        with tempfile.TemporaryDirectory() as tmp:
            svc = self._setup(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C", "ozon_api_key": "K"})

            # 插入一条 posting
            app.store.upsert_postings([{
                "posting_number": "PN-001",
                "ozon_order_id": "ORD-1",
                "status": "awaiting_packaging",
                "ship_by": None,
                "warehouse_id": None,
                "products": [{"offer_id": "OFR-A", "sku": 12345, "quantity": 1}],
                "raw": {},
            }])

            # 让 get_ozon_info 抛网络异常
            orig_get = adapter.get_ozon_info

            def boom(settings, offer_ids):
                raise ConnectionError("模拟网络超时")

            adapter.get_ozon_info = boom
            try:
                with self.assertRaises(ValueError) as ctx:
                    app.ship_posting("PN-001")
                self.assertIn("拉取商品信息失败", str(ctx.exception))
            finally:
                adapter.get_ozon_info = orig_get
                app.store.close()

    def test_get_ozon_info_network_error_is_not_bare_exception(self):
        """确保抛出的是 ValueError（FastAPI route 捕获 ValueError → 400），不是裸 Exception / ConnectionError。"""
        import webui.ozon_client_adapter as adapter

        with tempfile.TemporaryDirectory() as tmp:
            svc = self._setup(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C", "ozon_api_key": "K"})

            app.store.upsert_postings([{
                "posting_number": "PN-002",
                "ozon_order_id": "ORD-2",
                "status": "awaiting_packaging",
                "ship_by": None,
                "warehouse_id": None,
                "products": [{"offer_id": "OFR-B", "sku": 99, "quantity": 2}],
                "raw": {},
            }])

            orig_get = adapter.get_ozon_info

            def boom2(settings, offer_ids):
                raise RuntimeError("Ozon API returned 503")

            adapter.get_ozon_info = boom2
            try:
                # Must be ValueError, not RuntimeError or Exception
                exc_raised = None
                try:
                    app.ship_posting("PN-002")
                except ValueError as e:
                    exc_raised = e
                except Exception as e:  # noqa: BLE001
                    self.fail(f"Expected ValueError but got {type(e).__name__}: {e}")
                self.assertIsNotNone(exc_raised, "Expected ValueError to be raised")
            finally:
                adapter.get_ozon_info = orig_get
                app.store.close()


if __name__ == "__main__":
    unittest.main()
