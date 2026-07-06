from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from webui.drafts import create_draft_from_url


def _valid_draft() -> dict:
    draft = create_draft_from_url("https://detail.1688.com/offer/987654321098.html")
    draft.update({
        "ozon_title": "孝芯胁邪褉 褌械褋褌芯胁褘泄",
        "description": "袨锌懈褋邪薪懈械 褌芯胁邪褉邪",
        "category_id": "17028922",
        "type_id": "94307",
        "price": "799",
        "stock": 1,
        "images": ["https://example.test/a.jpg"],
        "ozon_title": "\u0422\u043e\u0432\u0430\u0440 \u0442\u0435\u0441\u0442\u043e\u0432\u044b\u0439",
        "description": "\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0442\u043e\u0432\u0430\u0440\u0430",
    })
    return draft


class TaskPipelineTest(unittest.TestCase):
    def _app(self, tmp: str):
        import webui.store as store_mod

        store_mod.DEFAULT_DB = Path(tmp) / "pipeline.db"
        import webui.app_service as svc

        importlib.reload(svc)
        return svc.App()

    def test_pipeline_reports_task_progress_and_preflight(self) -> None:
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
                app.store.create_task_run(
                    saved["id"],
                    "ai_text",
                    status="running",
                    progress_current=2,
                    progress_total=4,
                    source="text_jobs",
                    external_id="1",
                )

                body = app.draft_pipeline(saved["id"])
                steps = {s["id"]: s for s in body["steps"]}
                self.assertTrue(body["can_publish"])
                self.assertEqual(steps["ai_text"]["status"], "running")
                self.assertEqual(steps["ai_text"]["progress"], {"current": 2, "total": 4})
                self.assertIn(steps["preflight"]["status"], {"done", "warning"})
            finally:
                app.store.close()

    def test_pipeline_warns_but_allows_publish_for_invalid_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                draft = _valid_draft()
                draft["price"] = ""
                saved = app.store.insert_draft(draft)
                app.store.add_draft_image(
                    saved["id"],
                    "https://example.test/a.jpg",
                    type="main",
                    source="generated",
                )

                body = app.draft_pipeline(saved["id"])
                steps = {s["id"]: s for s in body["steps"]}
                self.assertTrue(body["can_publish"])
                self.assertEqual(steps["preflight"]["status"], "warning")
                self.assertNotEqual(steps["publish"]["status"], "blocked")
                self.assertTrue(steps["preflight"]["errors"])
                self.assertTrue(steps["preflight"]["checks"])
            finally:
                app.store.close()

    def test_pipeline_reports_publish_task_failure(self) -> None:
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
                app.store.create_task_run(
                    saved["id"],
                    "publish",
                    status="failed",
                    progress_current=2,
                    progress_total=3,
                    error="Ozon rejected image",
                    source="ozon_import",
                    external_id="task-1",
                )

                body = app.draft_pipeline(saved["id"])
                steps = {s["id"]: s for s in body["steps"]}
                self.assertEqual(steps["publish"]["status"], "failed")
                self.assertEqual(steps["publish"]["errors"], ["Ozon rejected image"])
                self.assertEqual(steps["publish"]["progress"], {"current": 2, "total": 3})
            finally:
                app.store.close()

    def test_pipeline_reports_sync_workflow_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                saved = app.store.insert_draft(_valid_draft())
                app.store.create_task_run(saved["id"], "rich_content", status="done", progress_current=1, progress_total=1)
                app.store.create_task_run(
                    saved["id"],
                    "attribute_mapping",
                    status="failed",
                    progress_current=0,
                    progress_total=1,
                    error="missing category",
                )

                body = app.draft_pipeline(saved["id"])
                steps = {s["id"]: s for s in body["steps"]}
                self.assertEqual(steps["rich_content"]["status"], "done")
                self.assertEqual(steps["attribute_mapping"]["status"], "failed")
                self.assertEqual(steps["attribute_mapping"]["errors"], ["missing category"])
                self.assertIn("translate", steps)
                self.assertIn("category_recognition", steps)
            finally:
                app.store.close()

    def test_pipeline_next_skip_cancel_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                saved = app.store.insert_draft(_valid_draft())

                nxt = app.pipeline_next(saved["id"])
                self.assertIn(nxt["action"], {"run", "fix"})

                skipped = app.pipeline_skip(saved["id"], "rich_content", "not needed")
                self.assertTrue(skipped["ok"])
                task = next(t for t in app.store.latest_task_runs_for_draft(saved["id"]) if t["task_type"] == "rich_content")
                self.assertEqual(task["status"], "skipped")

                running = app.store.create_task_run(
                    saved["id"],
                    "attribute_mapping",
                    status="running",
                    progress_total=1,
                )
                cancelled = app.pipeline_cancel(saved["id"], "attribute_mapping", "stop")
                self.assertTrue(cancelled["ok"])
                self.assertEqual(app.store.update_task_run(running["id"], {})["status"], "cancel_requested")

                called = {}

                def fake_submit_text_job(did):
                    called["did"] = did
                    return {"job_id": 99, "status": "queued"}

                app.submit_text_job = fake_submit_text_job
                retried = app.pipeline_retry(saved["id"], "ai_text")
                self.assertEqual(called["did"], saved["id"])
                self.assertEqual(retried["job_id"], 99)
            finally:
                app.store.close()

    def test_global_task_and_stale_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                run = app.store.create_task_run(None, "warehouse_sync", status="running")
                recovered = app.store.recover_stale_task_runs(timeout_seconds=-1)
                self.assertGreaterEqual(recovered, 1)
                updated = app.store.update_task_run(run["id"], {})
                self.assertEqual(updated["status"], "failed")
                self.assertIn("timeout", updated["error"])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
