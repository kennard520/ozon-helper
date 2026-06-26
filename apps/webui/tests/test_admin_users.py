import importlib
import tempfile
import unittest
from pathlib import Path


def fresh_store(tmp):
    # 设模块级 DEFAULT_DB 指向临时库（Store.__init__ 调用时读它）。本地无 OZON_MYSQL_HOST → 走 SQLite。
    import webui.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "t.db"
    return store_mod.Store()


class StoreUserTest(unittest.TestCase):
    def test_create_user_with_max_stores(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = fresh_store(tmp)
            try:
                u = s.create_user("alice", "h", role="user", max_stores=3)
                self.assertEqual(u["max_stores"], 3)
                got = s.get_user_by_id(u["id"])
                self.assertEqual(got["max_stores"], 3)
            finally:
                s.close()

    def test_create_user_default_max_stores_is_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = fresh_store(tmp)
            try:
                u = s.create_user("bob", "h")
                self.assertEqual(u["max_stores"], 1)
            finally:
                s.close()

    def test_list_and_mutate_users(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = fresh_store(tmp)
            try:
                a = s.create_user("alice", "h1", max_stores=2)
                s.create_user("bob", "h2", max_stores=5)
                rows = s.list_users()
                names = {r["username"] for r in rows}
                self.assertEqual(names, {"alice", "bob"})
                self.assertTrue(all("password_hash" not in r for r in rows))  # 不外泄哈希

                s.set_max_stores(a["id"], 9)
                self.assertEqual(s.get_user_by_id(a["id"])["max_stores"], 9)

                s.set_status(a["id"], "disabled")
                self.assertEqual(s.get_user_by_id(a["id"])["status"], "disabled")

                s.set_password_hash(a["id"], "newhash")
                self.assertEqual(s.get_user_by_id(a["id"])["password_hash"], "newhash")
            finally:
                s.close()


class AdminApiTest(unittest.TestCase):
    def _client(self, tmp):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "api.db"
        import webui.app_service as svc
        importlib.reload(svc)
        import webui.main as main_mod
        importlib.reload(main_mod)
        from fastapi.testclient import TestClient
        self._main = main_mod
        return TestClient(main_mod.app)

    def _admin_token(self, client):
        # 首启自动建 admin/admin
        return client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()["token"]

    def test_public_register_removed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                r = client.post("/api/auth/register", json={"username": "x", "password": "secret1"})
                # 路由已删除：POST 落到根静态 catch-all（只允许 GET/HEAD）→ 405；总之非 2xx
                self.assertIn(r.status_code, (404, 405))
            finally:
                self._main.APP.store.close()

    def test_disabled_user_cannot_login(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                from webui.auth import hash_password
                u = self._main.APP.store.create_user("carol", hash_password("secret1"))
                self._main.APP.store.set_status(u["id"], "disabled")
                r = client.post("/api/auth/login", json={"username": "carol", "password": "secret1"})
                self.assertEqual(r.status_code, 400)
            finally:
                self._main.APP.store.close()

    def test_admin_endpoints_require_admin(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                # 无 token → 401/403
                self.assertIn(client.get("/api/admin/users").status_code, (401, 403))
                # 普通用户 token → 403
                from webui.auth import hash_password
                self._main.APP.store.create_user("dave", hash_password("secret1"))
                t = client.post("/api/auth/login", json={"username": "dave", "password": "secret1"}).json()["token"]
                r = client.get("/api/admin/users", headers={"Authorization": "Bearer " + t})
                self.assertEqual(r.status_code, 403)
            finally:
                self._main.APP.store.close()

    def test_admin_crud_user(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                H = {"Authorization": "Bearer " + self._admin_token(client)}
                # 创建
                r = client.post("/api/admin/users", headers=H,
                                json={"username": "erin", "password": "secret1", "max_stores": 4})
                self.assertEqual(r.status_code, 200)
                uid = r.json()["id"]
                self.assertEqual(r.json()["max_stores"], 4)
                # 列出含 store_count
                rows = client.get("/api/admin/users", headers=H).json()["users"]
                erin = [x for x in rows if x["id"] == uid][0]
                self.assertEqual(erin["max_stores"], 4)
                self.assertIn("store_count", erin)
                # 改上限
                client.patch(f"/api/admin/users/{uid}", headers=H, json={"max_stores": 7})
                rows = client.get("/api/admin/users", headers=H).json()["users"]
                self.assertEqual([x for x in rows if x["id"] == uid][0]["max_stores"], 7)
                # 重置密码 → 新密码可登录
                client.patch(f"/api/admin/users/{uid}", headers=H, json={"password": "newpass1"})
                self.assertEqual(client.post("/api/auth/login",
                                 json={"username": "erin", "password": "newpass1"}).status_code, 200)
                # 禁用 → 登录失败
                client.patch(f"/api/admin/users/{uid}", headers=H, json={"status": "disabled"})
                self.assertEqual(client.post("/api/auth/login",
                                 json={"username": "erin", "password": "newpass1"}).status_code, 400)
            finally:
                self._main.APP.store.close()

    def test_admin_create_validation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                H = {"Authorization": "Bearer " + self._admin_token(client)}
                self.assertEqual(client.post("/api/admin/users", headers=H,
                                 json={"username": "ab", "password": "secret1"}).status_code, 400)   # 名太短
                self.assertEqual(client.post("/api/admin/users", headers=H,
                                 json={"username": "frank", "password": "123"}).status_code, 400)     # 密码太短
                client.post("/api/admin/users", headers=H, json={"username": "grace", "password": "secret1"})
                self.assertEqual(client.post("/api/admin/users", headers=H,
                                 json={"username": "grace", "password": "secret1"}).status_code, 400)  # 重名
            finally:
                self._main.APP.store.close()

    def test_admin_cannot_disable_self(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                H = {"Authorization": "Bearer " + self._admin_token(client)}
                me = client.get("/api/auth/me", headers=H).json()["user"]
                r = client.patch(f"/api/admin/users/{me['id']}", headers=H, json={"status": "disabled"})
                self.assertEqual(r.status_code, 400)
            finally:
                self._main.APP.store.close()

    def test_store_quota_enforced(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                H = {"Authorization": "Bearer " + self._admin_token(client)}
                client.post("/api/admin/users", headers=H,
                            json={"username": "frank", "password": "secret1", "max_stores": 1})
                ft = client.post("/api/auth/login", json={"username": "frank", "password": "secret1"}).json()["token"]
                FH = {"Authorization": "Bearer " + ft}
                two = [{"name": "s1", "client_id": "111", "api_key": "k1", "is_default": True},
                       {"name": "s2", "client_id": "222", "api_key": "k2"}]
                r = client.post("/api/settings", headers=FH, json={"ozon_stores": two})
                self.assertEqual(r.status_code, 400)
                # admin 不受限
                r2 = client.post("/api/settings", headers=H, json={"ozon_stores": two})
                self.assertEqual(r2.status_code, 200)
            finally:
                self._main.APP.store.close()

    def test_admin_delete_user_cascades(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                H = {"Authorization": "Bearer " + self._admin_token(client)}
                uid = client.post("/api/admin/users", headers=H,
                                  json={"username": "henry", "password": "secret1"}).json()["id"]
                # 给 henry 插一条草稿
                from webui.drafts import create_draft_from_url
                self._main.APP.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/h.html"), user_id=uid)
                self.assertEqual(len(self._main.APP.store.list_drafts(user_id=uid)), 1)
                # 删用户 → 用户没了 + 草稿级联删除
                r = client.delete(f"/api/admin/users/{uid}", headers=H)
                self.assertEqual(r.status_code, 200)
                self.assertIsNone(self._main.APP.store.get_user_by_id(uid))
                self.assertEqual(self._main.APP.store.list_drafts(user_id=uid), [])
            finally:
                self._main.APP.store.close()

    def test_admin_cannot_delete_self_or_admin(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                H = {"Authorization": "Bearer " + self._admin_token(client)}
                me = client.get("/api/auth/me", headers=H).json()["user"]
                # 不能删自己（自己就是 admin）
                self.assertEqual(client.delete(f"/api/admin/users/{me['id']}", headers=H).status_code, 400)
            finally:
                self._main.APP.store.close()


if __name__ == "__main__":
    unittest.main()
