from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from webui.app_service import App
from webui.store import Store


def _app(tmp: str) -> App:
    app = App()
    app.store.close()                          # 关掉默认库连接
    app.store = Store(Path(tmp) / "test.db")   # 隔离到临时库
    return app


class RealfbsRoutesTest(unittest.TestCase):
    def test_seed_on_first_read_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _app(tmp)
            try:
                res = app.realfbs_routes()
                self.assertGreater(len(res["routes"]), 100)        # 灌入种子(141 条)
                self.assertIn("provider", res["routes"][0])
                self.assertIn("rateText", res["routes"][0])
                # 已持久化：第二次读数量一致（来自 DB，不再灌种子）
                self.assertEqual(len(app.realfbs_routes()["routes"]), len(res["routes"]))
            finally:
                app.store.close()

    def test_import_overwrites_and_export_roundtrips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _app(tmp)
            try:
                csv_in = (
                    "scoringGroup,serviceLevel,provider,deliveryMethod,ozonRating,etaDays,rateText,"
                    "batteries,liquids,measurements,weightMinG,weightMaxG,valueRangeRub,tarification,"
                    "volumeFormula,compensationRub\n"
                    'Extra Small,Economy,TESTX,TESTX Economy,3.0,17-29,"¥2.6 + ¥0.024/1 g",'
                    'Allowed,Forbidden,"Sum of sides ≤ 150 cm, length ≤ 60 cm",1,30000,1 - 1500,'
                    "Physical weight,-,1500\n"
                )
                self.assertEqual(app.import_realfbs_routes(csv_in)["count"], 1)
                routes = app.realfbs_routes()["routes"]
                self.assertEqual(len(routes), 1)                    # 整表覆盖（不是追加）
                self.assertEqual(routes[0]["provider"], "TESTX")
                self.assertEqual(routes[0]["weightMaxG"], 30000.0)  # 数值列转 float
                self.assertEqual(routes[0]["ozonRating"], 3.0)
                # 带逗号字段经 CSV 引号正确保留（不串列）
                self.assertEqual(routes[0]["measurements"], "Sum of sides ≤ 150 cm, length ≤ 60 cm")
                # 导出→再导入 等价
                csv_out = app.export_realfbs_routes_csv()
                self.assertIn("TESTX", csv_out)
                app.import_realfbs_routes(csv_out)
                again = app.realfbs_routes()["routes"]
                self.assertEqual(len(again), 1)
                self.assertEqual(again[0]["measurements"], "Sum of sides ≤ 150 cm, length ≤ 60 cm")
            finally:
                app.store.close()

    def test_import_no_data_rows_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _app(tmp)
            try:
                with self.assertRaises(ValueError):
                    app.import_realfbs_routes("scoringGroup,provider,rateText\n")  # 只有表头
            finally:
                app.store.close()

    def test_store_get_set_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            try:
                self.assertIsNone(store.get_realfbs_routes())       # 空 → None
                store.set_realfbs_routes([{"provider": "A"}, {"provider": "B"}])
                got = store.get_realfbs_routes()
                self.assertEqual([r["provider"] for r in got], ["A", "B"])
                store.set_realfbs_routes([{"provider": "C"}])       # 覆盖
                self.assertEqual([r["provider"] for r in store.get_realfbs_routes()], ["C"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
