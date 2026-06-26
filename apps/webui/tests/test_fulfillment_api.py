from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


class FulfillmentApiTest(unittest.TestCase):
    def _client(self, tmp):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "f.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app)

    def test_pull_builds_procurement_with_supplier(self) -> None:
        import webui.main as main_mod  # noqa: PLC0415
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                # 预插一条 offer_id 匹配的草稿，带 supplier/cost/采购链接
                main_mod.APP.store.conn.execute(
                    "INSERT INTO drafts (source_platform, source_url, source_offer_id, source_title, "
                    "ozon_title, description, category_id, price, old_price, stock, images_json, "
                    "attributes_json, status, validation_errors_json, created_at, updated_at, "
                    "offer_id, purchase_url, purchase_note, supplier, cost_cny) "
                    "VALUES ('1688','u1','o1','t','t','d','1','10','10',1,'[]','{}','draft','[]',"
                    "'now','now','SKU-1','https://detail.1688.com/offer/1.html','厂家A','厂家A',12.5)"
                )
                main_mod.APP.store.conn.commit()

                def fake_pull(settings, status, days):  # noqa: ANN001
                    return [
                        {"posting_number": "P-1", "ozon_order_id": "O-1",
                         "status": "awaiting_packaging", "ship_by": None, "warehouse_id": None,
                         "products": [{"offer_id": "SKU-1", "sku": 1001, "quantity": 2}], "raw": {}},
                        {"posting_number": "P-2", "ozon_order_id": "O-2",
                         "status": "awaiting_packaging", "ship_by": None, "warehouse_id": None,
                         "products": [{"offer_id": "SKU-X", "sku": 2002, "quantity": 1}], "raw": {}},
                    ]

                adapter.pull_fbs_postings = fake_pull
                resp = client.post("/api/fbs/pull", json={"status": "awaiting_packaging", "days": 14})
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertEqual(body["synced"], 2)
                proc = body["procurement"]
                self.assertEqual(len(proc), 2)
                matched = next(r for r in proc if r["offer_id"] == "SKU-1")
                self.assertEqual(matched["supplier"], "厂家A")
                self.assertEqual(matched["qty"], 2)
            finally:
                main_mod.APP.store.close()

    def test_procurement_get_and_set_state(self) -> None:
        import webui.main as main_mod  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                main_mod.APP.store.upsert_postings([
                    {"posting_number": "P-1", "ozon_order_id": "O-1",
                     "status": "awaiting_packaging", "ship_by": None, "warehouse_id": None,
                     "products": [{"offer_id": "SKU-1", "sku": 1001, "quantity": 1}], "raw": {}},
                ])
                main_mod.APP.store.rebuild_procurement()
                resp = client.get("/api/fbs/procurement")
                self.assertEqual(resp.status_code, 200)
                pid = resp.json()["procurement"][0]["id"]
                resp = client.post(f"/api/fbs/procurement/{pid}/state",
                                   json={"purchase_state": "已下单"})
                self.assertEqual(resp.status_code, 200)
                row = next(r for r in resp.json()["procurement"] if r["id"] == pid)
                self.assertEqual(row["purchase_state"], "已下单")
            finally:
                main_mod.APP.store.close()

    def test_ship_resolves_real_product_id_from_offer_id(self) -> None:
        """P0-B：发货 product_id 必须由 offer_id 反查真实 product_id（info.id），
        不能拿 posting 的 sku 顶替。"""
        import webui.main as main_mod  # noqa: PLC0415
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                main_mod.APP.store.upsert_postings([
                    {"posting_number": "P-1", "ozon_order_id": "O-1",
                     "status": "awaiting_packaging", "ship_by": None, "warehouse_id": None,
                     "products": [{"offer_id": "SKU-1", "sku": 1001, "quantity": 3}], "raw": {}},
                ])
                captured = {}

                # sku=1001，但真实 product_id=777999（不同！）→ 必须用 777999 发货
                def fake_info(settings, offer_ids):  # noqa: ANN001
                    return {"SKU-1": {"id": 777999, "offer_id": "SKU-1"}}

                def fake_ship(settings, posting_number, packages):  # noqa: ANN001
                    captured["posting_number"] = posting_number
                    captured["packages"] = packages
                    return {"result": ["P-1"]}

                adapter.get_ozon_info = fake_info
                adapter.ship_fbs = fake_ship
                resp = client.post("/api/fbs/ship", json={"posting_number": "P-1"})
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.json()["shipped"])
                self.assertEqual(captured["packages"],
                                 [{"products": [{"product_id": 777999, "quantity": 3}]}])

            finally:
                main_mod.APP.store.close()

    def test_ship_errors_when_product_id_unresolved(self) -> None:
        import webui.main as main_mod  # noqa: PLC0415
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                main_mod.APP.store.upsert_postings([
                    {"posting_number": "P-2", "ozon_order_id": "O-2",
                     "status": "awaiting_packaging", "ship_by": None, "warehouse_id": None,
                     "products": [{"offer_id": "SKU-Z", "sku": 9, "quantity": 1}], "raw": {}},
                ])
                adapter.get_ozon_info = lambda settings, offer_ids: {}  # 查不到 → 不发货
                resp = client.post("/api/fbs/ship", json={"posting_number": "P-2"})
                self.assertEqual(resp.status_code, 400)  # 宁可报错也不拿 sku 顶替乱发
            finally:
                main_mod.APP.store.close()

    def test_label_returns_pdf(self) -> None:
        import webui.main as main_mod  # noqa: PLC0415
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                def fake_label(settings, posting_numbers):  # noqa: ANN001
                    return b"%PDF-1.4 x"

                adapter.fbs_label_pdf = fake_label
                resp = client.get("/api/fbs/label?posting=P-1")
                self.assertEqual(resp.status_code, 200)
                self.assertTrue(resp.headers["content-type"].startswith("application/pdf"))
                self.assertTrue(resp.content.startswith(b"%PDF"))
            finally:
                main_mod.APP.store.close()


