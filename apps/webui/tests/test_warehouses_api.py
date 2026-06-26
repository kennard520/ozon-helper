from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


class FetchWarehousesKeyTest(unittest.TestCase):
    """Ozon 改版后仓库在 warehouses 键（旧 result）；fetch_warehouses 要读对。"""

    def test_reads_warehouses_key(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        class FakeClient:
            def list_warehouses(self, *, cursor: str = "", limit: int = 100):  # noqa: ANN001
                return {"warehouses": [{"warehouse_id": 1, "name": "成都龙泉"}],
                        "has_next": False, "cursor": ""}

        orig = adapter.build_client
        adapter.build_client = lambda settings: FakeClient()
        try:
            whs = adapter.fetch_warehouses({})
            self.assertEqual(len(whs), 1)
            self.assertEqual(whs[0]["name"], "成都龙泉")
        finally:
            adapter.build_client = orig

    def test_fetch_warehouses_paginates_multi_page(self) -> None:
        """验证 fetch_warehouses 正确处理多页游标翻页，合并所有页结果。"""
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        class MultiPageClient:
            def __init__(self) -> None:
                self.call_count = 0
                self.cursors_received: list[str] = []

            def list_warehouses(self, *, cursor: str = "", limit: int = 100):  # noqa: ANN001
                self.call_count += 1
                self.cursors_received.append(cursor)

                if cursor == "":
                    # 第一页：2 个仓库 + 有下一页
                    return {
                        "warehouses": [
                            {"warehouse_id": 101, "name": "FBS-北京"},
                            {"warehouse_id": 102, "name": "FBS-上海"},
                        ],
                        "has_next": True,
                        "cursor": "C1",
                    }
                elif cursor == "C1":
                    # 第二页：1 个仓库 + 无下一页
                    return {
                        "warehouses": [
                            {"warehouse_id": 103, "name": "rFBS-深圳"},
                        ],
                        "has_next": False,
                        "cursor": "",
                    }
                else:
                    # 不应该到这里
                    raise AssertionError(f"Unexpected cursor: {cursor}")

        orig = adapter.build_client
        client = MultiPageClient()
        adapter.build_client = lambda settings: client
        try:
            whs = adapter.fetch_warehouses({})
            # 验证返回的是全部 3 个仓库，合并正确
            self.assertEqual(len(whs), 3)
            wh_names = {w["name"] for w in whs}
            self.assertEqual(wh_names, {"FBS-北京", "FBS-上海", "rFBS-深圳"})
            # 验证调用了 2 次，第二次传了正确的 cursor
            self.assertEqual(client.call_count, 2)
            self.assertEqual(client.cursors_received, ["", "C1"])
        finally:
            adapter.build_client = orig


class WarehousesApiTest(unittest.TestCase):
    def _client(self, tmp: str):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415

        store_mod.DEFAULT_DB = Path(tmp) / "wh.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def test_get_warehouses_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import webui.main as main_mod  # noqa: PLC0415
            client = self._client(tmp)
            try:
                resp = client.get("/api/warehouses")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertIn("warehouses", body)
                self.assertEqual(body["warehouses"], [])
            finally:
                main_mod.APP.store.close()

    def test_sync_warehouses(self) -> None:
        fake_warehouses = [
            {"warehouse_id": 111, "name": "FBS-Москва", "is_rfbs": False, "status": "created"},
            {"warehouse_id": 222, "name": "rFBS-СПб", "is_rfbs": True, "status": "created"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            import webui.main as main_mod  # noqa: PLC0415
            import webui.ozon_client_adapter as adapter_mod  # noqa: PLC0415
            client = self._client(tmp)
            # monkeypatch fetch_warehouses / fetch_delivery_methods on the source module
            o_wh, o_dm = adapter_mod.fetch_warehouses, adapter_mod.fetch_delivery_methods
            adapter_mod.fetch_warehouses = lambda settings: fake_warehouses
            adapter_mod.fetch_delivery_methods = lambda settings, wids: []
            try:
                resp = client.post("/api/warehouses/sync")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["synced"], 2)
                self.assertEqual(len(body["warehouses"]), 2)
                wids = {w["warehouse_id"] for w in body["warehouses"]}
                self.assertEqual(wids, {111, 222})
            finally:
                adapter_mod.fetch_warehouses, adapter_mod.fetch_delivery_methods = o_wh, o_dm
                main_mod.APP.store.close()

    def test_set_default_warehouse(self) -> None:
        fake_warehouses = [
            {"warehouse_id": 111, "name": "FBS-Москва", "is_rfbs": False, "status": "created"},
            {"warehouse_id": 222, "name": "rFBS-СПб", "is_rfbs": True, "status": "created"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            import webui.main as main_mod  # noqa: PLC0415
            import webui.ozon_client_adapter as adapter_mod  # noqa: PLC0415
            client = self._client(tmp)
            o_wh, o_dm = adapter_mod.fetch_warehouses, adapter_mod.fetch_delivery_methods
            adapter_mod.fetch_warehouses = lambda settings: fake_warehouses
            adapter_mod.fetch_delivery_methods = lambda settings, wids: []
            try:
                # first sync to populate warehouses
                client.post("/api/warehouses/sync")
                # then set default to 222
                resp = client.post("/api/warehouses/default", json={"warehouse_id": 222})
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                by_id = {w["warehouse_id"]: w for w in body["warehouses"]}
                self.assertTrue(by_id[222]["is_default"])
                self.assertFalse(by_id[111]["is_default"])
            finally:
                adapter_mod.fetch_warehouses, adapter_mod.fetch_delivery_methods = o_wh, o_dm
                main_mod.APP.store.close()


class FetchDeliveryMethodsTest(unittest.TestCase):
    """fetch_delivery_methods 应一次传全部 warehouse_ids、cursor 翻页、归一字段。"""

    def test_passes_all_warehouse_ids_and_cursor_paginates(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        class FakeClient:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def list_delivery_methods(self, *, warehouse_ids=None, cursor="", limit=100, **_):  # noqa: ANN001
                self.calls.append({"warehouse_ids": warehouse_ids, "cursor": cursor})
                if cursor == "":
                    # 第一页：两仓各一条 + 有下一页（id=11 带完整自提点，模拟真实 v2 返回）
                    return {"result": [
                                {"id": 11, "name": "RETS PUDO", "warehouse_id": "1",
                                 "provider_id": 1268, "tpl_integration_type": "aggregator",
                                 "is_express": False, "status": "ACTIVE", "cutoff": "17:00",
                                 "sla_cut_in": 7200,
                                 "tpl_dropoff_point": {
                                     "name": "RETS泉州中心仓", "code": "1268_泉州东海集货仓",
                                     "address": "福建省泉州市晋江市池店镇浯潭村东北区113号",
                                     "address_coordinates": {"latitude": 25, "longitude": 119}}},
                                {"id": 21, "name": "Boxberry", "warehouse_id": 2}],
                            "has_next": True, "cursor": "C1"}
                if cursor == "C1":
                    return {"result": [{"id": 12, "name": "СДЭК", "warehouse_id": 1}],
                            "has_next": False, "cursor": ""}
                raise AssertionError(f"Unexpected cursor: {cursor}")

        orig = adapter.build_client
        client = FakeClient()
        adapter.build_client = lambda settings: client
        try:
            methods = adapter.fetch_delivery_methods({}, [1, 2])
            ids = {m["delivery_method_id"] for m in methods}
            self.assertEqual(ids, {11, 12, 21})
            # 单一 cursor 循环：两次调用，全部仓库一次性进 filter
            self.assertEqual([c["cursor"] for c in client.calls], ["", "C1"])
            self.assertEqual(client.calls[0]["warehouse_ids"], [1, 2])
            m11 = next(m for m in methods if m["delivery_method_id"] == 11)
            self.assertEqual(m11["warehouse_id"], "1")
            self.assertEqual(m11["name"], "RETS PUDO")
            # 自提点(地址)被正确抽出
            self.assertEqual(m11["dropoff_name"], "RETS泉州中心仓")
            self.assertEqual(m11["dropoff_code"], "1268_泉州东海集货仓")
            self.assertEqual(m11["dropoff_address"], "福建省泉州市晋江市池店镇浯潭村东北区113号")
            self.assertEqual(m11["dropoff_lat"], 25)
            self.assertEqual(m11["dropoff_lng"], 119)
            self.assertEqual(m11["tpl_integration_type"], "aggregator")
            self.assertIs(m11["is_express"], False)
            # 缺自提点的条目不报错，地址字段为 None
            m21 = next(m for m in methods if m["delivery_method_id"] == 21)
            self.assertIsNone(m21["dropoff_address"])
        finally:
            adapter.build_client = orig

    def test_empty_warehouse_ids_skips_call(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        class BoomClient:
            def list_delivery_methods(self, **_):  # noqa: ANN001
                raise AssertionError("不应在无仓库时发起请求")

        orig = adapter.build_client
        adapter.build_client = lambda settings: BoomClient()
        try:
            self.assertEqual(adapter.fetch_delivery_methods({}, []), [])
        finally:
            adapter.build_client = orig


class DeliveryMethodsStoreTest(unittest.TestCase):
    """store 层：按店全量替换 + 按店隔离。"""

    def _store(self, tmp: str):
        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "dm.db"
        return store_mod.Store()

    def test_replace_is_full_and_store_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            st = self._store(tmp)
            try:
                st.replace_delivery_methods(
                    [{"delivery_method_id": 1, "warehouse_id": 9, "name": "A"},
                     {"delivery_method_id": 2, "warehouse_id": 9, "name": "B"}],
                    "storeX",
                )
                st.replace_delivery_methods(
                    [{"delivery_method_id": 99, "warehouse_id": 7, "name": "Z"}],
                    "storeY",
                )
                # 全量替换：storeX 第二次只剩 1 条
                st.replace_delivery_methods(
                    [{"delivery_method_id": 3, "warehouse_id": 9, "name": "C"}],
                    "storeX",
                )
                x = st.list_delivery_methods("storeX")
                self.assertEqual({m["delivery_method_id"] for m in x}, {3})
                # storeY 不受影响
                y = st.list_delivery_methods("storeY")
                self.assertEqual({m["delivery_method_id"] for m in y}, {99})
            finally:
                st.close()

    def test_dropoff_fields_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            st = self._store(tmp)
            try:
                st.replace_delivery_methods([{
                    "delivery_method_id": 5, "warehouse_id": 9, "name": "PUDO",
                    "is_express": True, "tpl_integration_type": "aggregator",
                    "dropoff_name": "中心仓", "dropoff_code": "X1",
                    "dropoff_address": "福建省泉州市…", "dropoff_lat": 25, "dropoff_lng": 119,
                }], "storeX")
                m = st.list_delivery_methods("storeX")[0]
                self.assertEqual(m["dropoff_address"], "福建省泉州市…")
                self.assertEqual(m["dropoff_code"], "X1")
                self.assertEqual(m["dropoff_lat"], 25)
                self.assertIs(m["is_express"], True)  # 0/1 → bool
            finally:
                st.close()


class SyncAttachesDeliveryMethodsTest(unittest.TestCase):
    """/api/warehouses/sync 后 /api/warehouses 每个仓库挂上分组后的 delivery_methods。"""

    def _client(self, tmp: str):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "wh_dm.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def test_sync_then_list_groups_by_warehouse(self) -> None:
        fake_warehouses = [
            {"warehouse_id": 111, "name": "FBS", "is_rfbs": False, "status": "created"},
            {"warehouse_id": 222, "name": "rFBS", "is_rfbs": True, "status": "created"},
        ]
        fake_methods = [
            {"delivery_method_id": 1, "warehouse_id": 111, "name": "Почта"},
            {"delivery_method_id": 2, "warehouse_id": 222, "name": "СДЭК"},
            {"delivery_method_id": 3, "warehouse_id": 222, "name": "Boxberry"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            import webui.main as main_mod  # noqa: PLC0415
            import webui.ozon_client_adapter as adapter_mod  # noqa: PLC0415
            client = self._client(tmp)
            o_wh, o_dm = adapter_mod.fetch_warehouses, adapter_mod.fetch_delivery_methods
            adapter_mod.fetch_warehouses = lambda settings: fake_warehouses
            adapter_mod.fetch_delivery_methods = lambda settings, wids: fake_methods
            try:
                resp = client.post("/api/warehouses/sync")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["synced"], 2)
                self.assertEqual(body["delivery_methods"], 3)
                by_id = {w["warehouse_id"]: w for w in body["warehouses"]}
                self.assertEqual(len(by_id[111]["delivery_methods"]), 1)
                self.assertEqual(len(by_id[222]["delivery_methods"]), 2)
                # GET 也应带上分组后的配送方式
                got = client.get("/api/warehouses").json()
                by_id2 = {w["warehouse_id"]: w for w in got["warehouses"]}
                self.assertEqual(
                    {m["delivery_method_id"] for m in by_id2[222]["delivery_methods"]},
                    {2, 3},
                )
            finally:
                adapter_mod.fetch_warehouses, adapter_mod.fetch_delivery_methods = o_wh, o_dm
                main_mod.APP.store.close()


if __name__ == "__main__":
    unittest.main()
