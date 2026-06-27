"""draft_images 表阶段1 单测：insert/update 同步、image_types 还原、回填、images_json 已停写。"""

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

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

        # 语义变更:采集图→素材(in_gallery=0),图集为空;从 materials 验证
        got = self.store.get_draft(d["id"])
        self.assertEqual(got["images"], [])
        material_urls = {m["url"] for m in got["materials"]}
        self.assertEqual(material_urls, {"http://a.com/1.jpg", "http://a.com/2.jpg"})

    def test_update_draft_reorders_images(self):
        """update_draft 改 images（换序/新增/删除）→ 图集同步;素材行保留不删。"""
        draft = create_draft_from_url("https://detail.1688.com/offer/876543210987.html")
        draft["images"] = ["a.jpg", "b.jpg", "c.jpg"]
        d = self.store.insert_draft(draft)

        # 换序 + 新增 d + c 留图集 + b 降级为素材(不在目标里)
        # gallery=True 语义:目标 ["c.jpg","a.jpg","d.jpg"]
        #   - a/c 已是素材,提升为图集
        #   - b 已是素材,不在目标里,保持素材(in_gallery=0)
        #   - d 新插入图集
        updated = self.store.update_draft(d["id"], {"images": ["c.jpg", "a.jpg", "d.jpg"]})
        self.assertEqual(updated["images"], ["c.jpg", "a.jpg", "d.jpg"])

        rows = self._draft_images_rows(d["id"])
        # 语义变更:_sync gallery=True 不删行,素材行 b 保留 → 共 4 行
        self.assertEqual(len(rows), 4)
        # 图集行:c/a/d(按 position 排序)
        gallery_rows = [r for r in rows if r["in_gallery"] == 1]
        gallery_urls = [r["url"] for r in gallery_rows]
        self.assertEqual(gallery_urls, ["c.jpg", "a.jpg", "d.jpg"])
        # 素材行:b(降级)
        material_rows = [r for r in rows if r["in_gallery"] == 0]
        self.assertEqual([r["url"] for r in material_rows], ["b.jpg"])

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

        with self.store._session_engine.begin() as c:
            row = c.execute(
                text("SELECT images_json FROM drafts WHERE id=:id"), {"id": d["id"]}
            ).mappings().fetchone()
        self.assertEqual(loads_json(row["images_json"], None), [])
        # 语义变更:采集图→素材(in_gallery=0),图集为空;materials 有 2 张
        self.assertEqual(d["images"], [])
        material_urls = {m["url"] for m in d["materials"]}
        self.assertEqual(material_urls, {"a.jpg", "b.jpg"})

    def test_backfill_migration(self):
        """回填：images_json 非空且无 draft_images 行的草稿 → 回填到表。"""
        with self.store._session_engine.begin() as c:
            cur = c.execute(
                text("""INSERT INTO drafts (
                    user_id, store_client_id, source_platform, source_url, source_title,
                    purchase_url, purchase_note, ozon_title, description, category_id,
                    type_id, brand_id, brand_name, price, old_price, stock,
                    images_json, attributes_json, source_raw_json,
                    status, validation_errors_json, created_at, updated_at)
                VALUES (1, '', '1688', 'test://bf', 't', '', '', 't', 't', '1',
                    '', NULL, '', '100', '90', 10, :images, '{}', :raw,
                    'ready', '[]', :created, :updated)"""),
                {
                    "images": dumps_json(["bf_a.jpg", "bf_b.jpg"]),
                    "raw": dumps_json({"image_types": {"bf_a.jpg": "白底", "bf_b.jpg": "场景"}}),
                    "created": utc_now_iso(),
                    "updated": utc_now_iso(),
                },
            )
            draft_id = cur.lastrowid

        # 回填前表空
        with self.store._session_engine.begin() as c:
            rows_before = c.execute(
                text("SELECT COUNT(*) c FROM draft_images WHERE draft_id=:id"), {"id": draft_id}
            ).mappings().fetchone()["c"]
        self.assertEqual(rows_before, 0)

        from webui.db_backfills import _backfill_draft_images
        with self.store._session_engine.begin() as sa_conn:
            _backfill_draft_images(sa_conn)

        rows = self._draft_images_rows(draft_id)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], "bf_a.jpg")
        self.assertEqual(rows[0]["type"], "白底")
        self.assertEqual(rows[1]["url"], "bf_b.jpg")
        self.assertEqual(rows[1]["type"], "场景")

        # 自限：再跑不重复
        with self.store._session_engine.begin() as sa_conn:
            _backfill_draft_images(sa_conn)
        rows2 = self._draft_images_rows(draft_id)
        self.assertEqual(len(rows2), 2)

    # ---------- helpers ----------

    def _draft_images_rows(self, draft_id: int) -> list[dict]:
        with self.store._session_engine.begin() as c:
            return [
                dict(r) for r in
                c.execute(
                    text("SELECT * FROM draft_images WHERE draft_id=:id ORDER BY position"),
                    {"id": draft_id},
                ).mappings().fetchall()
            ]


if __name__ == "__main__":
    unittest.main()
