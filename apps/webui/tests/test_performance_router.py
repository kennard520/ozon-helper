from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class PerformanceRouterTest(unittest.TestCase):
    def _client(self, tmp):
        from fastapi.testclient import TestClient

        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import webui.app_service as svc
        importlib.reload(svc)
        import webui.main as main_mod
        importlib.reload(main_mod)
        self._main = main_mod
        return TestClient(main_mod.app)

    def test_campaigns_missing_performance_credentials_returns_400(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                resp = client.get("/api/performance/campaigns")

                self.assertEqual(resp.status_code, 400)
                self.assertIn("Performance API", resp.json()["detail"])
            finally:
                self._main.APP.store.close()

    def test_campaigns_endpoint_returns_service_data(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={
                    "performance_client_id": "cid",
                    "performance_client_secret": "sec",
                })

                import webui.routers.performance as router_mod

                def fake_campaigns(settings):
                    return {"campaigns": [{"id": "11", "title": settings["performance_client_id"]}]}

                with patch.object(router_mod.performance_service, "campaigns", fake_campaigns):
                    resp = client.get("/api/performance/campaigns")

                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json(), {"campaigns": [{"id": "11", "title": "cid"}]})
            finally:
                self._main.APP.store.close()


if __name__ == "__main__":
    unittest.main()
