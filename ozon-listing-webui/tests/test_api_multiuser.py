import importlib
import tempfile
import unittest
from pathlib import Path


class ApiMultiUserTest(unittest.TestCase):
    def _client(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "api.db"
        import backend.app_service as svc
        importlib.reload(svc)
        import backend.main as main_mod
        importlib.reload(main_mod)
        from fastapi.testclient import TestClient
        self._main = main_mod
        return TestClient(main_mod.app)

    def test_drafts_isolated_by_token(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                from backend.drafts import create_draft_from_url
                # 两个用户注册
                ta = client.post("/api/auth/register", json={"username": "alice", "password": "secret1"}).json()
                tb = client.post("/api/auth/register", json={"username": "bob", "password": "secret1"}).json()
                ua, ub = ta["user"]["id"], tb["user"]["id"]
                self.assertNotEqual(ua, ub)
                # 各自插一条草稿（直接走 store，带各自 user_id）
                store = self._main.APP.store
                store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/aaa.html"), user_id=ua)
                store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/bbb.html"), user_id=ub)
                # alice 带 token 拉 → 只见自己的（验证中间件→ContextVar→store 端到端隔离）
                ra = client.get("/api/drafts", headers={"Authorization": "Bearer " + ta["token"]}).json()
                self.assertEqual(ra["total"], 1)
                self.assertEqual(ra["drafts"][0]["source_url"], "https://detail.1688.com/offer/aaa.html")
                rb = client.get("/api/drafts", headers={"Authorization": "Bearer " + tb["token"]}).json()
                self.assertEqual(rb["total"], 1)
                self.assertEqual(rb["drafts"][0]["source_url"], "https://detail.1688.com/offer/bbb.html")
            finally:
                self._main.APP.store.close()

    def test_no_token_defaults_admin(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                from backend.drafts import create_draft_from_url
                store = self._main.APP.store
                store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/admin.html"), user_id=1)
                # 无 token → 默认 admin(user 1)，看得到 admin 的草稿（保旧客户端/测试兼容）
                r = client.get("/api/drafts").json()
                self.assertEqual(r["total"], 1)
            finally:
                self._main.APP.store.close()

    def test_me_requires_token(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                self.assertEqual(client.get("/api/auth/me").status_code, 401)
                t = client.post("/api/auth/register", json={"username": "carol", "password": "secret1"}).json()
                r = client.get("/api/auth/me", headers={"Authorization": "Bearer " + t["token"]})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["user"]["username"], "carol")
            finally:
                self._main.APP.store.close()


if __name__ == "__main__":
    unittest.main()
