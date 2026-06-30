"""文本任务提交 service + HTTP 端点测试。

覆盖：
1. submit_text_job 正常：mock MQ publish 成功，返回 job_id + status=queued
2. submit_text_job 拒重复：已有 active job 时返回 409
3. submit_text_job draft 不存在：返回 404
4. get_text_job_status 正常
5. get_latest_text_job 无任务：返回 404
"""
from __future__ import annotations

import gc
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _make_app(tmp: str):
    """建独立临时 DB + 重新加载 app_service，返回 (svc_module, app_instance)。"""
    import webui.store as store_mod  # noqa: PLC0415

    store_mod.DEFAULT_DB = Path(tmp) / "textjob.db"
    import webui.app_service as svc  # noqa: PLC0415

    importlib.reload(svc)
    app = svc.App()
    return svc, app


def _make_client(tmp: str):
    """建 FastAPI TestClient（完全隔离的临时 DB）。"""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    import webui.store as store_mod  # noqa: PLC0415

    store_mod.DEFAULT_DB = Path(tmp) / "textjob_http.db"
    import webui.app_service as svc  # noqa: PLC0415

    importlib.reload(svc)
    import webui.main as main_mod  # noqa: PLC0415

    importlib.reload(main_mod)
    return TestClient(main_mod.app), main_mod


def _insert_draft(app) -> int:
    from webui.drafts import create_draft_from_url  # noqa: PLC0415

    d = app.store.insert_draft(
        create_draft_from_url("https://detail.1688.com/offer/999000111.html")
    )
    return d["id"]


# ---------------------------------------------------------------------------
# Service 层测试（直接调 App 方法，mock publish_text_job）
# ---------------------------------------------------------------------------

class SubmitTextJobTest(unittest.TestCase):
    def test_submit_ok_returns_job_id_and_queued(self):
        """正常提交：MQ publish mock，返回 job_id + status=queued。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                did = _insert_draft(app)
                with patch("ozon_common.mq.publish_text_job") as mock_pub:
                    mock_pub.return_value = None
                    result = app.submit_text_job(did)
                self.assertIn("job_id", result)
                self.assertEqual(result["status"], "queued")
                self.assertIsInstance(result["job_id"], int)
                mock_pub.assert_called_once()
                args = mock_pub.call_args[0]
                self.assertEqual(args[0], result["job_id"])
                self.assertEqual(args[1], did)
            finally:
                app.store.close()

    def test_submit_duplicate_raises_value_error(self):
        """已有 active job → 拒绝，抛 ValueError。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                did = _insert_draft(app)
                with patch("ozon_common.mq.publish_text_job"):
                    app.submit_text_job(did)  # 第一次：queued
                with self.assertRaises(ValueError) as ctx:
                    with patch("ozon_common.mq.publish_text_job"):
                        app.submit_text_job(did)  # 第二次：拒绝
                self.assertIn("已有进行中", str(ctx.exception))
            finally:
                app.store.close()

    def test_submit_draft_not_found_raises_key_error(self):
        """draft 不存在 → 抛 KeyError。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                with self.assertRaises(KeyError):
                    app.submit_text_job(99999)
            finally:
                app.store.close()

    def test_mq_failure_marks_job_failed_and_raises_runtime_error(self):
        """MQ publish 抛异常 → job.status 被置 failed，对外抛 RuntimeError。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                did = _insert_draft(app)
                with patch("ozon_common.mq.publish_text_job", side_effect=ConnectionError("rabbitmq down")):
                    with self.assertRaises(RuntimeError) as ctx:
                        app.submit_text_job(did)
                self.assertIn("消息队列不可用", str(ctx.exception))
                # 验证 job 状态已被置 failed
                status = app.get_latest_text_job(did)
                self.assertEqual(status["status"], "failed")
            finally:
                app.store.close()


class GetTextJobStatusTest(unittest.TestCase):
    def test_get_status_ok(self):
        """submit 后，get_text_job_status 能取到正确字段。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                did = _insert_draft(app)
                with patch("ozon_common.mq.publish_text_job"):
                    res = app.submit_text_job(did)
                job_id = res["job_id"]
                status = app.get_text_job_status(job_id)
                self.assertEqual(status["job_id"], job_id)
                self.assertEqual(status["status"], "queued")
                self.assertIn("created_at", status)
                self.assertIn("updated_at", status)
            finally:
                app.store.close()

    def test_get_status_not_found_raises_key_error(self):
        """不存在的 job_id → 抛 KeyError。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                with self.assertRaises(KeyError):
                    app.get_text_job_status(88888)
            finally:
                app.store.close()


