"""Task 1 TDD: draft_images.local_url 列 ——采集素材随行存本地代理(防盗链显示)

采集落库时 images[i] ↔ local_images[i] 平行,local_url 随行入库;
getDraft 的 materials 应返回 local_url。
"""
import gc
import importlib
import tempfile
import unittest
from pathlib import Path


class MaterialLocalUrlTest(unittest.TestCase):
    def _app(self, tmp):
        import webui.store as store_mod  # noqa: PLC0415

        store_mod.DEFAULT_DB = Path(tmp) / "mat_local.db"
        import webui.app_service as svc  # noqa: PLC0415

        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415

        importlib.reload(main_mod)
        return main_mod.APP

    def test_collected_material_carries_local_url(self):
        from webui.drafts import create_draft_from_url  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = create_draft_from_url("https://detail.1688.com/offer/LU1.html")
                d["images"] = ["http://raw/a.jpg", "http://raw/b.jpg"]
                d["local_images"] = ["/media/a.jpg", "/media/b.jpg"]
                row = app.store.insert_draft(d)
                got = app.store.get_draft(row["id"])
                mats = {m["url"]: m for m in got["materials"]}
                self.assertEqual(mats["http://raw/a.jpg"]["local_url"], "/media/a.jpg")
                self.assertEqual(mats["http://raw/b.jpg"]["local_url"], "/media/b.jpg")
            finally:
                app.store.close()
                gc.collect()
