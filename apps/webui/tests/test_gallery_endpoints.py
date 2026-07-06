"""图集管理 HTTP 端点测试 (TDD)

测试覆盖:
  POST /api/drafts/{id}/gallery/add    → 素材进图集
  POST /api/drafts/{id}/gallery/remove → 图集移出(素材保留)
  POST /api/drafts/{id}/gallery/reorder → 重排图集
  DELETE /api/drafts/{id}/images/{image_id} → 彻底删图
"""
import gc
import importlib
import tempfile
import unittest
from pathlib import Path


class GalleryEndpointsTest(unittest.TestCase):
    # ------------------------------------------------------------------
    # 辅助: 建 TestClient(与 test_api.py 里 ApiWriteTest._client 完全相同)
    # ------------------------------------------------------------------
    def _client(self, tmp):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415

        store_mod.DEFAULT_DB = Path(tmp) / "gallery.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return TestClient(main_mod.app), main_mod

    # ------------------------------------------------------------------
    # add: 素材(in_gallery=0)进图集后出现在 images
    # ------------------------------------------------------------------
    def test_gallery_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                # 建草稿
                from webui.drafts import create_draft_from_url  # noqa: PLC0415
                d = app.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/111.html")
                )
                did = d["id"]
                # 以 source="collected" 插入素材(in_gallery=0)
                img_id = app.store.add_draft_image(did, "https://example.com/a.jpg",
                                                   source="collected")
                # 确认未进图集
                before = app.store.get_draft(did)
                self.assertNotIn("https://example.com/a.jpg", before["images"])

                # POST gallery/add
                resp = client.post(f"/api/drafts/{did}/gallery/add",
                                   json={"image_ids": [img_id]})
                self.assertEqual(resp.status_code, 200)
                draft = resp.json()
                self.assertIn("https://example.com/a.jpg", draft["images"])
            finally:
                main_mod.APP.store.close()
                gc.collect()  # 释放 TestClient/连接句柄,否则 Windows 删不掉临时库

    def test_upload_media_adds_one_gallery_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                from webui.drafts import create_draft_from_url  # noqa: PLC0415
                d = app.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/555.html")
                )
                did = d["id"]

                resp = client.post(
                    f"/api/drafts/{did}/media",
                    files={"file": ("a.png", b"fake-image", "image/png")},
                    data={"kind": "image"},
                )
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["url"].startswith("/media/draft-"))
                draft = app.store.get_draft(did)
                self.assertEqual(draft["images"].count(body["url"]), 1)

                img_id = app.store.add_draft_image(did, body["url"], source="uploaded", in_gallery=1)
                draft2 = app.store.get_draft(did)
                self.assertEqual(draft2["images"].count(body["url"]), 1)
                self.assertEqual(img_id, body["image_id"])
            finally:
                main_mod.APP.store.close()
                gc.collect()

    # ------------------------------------------------------------------
    # remove: 图集中移出后 images 不含,但 materials 仍在
    # ------------------------------------------------------------------
    def test_gallery_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                from webui.drafts import create_draft_from_url  # noqa: PLC0415
                d = app.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/222.html")
                )
                did = d["id"]
                # 插入素材并加入图集
                img_id = app.store.add_draft_image(did, "https://example.com/b.jpg",
                                                   source="collected")
                app.store.gallery_add(did, [img_id])

                before = app.store.get_draft(did)
                self.assertIn("https://example.com/b.jpg", before["images"])

                # POST gallery/remove
                resp = client.post(f"/api/drafts/{did}/gallery/remove",
                                   json={"image_ids": [img_id]})
                self.assertEqual(resp.status_code, 200)
                draft = resp.json()
                # 图集中不含该 url
                self.assertNotIn("https://example.com/b.jpg", draft["images"])
                # materials 中仍存在(只移出图集,不删行)
                mat_ids = [m["id"] for m in draft.get("materials", [])]
                self.assertIn(img_id, mat_ids)
            finally:
                main_mod.APP.store.close()
                gc.collect()  # 释放 TestClient/连接句柄,否则 Windows 删不掉临时库

    # ------------------------------------------------------------------
    # delete: 彻底删除,materials 不含
    # ------------------------------------------------------------------
    def test_gallery_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                from webui.drafts import create_draft_from_url  # noqa: PLC0415
                d = app.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/333.html")
                )
                did = d["id"]
                img_id = app.store.add_draft_image(did, "https://example.com/c.jpg",
                                                   source="collected")

                # DELETE /api/drafts/{did}/images/{img_id}
                resp = client.delete(f"/api/drafts/{did}/images/{img_id}")
                self.assertEqual(resp.status_code, 200)
                draft = resp.json()
                mat_ids = [m["id"] for m in draft.get("materials", [])]
                self.assertNotIn(img_id, mat_ids)
                self.assertNotIn("https://example.com/c.jpg", draft.get("images", []))
            finally:
                main_mod.APP.store.close()
                gc.collect()  # 释放 TestClient/连接句柄,否则 Windows 删不掉临时库

    # ------------------------------------------------------------------
    # reorder: 重排后 images 顺序一致
    # ------------------------------------------------------------------
    def test_gallery_reorder(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = self._client(tmp)
            try:
                app = main_mod.APP
                from webui.drafts import create_draft_from_url  # noqa: PLC0415
                d = app.store.insert_draft(
                    create_draft_from_url("https://detail.1688.com/offer/444.html")
                )
                did = d["id"]
                id1 = app.store.add_draft_image(did, "https://example.com/x1.jpg",
                                                source="collected")
                id2 = app.store.add_draft_image(did, "https://example.com/x2.jpg",
                                                source="collected")
                # 先加入图集(顺序 x1, x2)
                app.store.gallery_add(did, [id1, id2])

                # reorder: 改成 x2, x1
                resp = client.post(f"/api/drafts/{did}/gallery/reorder",
                                   json={"image_ids": [id2, id1]})
                self.assertEqual(resp.status_code, 200)
                draft = resp.json()
                imgs = draft["images"]
                self.assertIn("https://example.com/x2.jpg", imgs)
                self.assertIn("https://example.com/x1.jpg", imgs)
                self.assertLess(imgs.index("https://example.com/x2.jpg"),
                                imgs.index("https://example.com/x1.jpg"))
            finally:
                main_mod.APP.store.close()
                gc.collect()  # 释放 TestClient/连接句柄,否则 Windows 删不掉临时库