class GetLatestTextJobTest(unittest.TestCase):
    def test_no_job_raises_key_error(self):
        """没有任务的 draft → get_latest_text_job 抛 KeyError。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                did = _insert_draft(app)
                with self.assertRaises(KeyError):
                    app.get_latest_text_job(did)
            finally:
                app.store.close()

    def test_returns_latest_job(self):
        """有任务时返回最新一条。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, app = _make_app(tmp)
            try:
                did = _insert_draft(app)
                with patch("ozon_common.mq.publish_text_job"):
                    submitted = app.submit_text_job(did)
                latest = app.get_latest_text_job(did)
                self.assertEqual(latest["job_id"], submitted["job_id"])
                self.assertEqual(latest["status"], "queued")
            finally:
                app.store.close()


# ---------------------------------------------------------------------------
# HTTP 端点测试（FastAPI TestClient，通过真实路由验证状态码）
# ---------------------------------------------------------------------------

class GenerateAllEndpointTest(unittest.TestCase):
    def test_post_generate_all_returns_202_like_job(self):
        """POST /api/drafts/{id}/generate-all → 200 + job_id。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                did = _insert_draft(main_mod.APP)
                with patch("ozon_common.mq.publish_text_job"):
                    resp = client.post(f"/api/drafts/{did}/generate-all")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertIn("job_id", body)
                self.assertEqual(body["status"], "queued")
            finally:
                main_mod.APP.store.close()
                gc.collect()

    def test_post_generate_all_draft_not_found_404(self):
        """draft 不存在 → 404。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                with patch("ozon_common.mq.publish_text_job"):
                    resp = client.post("/api/drafts/99999/generate-all")
                self.assertEqual(resp.status_code, 404)
            finally:
                main_mod.APP.store.close()
                gc.collect()

    def test_post_generate_all_duplicate_409(self):
        """已有 active job → 409。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                did = _insert_draft(main_mod.APP)
                with patch("ozon_common.mq.publish_text_job"):
                    client.post(f"/api/drafts/{did}/generate-all")  # 第一次
                with patch("ozon_common.mq.publish_text_job"):
                    resp = client.post(f"/api/drafts/{did}/generate-all")  # 第二次
                self.assertEqual(resp.status_code, 409)
            finally:
                main_mod.APP.store.close()
                gc.collect()


class TextJobStatusEndpointTest(unittest.TestCase):
    def test_get_text_job_ok(self):
        """GET /api/text-jobs/{job_id} → 200 + 正确字段。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                did = _insert_draft(main_mod.APP)
                with patch("ozon_common.mq.publish_text_job"):
                    sub = client.post(f"/api/drafts/{did}/generate-all").json()
                resp = client.get(f"/api/text-jobs/{sub['job_id']}")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["status"], "queued")
            finally:
                main_mod.APP.store.close()
                gc.collect()

    def test_get_text_job_not_found_404(self):
        """不存在的 job_id → 404。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                resp = client.get("/api/text-jobs/77777")
                self.assertEqual(resp.status_code, 404)
            finally:
                main_mod.APP.store.close()
                gc.collect()


class LatestTextJobEndpointTest(unittest.TestCase):
    def test_get_latest_no_job_404(self):
        """没有任务的 draft → GET latest → 404。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                did = _insert_draft(main_mod.APP)
                resp = client.get(f"/api/drafts/{did}/text-job/latest")
                self.assertEqual(resp.status_code, 404)
            finally:
                main_mod.APP.store.close()
                gc.collect()

    def test_get_latest_returns_latest(self):
        """提交后 GET latest 返回 job_id + queued。"""
        with tempfile.TemporaryDirectory() as tmp:
            client, main_mod = _make_client(tmp)
            try:
                did = _insert_draft(main_mod.APP)
                with patch("ozon_common.mq.publish_text_job"):
                    sub = client.post(f"/api/drafts/{did}/generate-all").json()
                resp = client.get(f"/api/drafts/{did}/text-job/latest")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json()["job_id"], sub["job_id"])
            finally:
                main_mod.APP.store.close()
                gc.collect()


if __name__ == "__main__":
    unittest.main()
