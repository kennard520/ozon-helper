import importlib
import tempfile
import unittest
from pathlib import Path


class BatchPublishTest(unittest.TestCase):
    def _app(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "bp.db"
        import backend.app_service as svc
        importlib.reload(svc)
        return svc.App()

    def test_aggregates_and_isolates_failures(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                calls = []

                def fake_publish(did, store_client_id=None):
                    calls.append((did, store_client_id))
                    if did == 2:
                        raise RuntimeError("boom")          # 抛异常的单个不影响其它
                    if did == 3:
                        return {"published": False, "errors": ["余额不足"]}
                    return {"published": True}

                app.publish = fake_publish
                r = app.batch_publish([1, 2, 3], store_client_id="cid")
                self.assertEqual(r["published"], 1)        # 只有 #1 成功
                self.assertEqual(r["failed"], 2)           # #2 异常 + #3 余额不足
                self.assertEqual(len(r["results"]), 3)
                self.assertEqual([c[0] for c in calls], [1, 2, 3])
                self.assertTrue(all(c[1] == "cid" for c in calls))  # 目标店透传
                byid = {x["id"]: x for x in r["results"]}
                self.assertTrue(byid[1]["published"])
                self.assertEqual(byid[2]["errors"], ["boom"])
                self.assertEqual(byid[3]["errors"], ["余额不足"])
            finally:
                app.store.close()

    def test_empty_ids(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                r = app.batch_publish([])
                self.assertEqual(r, {"results": [], "published": 0, "failed": 0})
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
