from __future__ import annotations


class TextJobMixin:
    """文本生成 MQ 任务（text_jobs）。"""

    def submit_text_job(self, draft_id: int) -> dict:
        """提交合并文本生成任务(understand→category→copy→attrs)到 MQ。
        同变体串行：已有进行中任务(queued/running)时直接拒绝，防客户重复烧 token。"""
        from ozon_common.dal.repositories.task_run_repo import TaskRunRepo  # noqa: PLC0415
        from ozon_common.dal.repositories.text_job_repo import TextJobRepo  # noqa: PLC0415
        from ozon_common.dal.session import session_scope  # noqa: PLC0415
        from ozon_common.mq import publish_text_job  # noqa: PLC0415

        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")

        with session_scope():
            repo = TextJobRepo()
            if repo.has_active(draft_id):
                raise ValueError("该变体已有进行中的文本生成任务，请等待完成后再重新提交")
            job = repo.create(draft_id)
            run = TaskRunRepo().create(
                draft_id,
                "ai_text",
                status="queued",
                progress_total=4,
                source="text_jobs",
                external_id=job["id"],
            )

        try:
            publish_text_job(job["id"], draft_id)
        except Exception as exc:  # noqa: BLE001
            with session_scope():
                TextJobRepo().update_status(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
                TaskRunRepo().update(run["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")

        return {"job_id": job["id"], "task_run_id": run["id"], "status": job["status"]}

    def get_text_job_status(self, job_id: int) -> dict:
        from ozon_common.dal.repositories.task_run_repo import TaskRunRepo  # noqa: PLC0415
        from ozon_common.dal.repositories.text_job_repo import TextJobRepo  # noqa: PLC0415
        from ozon_common.dal.session import session_scope  # noqa: PLC0415

        with session_scope():
            job = TextJobRepo().get(job_id)
            if job is not None:
                steps_done = [s for s in str(job.get("steps_done") or "").split(",") if s]
                TaskRunRepo().upsert_external(
                    job["draft_id"],
                    "ai_text",
                    "text_jobs",
                    job["id"],
                    job.get("user_id"),
                    status=str(job.get("status") or ""),
                    progress_current=len(steps_done),
                    progress_total=4,
                    error=job.get("error"),
                    result={"current_step": job.get("current_step"), "steps_done": steps_done},
                )
        if job is None:
            raise KeyError(f"text_job {job_id} not found")
        return {
            "job_id": job["id"],
            "status": job["status"],
            "current_step": job.get("current_step"),
            "steps_done": job.get("steps_done"),
            "error": job.get("error"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }

    def get_latest_text_job(self, draft_id: int) -> dict:
        from ozon_common.dal.repositories.text_job_repo import TextJobRepo  # noqa: PLC0415
        from ozon_common.dal.session import session_scope  # noqa: PLC0415

        with session_scope():
            job = TextJobRepo().get_latest(draft_id)
        if job is None:
            raise KeyError(f"draft {draft_id} 没有文本生成任务")
        return self.get_text_job_status(job["id"])
