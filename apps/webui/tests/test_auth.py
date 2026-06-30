import importlib
import tempfile
import unittest
from pathlib import Path

from webui.auth import decode_token, hash_password, make_token, verify_password


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
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "auth.db"
        import webui.app_service as svc
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

    def test_create_then_login(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                from webui.auth import hash_password
                app.store.create_user("alice", hash_password("secret1"))
                lg = app.login("alice", "secret1")
                self.assertEqual(lg["user"]["username"], "alice")
                self.assertTrue(lg["token"])
                # token 能解析回该用户
                me = app.user_from_token(lg["token"])
                self.assertEqual(me["username"], "alice")
            finally:
                app.store.close()

    def test_login_wrong_password(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                from webui.auth import hash_password
                app.store.create_user("bob", hash_password("secret1"))
                with self.assertRaises(ValueError):
                    app.login("bob", "nope")
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
