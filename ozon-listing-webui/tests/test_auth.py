import importlib
import tempfile
import unittest
from pathlib import Path

from backend.auth import hash_password, verify_password, make_token, decode_token


class AuthCryptoTest(unittest.TestCase):
    def test_password_roundtrip(self):
        h = hash_password("hunter2")
        self.assertTrue(h.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("hunter2", h))
        self.assertFalse(verify_password("wrong", h))

    def test_password_salts_differ(self):
        self.assertNotEqual(hash_password("x"), hash_password("x"))  # 每次盐不同

    def test_token_roundtrip(self):
        t = make_token(42, "secret", now=1000)
        payload = decode_token(t, "secret", now=1001)
        self.assertEqual(payload["sub"], 42)

    def test_token_wrong_secret(self):
        t = make_token(42, "secret", now=1000)
        self.assertIsNone(decode_token(t, "other", now=1001))

    def test_token_expired(self):
        t = make_token(42, "secret", ttl=10, now=1000)
        self.assertIsNone(decode_token(t, "secret", now=2000))

    def test_token_tampered(self):
        t = make_token(42, "secret", now=1000)
        self.assertIsNone(decode_token(t + "x", "secret", now=1001))
        self.assertIsNone(decode_token("garbage", "secret", now=1001))


class AuthFlowTest(unittest.TestCase):
    def _app(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "auth.db"
        import backend.app_service as svc
        importlib.reload(svc)
        return svc.App()

    def test_default_admin_created(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                admin = app.store.get_user_by_username("admin")
                self.assertIsNotNone(admin)
                self.assertEqual(admin["id"], 1)
                self.assertEqual(admin["role"], "admin")
                self.assertTrue(app.auth_secret())  # 生成了密钥
            finally:
                app.store.close()

    def test_register_then_login(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                r = app.register("alice", "secret1")
                self.assertEqual(r["user"]["username"], "alice")
                self.assertTrue(r["token"])
                # token 能解析回该用户
                me = app.user_from_token(r["token"])
                self.assertEqual(me["username"], "alice")
                # 登录拿到 token
                lg = app.login("alice", "secret1")
                self.assertTrue(lg["token"])
            finally:
                app.store.close()

    def test_login_wrong_password(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                app.register("bob", "secret1")
                with self.assertRaises(ValueError):
                    app.login("bob", "nope")
            finally:
                app.store.close()

    def test_register_validation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                with self.assertRaises(ValueError):
                    app.register("ab", "secret1")       # 用户名太短
                with self.assertRaises(ValueError):
                    app.register("carol", "123")        # 密码太短
                app.register("carol", "secret1")
                with self.assertRaises(ValueError):
                    app.register("carol", "secret1")    # 重名
            finally:
                app.store.close()

    def test_bad_token_returns_none(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                self.assertIsNone(app.user_from_token("garbage.token.here"))
                self.assertIsNone(app.user_from_token(""))
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
