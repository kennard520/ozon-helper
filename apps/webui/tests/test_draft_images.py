"""draft_images 表阶段1 单测：insert/update 同步、image_types 还原、回填、images_json 已停写。"""

import json
import tempfile
import unittest
from pathlib import Path

from webui.drafts import create_draft_from_url, dumps_json, loads_json
from webui.store import DEFAULT_DB, Store, utc_now_iso


class DraftImagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        DEFAULT_DB_orig = DEFAULT_DB
        import webui.store as store_mod
        store_mod.DEFAULT_DB = self.db_path
        self.store = Store(self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_insert_draft_syncs_images(self):
        """insert_draft 带 images → draft_images 有对应行，get_draft images 一致。"""
        draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
        draft["images"] = ["http://a.com/1.jpg", "http://a.com/2.jpg"]
        draft["source_raw"] = {"image_types": {"http://a.com/1.jpg": "白底", "http://a.com/2.jpg": "场景"}}

        d = self.store.insert_draft(draft)

        rows = self._draft_images_rows(d["id"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["position"], 0)
        self.assertEqual(rows[0]["url"], "http://a.com/1.jpg")
        self.assertEqual(rows[0]["type"], "白底")
        self.assertEqual(rows[1]["position"], 1)
        self.assertEqual(rows[1]["url"], "http://a.com/2.jpg")
        self.assertEqual(rows[1]["type"], "场景")

        # get_draft 拼装一致
        got = self.store.get_draft(d["id"])
        self.assertEqual(got["images"], ["http://a.com/1.jpg", "http://a.com/2.jpg"])
        self.assertEqual(got["source_raw"]["image_types"],
                         {"http://a.com/1.jpg": "白底", "http://a.com/2.jpg": "场景"})

    def test_update_draft_reorders_images(self):
        """update_draft 改 images（换序/新增/删除）→ 表同步。"""
        draft = create_draft_from_url("https://detail.1688.com/offer/876543210987.html")
        draft["images"] = ["a.jpg", "b.jpg", "c.jpg"]
        d = self.store.insert_draft(draft)

        # 换序 + 新增 + 删除 c
        updated = self.store.update_draft(d["id"], {"images": ["c.jpg", "a.jpg", "d.jpg"]})
        self.assertEqual(updated["images"], ["c.jpg", "a.jpg", "d.jpg"])

        rows = self._draft_images_rows(d["id"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["url"], "c.jpg")
        self.assertEqual(rows[1]["url"], "a.jpg")
        self.assertEqual(rows[2]["url"], "d.jpg")

    def test_update_draft_preserves_type_by_url(self):
        """改 images 时已有的 type 按 url 保留，新 URL 无类型=空字符串。"""
        draft = create_draft_from_url("https://detail.1688.com/offer/555555555555.html")
        draft["images"] = ["x.jpg"]
        draft["source_raw"] = {"image_types": {"x.jpg": "白底"}}
        d = self.store.insert_draft(draft)

        updated = self.store.update_draft(d["id"], {"images": ["x.jpg", "y.jpg"]})
        rows = self._draft_images_rows(d["id"])
        self.assertEqual(rows[0]["type"], "白底")   # 保留
        self.assertEqual(rows[1]["type"], "其他")       # 新图无类型→兜底"其他"

    def test_add_draft_image_append(self):
        """add_draft_image 直接追加行，不读改写整数组。"""
        draft = create_draft_from_url("https://detail.1688.com/offer/111111111111.html")
        d = self.store.insert_draft(draft)

        self.store.add_draft_image(d["id"], "gen_1.png", type="卖点", source="generated")
        self.store.add_draft_image(d["id"], "gen_2.png", type="细节", source="generated")

        rows = self._draft_images_rows(d["id"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "gen_1.png")
        self.assertEqual(rows[0]["type"], "卖点")
        self.assertEqual(rows[0]["source"], "generated")
        self.assertEqual(rows[1]["url"], "gen_2.png")

    def test_images_json_is_written_empty(self):
        """images_json 列停用，insert 写空数组占位（SQLite NOT NULL 约束）。"""
        draft = create_draft_from_url("https://detail.1688.com/offer/222222222222.html")
        draft["images"] = ["a.jpg", "b.jpg"]
        d = self.store.insert_draft(draft)

        row = self.store.conn.execute(
            "SELECT images_json FROM drafts WHERE id=?", (d["id"],)
        ).fetchone()
        self.assertEqual(loads_json(row["images_json"], None), [])
        # 但 get_draft 从 draft_images 表读，数据完整
        self.assertEqual(d["images"], ["a.jpg", "b.jpg"])

    def test_backfill_migration(self):
        """回填：images_json 非空且无 draft_images 行的草稿 → 回填到表。"""
        with self.store.lock:
            cur = self.store.conn.execute(
                """INSERT INTO drafts (
                    user_id, store_client_id, source_platform, source_url, source_title,
                    purchase_url, purchase_note, ozon_title, description, category_id,
                    type_id, brand_id, brand_name, price, old_price, stock,
                    images_json, attributes_json, source_raw_json,
                    status, validation_errors_json, created_at, updated_at)
                VALUES (1, '', '1688', 'test://bf', 't', '', '', 't', 't', '1',
                    '', NULL, '', '100', '90', 10, ?, '{}', ?,
                    'ready', '[]', ?, ?)""",
                (dumps_json(["bf_a.jpg", "bf_b.jpg"]),
                 dumps_json({"image_types": {"bf_a.jpg": "白底", "bf_b.jpg": "场景"}}),
                 utc_now_iso(), utc_now_iso()),
            )
            self.store.conn.commit()

        # 回填前表空
        rows_before = self.store.conn.execute(
            "SELECT COUNT(*) c FROM draft_images WHERE draft_id=?", (cur.lastrowid,)
        ).fetchone()["c"]
        self.assertEqual(rows_before, 0)

        from webui.db_backfills import _backfill_draft_images
        with self.store._session_engine.begin() as sa_conn:
            _backfill_draft_images(sa_conn)

        rows = self._draft_images_rows(cur.lastrowid)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "bf_a.jpg")
        self.assertEqual(rows[0]["type"], "白底")
        self.assertEqual(rows[1]["url"], "bf_b.jpg")
        self.assertEqual(rows[1]["type"], "场景")

        # 自限：再跑不重复
        with self.store._session_engine.begin() as sa_conn:
            _backfill_draft_images(sa_conn)
        rows2 = self._draft_images_rows(cur.lastrowid)
        self.assertEqual(len(rows2), 2)

    # ---------- helpers ----------

    def _draft_images_rows(self, draft_id: int) -> list[dict]:
        return [
            dict(r) for r in
            self.store.conn.execute(
                "SELECT * FROM draft_images WHERE draft_id=? ORDER BY position",
                (draft_id,),
            ).fetchall()
        ]


if __name__ == "__main__":
    unittest.main()
