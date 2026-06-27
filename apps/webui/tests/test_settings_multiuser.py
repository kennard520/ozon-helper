import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

from webui.store import Store


class SettingsMultiUserTest(unittest.TestCase):
    def _store(self, tmp):
        return Store(Path(tmp) / "s.db")

    def test_per_user_isolation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.save_settings({"ozon_api_key": "k1", "rub_cny": 0.1}, user_id=1)
                s.save_settings({"ozon_api_key": "k2", "rub_cny": 0.2}, user_id=2)
                self.assertEqual(s.get_settings(1)["ozon_api_key"], "k1")
                self.assertEqual(s.get_settings(2)["ozon_api_key"], "k2")
                self.assertEqual(s.get_settings(1)["rub_cny"], 0.1)
                self.assertEqual(s.get_settings(2)["rub_cny"], 0.2)
                # 用户1 看不到用户2 的非全局设置
                self.assertNotIn("k2", s.get_settings(1).values())
            finally:
                s.close()

    def test_global_keys_shared(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                # OSS 是系统级全局：任一用户写，所有用户可见
                s.save_settings({"oss_bucket": "shared-bucket"}, user_id=1)
                self.assertEqual(s.get_settings(1)["oss_bucket"], "shared-bucket")
                self.assertEqual(s.get_settings(2)["oss_bucket"], "shared-bucket")
                self.assertEqual(s.get_settings(99)["oss_bucket"], "shared-bucket")
            finally:
                s.close()

    def test_global_not_duplicated_per_user(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.save_settings({"oss_bucket": "b1"}, user_id=1)
                s.save_settings({"oss_bucket": "b2"}, user_id=2)  # 全局键 → 覆盖同一行
                self.assertEqual(s.get_settings(1)["oss_bucket"], "b2")  # 最后写的赢
                with s._session_engine.begin() as c:
                    rows = c.execute(
                        text("SELECT COUNT(*) FROM settings WHERE key='oss_bucket'")
                    ).fetchone()[0]
                self.assertEqual(rows, 1)  # 全局键只有一行(user_id=0)
            finally:
                s.close()

    def test_default_user_is_one(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.save_settings({"contract_currency": "CNY"})  # 默认 user_id=1
                self.assertEqual(s.get_settings()["contract_currency"], "CNY")
                self.assertEqual(s.get_settings(1)["contract_currency"], "CNY")
                self.assertNotIn("contract_currency", s.get_settings(2))
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
