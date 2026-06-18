from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


class FetchWarehousesKeyTest(unittest.TestCase):
    """Ozon 改版后仓库在 warehouses 键（旧 result）；fetch_warehouses 要读对。"""

    def test_reads_warehouses_key(self) -> None:
        import backend.ozon_client_adapter as adapter  # noqa: PLC0415

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
        import backend.ozon_client_adapter as adapter  # noqa: PLC0415

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
        import backend.store as store_mod  # noqa: PLC0415

        store_mod.DEFAULT_DB = Path(tmp) / "wh.db"
        import backend.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import backend.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def test_get_warehouses_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import backend.main as main_mod  # noqa: PLC0415
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
            import backend.main as main_mod  # noqa: PLC0415
            import backend.ozon_client_adapter as adapter_mod  # noqa: PLC0415
            client = self._client(tmp)
            # monkeypatch fetch_warehouses on the source module
            original = adapter_mod.fetch_warehouses
            adapter_mod.fetch_warehouses = lambda settings: fake_warehouses
            try:
                resp = client.post("/api/warehouses/sync")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["synced"], 2)
                self.assertEqual(len(body["warehouses"]), 2)
                wids = {w["warehouse_id"] for w in body["warehouses"]}
                self.assertEqual(wids, {111, 222})
            finally:
                adapter_mod.fetch_warehouses = original
                main_mod.APP.store.close()

    def test_set_default_warehouse(self) -> None:
        fake_warehouses = [
            {"warehouse_id": 111, "name": "FBS-Москва", "is_rfbs": False, "status": "created"},
            {"warehouse_id": 222, "name": "rFBS-СПб", "is_rfbs": True, "status": "created"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            import backend.main as main_mod  # noqa: PLC0415
            import backend.ozon_client_adapter as adapter_mod  # noqa: PLC0415
            client = self._client(tmp)
            original = adapter_mod.fetch_warehouses
            adapter_mod.fetch_warehouses = lambda settings: fake_warehouses
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
                adapter_mod.fetch_warehouses = original
                main_mod.APP.store.close()


if __name__ == "__main__":
    unittest.main()
