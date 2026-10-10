"""跨变体复制图片改造测试 (Task 6)

覆盖:
  POST /api/drafts/{A}/copy-images-to  body {"image_urls":[url],"target_draft_ids":[B,C]}
  - 多目标 B、C 的 images(图集) 含该 url
  - type/source 按源复制
  - 幂等:再调一次 added=0(按 url 去重)
  - 跨组目标返回 400
  - 兼容旧字段 target_draft_id (单值)
"""
import gc
import importlib
import json
import tempfile
import unittest
from pathlib import Path


class CopyImagesMultiTest(unittest.TestCase):
    # ------------------------------------------------------------------
    # 辅助: 建 TestClient(与 test_gallery_endpoints.py 完全相同的范式)
    # ------------------------------------------------------------------
    def _client(self, tmp):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415

        store_mod.DEFAULT_DB = Path(tmp) / "copy_multi.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app), main_mod

    def _make_draft_with_group(self, app, url_suffix, group):
        """建一个草稿并设 variant_group。"""
        from webui.drafts import create_draft_from_url  # noqa: PLC0415
        d = app.store.insert_draft(
            create_draft_from_url(f"https://detail.1688.com/offer/{url_suffix}.html")
        )
        did = d["id"]
        # 设 variant_group 到 source_raw
        app.store.update_draft(did, {**d, "source_raw": {"variant_group": group}})
        return did

    # ------------------------------------------------------------------
    # 主测试: 多目标复制 + 去重 + type/source 透传
    # ------------------------------------------------------------------
    def test_copy_to_multiple_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                # 建 A/B/C 三变体,同一变体组 VG1
                aid = self._make_draft_with_group(app, "A001", "VG1")
                bid = self._make_draft_with_group(app, "B001", "VG1")
                cid = self._make_draft_with_group(app, "C001", "VG1")

                # 给 A 插入一张图集图(in_gallery=1 => source=generated)
                img_url = "https://cdn.example.com/gallery_img.jpg"
                app.store.add_draft_image(aid, img_url, type="main", source="generated")

                # POST 多目标复制
                resp = client.post(
                    f"/api/drafts/{aid}/copy-images-to",
                    json={"image_urls": [img_url], "target_draft_ids": [bid, cid]},
                )
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["ok"])
                added = body["added"]
                # FastAPI JSON 序列化后 int key → str key
                added_b = added.get(str(bid))
                added_c = added.get(str(cid))
                self.assertEqual(added_b, 1)
                self.assertEqual(added_c, 1)

                # B 和 C 的图集(images)应含该 url
                b_draft = app.store.get_draft(bid)
                c_draft = app.store.get_draft(cid)
                self.assertIn(img_url, b_draft["images"])
                self.assertIn(img_url, c_draft["images"])

            finally:
                main_mod.APP.store.close()
                gc.collect()

    # ------------------------------------------------------------------
    # 去重: 第二次复制 added=0
    # ------------------------------------------------------------------
    def test_dedup_on_second_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                aid = self._make_draft_with_group(app, "A002", "VG2")
                bid = self._make_draft_with_group(app, "B002", "VG2")

                img_url = "https://cdn.example.com/img2.jpg"
                app.store.add_draft_image(aid, img_url, type="detail", source="generated")

                # 第一次复制
                resp1 = client.post(
                    f"/api/drafts/{aid}/copy-images-to",
                    json={"image_urls": [img_url], "target_draft_ids": [bid]},
                )
                self.assertEqual(resp1.status_code, 200)
                added1 = resp1.json()["added"]
                # FastAPI JSON 序列化后 int key → str key
                v1 = added1.get(str(bid))
                self.assertEqual(v1, 1)

                # 第二次复制 → 去重, added=0
                resp2 = client.post(
                    f"/api/drafts/{aid}/copy-images-to",
                    json={"image_urls": [img_url], "target_draft_ids": [bid]},
                )
                self.assertEqual(resp2.status_code, 200)
                added2 = resp2.json()["added"]
                v2 = added2.get(str(bid))
                self.assertEqual(v2, 0)

            finally:
                main_mod.APP.store.close()
                gc.collect()

    # ------------------------------------------------------------------
    # 跨组目标 → 400
    # ------------------------------------------------------------------
    def test_cross_group_returns_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                aid = self._make_draft_with_group(app, "A003", "VG_SRC")
                xid = self._make_draft_with_group(app, "X003", "VG_OTHER")

                img_url = "https://cdn.example.com/img3.jpg"
                app.store.add_draft_image(aid, img_url, type="main", source="generated")

                resp = client.post(
                    f"/api/drafts/{aid}/copy-images-to",
                    json={"image_urls": [img_url], "target_draft_ids": [xid]},
                )
                self.assertEqual(resp.status_code, 400)

            finally:
                main_mod.APP.store.close()
                gc.collect()

    # ------------------------------------------------------------------
    # 兼容旧字段 target_draft_id (单值)
    # ------------------------------------------------------------------
    def test_compat_single_target_draft_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                aid = self._make_draft_with_group(app, "A004", "VG4")
                bid = self._make_draft_with_group(app, "B004", "VG4")

                img_url = "https://cdn.example.com/img4.jpg"
                app.store.add_draft_image(aid, img_url, type="main", source="generated")

                # 用旧字段 target_draft_id 传单值
                resp = client.post(
                    f"/api/drafts/{aid}/copy-images-to",
                    json={"image_urls": [img_url], "target_draft_id": bid},
                )
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["ok"])
                # added 是 dict, FastAPI JSON 序列化后 int key → str key
                self.assertIsInstance(body["added"], dict)
                added_b = body["added"].get(str(bid))
                self.assertEqual(added_b, 1)

                b_draft = app.store.get_draft(bid)
                self.assertIn(img_url, b_draft["images"])

            finally:
                main_mod.APP.store.close()
                gc.collect()

    # ------------------------------------------------------------------
    # type/source 按源复制
    # ------------------------------------------------------------------
    def test_type_source_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                aid = self._make_draft_with_group(app, "A005", "VG5")
                bid = self._make_draft_with_group(app, "B005", "VG5")

                img_url = "https://cdn.example.com/img5.jpg"
                # source=collected, type=infographic
                app.store.add_draft_image(aid, img_url, type="infographic", source="collected")

                resp = client.post(
                    f"/api/drafts/{aid}/copy-images-to",
                    json={"image_urls": [img_url], "target_draft_ids": [bid]},
                )
                self.assertEqual(resp.status_code, 200)

                # 验证 B 的图集包含该 url 且 in_gallery=1 (images 列表里)
                b_draft = app.store.get_draft(bid)
                self.assertIn(img_url, b_draft["images"])

            finally:
                main_mod.APP.store.close()
                gc.collect()
