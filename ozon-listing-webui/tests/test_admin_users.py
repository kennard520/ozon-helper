import importlib
import tempfile
import unittest
from pathlib import Path


def fresh_store(tmp):
    # 设模块级 DEFAULT_DB 指向临时库（Store.__init__ 调用时读它）。本地无 OZON_MYSQL_HOST → 走 SQLite。
    import backend.store as store_mod
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


if __name__ == "__main__":
    unittest.main()