class GetPostingTest(unittest.TestCase):
    def test_get_posting_roundtrip(self) -> None:
        from webui.store import Store  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "g.db")
            store.upsert_postings([
                {"posting_number": "P-7", "ozon_order_id": "O-7",
                 "status": "awaiting_packaging", "ship_by": "2026-06-01T00:00:00Z",
                 "warehouse_id": 111,
                 "products": [{"offer_id": "SKU-1", "sku": 1001, "quantity": 2}],
                 "raw": {"k": "v"}},
            ])
            posting = store.get_posting("P-7")
            self.assertIsNotNone(posting)
            self.assertEqual(posting["posting_number"], "P-7")
            self.assertEqual(posting["ozon_order_id"], "O-7")
            self.assertEqual(posting["products"], [{"offer_id": "SKU-1", "sku": 1001, "quantity": 2}])
            self.assertIsNone(store.get_posting("nope"))
            store.close()


class ProcurementSortTest(unittest.TestCase):
    """Fix 1: list_procurement 按 ship_by ASC、NULL/空排最后，且每行携带 ship_by。"""

    def _make_store(self, tmp: str):
        from webui.store import Store  # noqa: PLC0415
        return Store(Path(tmp) / "proc_sort.db")

    def test_sorted_by_ship_by_null_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(tmp)
            # 三个 posting：远期 / 近期 / 没有 ship_by
            store.upsert_postings([
                {"posting_number": "P-FAR", "ozon_order_id": "", "status": "awaiting_packaging",
                 "ship_by": "2026-07-15T12:00:00Z", "warehouse_id": None,
                 "products": [{"offer_id": "SKU-A", "sku": 1, "quantity": 1}], "raw": {}},
                {"posting_number": "P-NEAR", "ozon_order_id": "", "status": "awaiting_packaging",
                 "ship_by": "2026-06-01T08:00:00Z", "warehouse_id": None,
                 "products": [{"offer_id": "SKU-B", "sku": 2, "quantity": 1}], "raw": {}},
                {"posting_number": "P-NULL", "ozon_order_id": "", "status": "awaiting_packaging",
                 "ship_by": None, "warehouse_id": None,
                 "products": [{"offer_id": "SKU-C", "sku": 3, "quantity": 1}], "raw": {}},
            ])
            store.rebuild_procurement()
            rows = store.list_procurement()
            self.assertEqual(len(rows), 3)

            # 顺序：近期 → 远期 → NULL
            self.assertEqual(rows[0]["posting_number"], "P-NEAR")
            self.assertEqual(rows[1]["posting_number"], "P-FAR")
            self.assertEqual(rows[2]["posting_number"], "P-NULL")

            # 每行都有 ship_by 字段
            for r in rows:
                self.assertIn("ship_by", r)

            # NULL posting 的 ship_by 是空字符串或 None（JOIN 产出 COALESCE '' 或 NULL）
            self.assertFalse(rows[2]["ship_by"])  # '' or None both falsy

            store.close()

    def test_ship_by_value_carried_in_row(self) -> None:
        """每条 procurement 行的 ship_by 必须等于对应 posting 的值。"""
        with tempfile.TemporaryDirectory() as tmp:
            store = self._make_store(tmp)
            store.upsert_postings([
                {"posting_number": "P-X", "ozon_order_id": "", "status": "awaiting_packaging",
                 "ship_by": "2026-06-10T00:00:00Z", "warehouse_id": None,
                 "products": [{"offer_id": "SKU-X", "sku": 10, "quantity": 2}], "raw": {}},
            ])
            store.rebuild_procurement()
            rows = store.list_procurement()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["ship_by"], "2026-06-10T00:00:00Z")
            store.close()


if __name__ == "__main__":
    unittest.main()
