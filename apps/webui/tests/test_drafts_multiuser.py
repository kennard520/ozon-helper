import tempfile
import unittest
from pathlib import Path

from webui.drafts import create_draft_from_url
from webui.store import Store


class DraftsMultiUserTest(unittest.TestCase):
    def _store(self, tmp):
        return Store(Path(tmp) / "d.db")

    def test_list_isolated_by_user(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.insert_draft(create_draft_from_url("https://detail.1688.com/offer/111.html"), user_id=1)
                s.insert_draft(create_draft_from_url("https://detail.1688.com/offer/222.html"), user_id=2)
                self.assertEqual(len(s.list_drafts(1)), 1)
                self.assertEqual(len(s.list_drafts(2)), 1)
                self.assertEqual(s.list_drafts(1)[0]["source_url"], "https://detail.1688.com/offer/111.html")
            finally:
                s.close()

    def test_same_url_different_users_both_kept(self):
        # 核心：两个用户采同一链接，各自建草稿，不串数据、不撞唯一约束
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                url = "https://detail.1688.com/offer/999.html"
                d1 = s.insert_draft(create_draft_from_url(url), user_id=1)
                d2 = s.insert_draft(create_draft_from_url(url), user_id=2)
                self.assertNotEqual(d1["id"], d2["id"])
                self.assertEqual(d1["user_id"], 1)
                self.assertEqual(d2["user_id"], 2)
                # 同用户重复采 → 去重返回原草稿
                d1b = s.insert_draft(create_draft_from_url(url), user_id=1)
                self.assertEqual(d1b["id"], d1["id"])
            finally:
                s.close()

    def test_get_update_delete_scoped(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                d = s.insert_draft(create_draft_from_url("https://detail.1688.com/offer/333.html"), user_id=1)
                did = d["id"]
                # 别的用户取不到/改不到/删不到
                self.assertIsNone(s.get_draft(did, user_id=2))
                with self.assertRaises(KeyError):
                    s.update_draft(did, {"ozon_title": "hack"}, user_id=2)
                s.delete_draft(did, user_id=2)            # 删别人 → 无效
                self.assertIsNotNone(s.get_draft(did, user_id=1))  # 仍在
                s.delete_draft(did, user_id=1)            # 自己删 → 成功
                self.assertIsNone(s.get_draft(did, user_id=1))
            finally:
                s.close()

    def test_count_and_page_scoped(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                for i in range(3):
                    s.insert_draft(create_draft_from_url(f"https://detail.1688.com/offer/a{i}.html"), user_id=1)
                s.insert_draft(create_draft_from_url("https://detail.1688.com/offer/b.html"), user_id=2)
                self.assertEqual(s.count_by_status(1)["all"], 3)
                self.assertEqual(s.count_by_status(2)["all"], 1)
                rows, total = s.list_drafts_page(status="all", page=1, page_size=20, user_id=1)
                self.assertEqual(total, 3)
                self.assertTrue(all(r["user_id"] == 1 for r in rows))
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
