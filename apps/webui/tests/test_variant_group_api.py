from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from webui.drafts import create_draft_from_url


class VariantGroupApiTest(unittest.TestCase):
    def _app(self, tmp: str):
        import webui.store as store_mod  # noqa: PLC0415

        store_mod.DEFAULT_DB = Path(tmp) / "variant-group.db"
        import webui.app_service as svc  # noqa: PLC0415

        importlib.reload(svc)
        return svc.App()

    def test_variant_group_includes_source_platform_for_wb_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                draft = create_draft_from_url(
                    "https://www.wildberries.ru/catalog/291085835/detail.aspx",
                    source_platform="wb",
                    scraped={"title": "Автосканер"},
                )
                saved = app.store.insert_draft(draft)
                app.store.update_draft(saved["id"], {"source_raw": {"variant_group": "wb-271556434"}})

                body = app.variant_group_siblings(saved["id"])

                self.assertEqual(body["count"], 1)
                self.assertEqual(body["variants"][0]["source_platform"], "wb")
            finally:
                app.store.close()

    def test_variant_group_siblings_are_store_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                ryd = create_draft_from_url(
                    "https://www.wildberries.ru/catalog/291085835/detail.aspx",
                    source_platform="wb",
                    scraped={"title": "old store"},
                )
                ryd["store_client_id"] = "5020196"
                a = app.store.insert_draft(ryd)
                app.store.update_draft(a["id"], {"source_raw": {"variant_group": "wb-271556434"}})

                rongyida = create_draft_from_url(
                    "https://www.wildberries.ru/catalog/291085835/detail.aspx",
                    source_platform="wb",
                    scraped={"title": "current store"},
                )
                rongyida["store_client_id"] = "4891171"
                b = app.store.insert_draft(rongyida)
                app.store.update_draft(b["id"], {"source_raw": {"variant_group": "wb-271556434"}})

                body = app.variant_group_siblings(b["id"])

                self.assertEqual(body["count"], 1)
                self.assertEqual([v["id"] for v in body["variants"]], [b["id"]])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
