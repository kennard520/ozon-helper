from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from webui.draft_state import derive_draft_status
from webui.drafts import create_draft_from_url


def _valid_draft() -> dict:
    draft = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
    draft.update({
        "ozon_title": "Товар тестовый",
        "description": "Описание товара",
        "category_id": "17028922",
        "type_id": "94307",
        "price": "799",
        "stock": 1,
        "images": ["https://example.test/a.jpg"],
        "ozon_title": "\u0422\u043e\u0432\u0430\u0440 \u0442\u0435\u0441\u0442\u043e\u0432\u044b\u0439",
        "description": "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0442\u043e\u0432\u0430\u0440\u0430",
    })
    return draft


class DraftStateTest(unittest.TestCase):
    def test_ready_without_errors(self) -> None:
        self.assertEqual(derive_draft_status(_valid_draft(), []), "ready")

    def test_invalid_with_errors(self) -> None:
        self.assertEqual(derive_draft_status(_valid_draft(), ["missing"]), "invalid")

    def test_media_pending_wins_over_ready(self) -> None:
        draft = {**_valid_draft(), "media_status": "pending"}
        self.assertEqual(derive_draft_status(draft, []), "media_pending")

    def test_explicit_status_wins(self) -> None:
        self.assertEqual(
            derive_draft_status(_valid_draft(), [], requested_status="published"),
            "published",
        )


class StoreDraftStateTest(unittest.TestCase):
    def _app(self, tmp: str):
        import webui.store as store_mod

        store_mod.DEFAULT_DB = Path(tmp) / "state.db"
        import webui.app_service as svc

        importlib.reload(svc)
        return svc.App()

    def test_media_status_updates_draft_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                saved = app.store.insert_draft(_valid_draft())
                app.store.add_draft_image(
                    saved["id"],
                    "https://example.test/a.jpg",
                    type="main",
                    source="generated",
                )

                app.store.set_media_status(saved["id"], "pending")
                pending = app.store.get_draft(saved["id"])
                self.assertEqual(pending["media_status"], "pending")
                self.assertEqual(pending["status"], "media_pending")
                tasks = app.store.latest_task_runs_for_draft(saved["id"])
                media_task = next(t for t in tasks if t["task_type"] == "media_rehost")
                self.assertEqual(media_task["status"], "running")

                app.store.apply_media_oss(saved["id"], {})
                done = app.store.get_draft(saved["id"])
                self.assertEqual(done["media_status"], "done")
                self.assertEqual(done["status"], "ready")
                tasks = app.store.latest_task_runs_for_draft(saved["id"])
                media_task = next(t for t in tasks if t["task_type"] == "media_rehost")
                self.assertEqual(media_task["status"], "done")
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
