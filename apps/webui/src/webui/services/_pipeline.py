from __future__ import annotations

from webui.draft_state import blocking_errors, build_draft_checks, warning_messages
from webui.services._helpers import step_flags

_RUNNING = {"queued", "running", "designing", "submitted", "cancel_requested"}
_DONE = {"done", "published"}
_FAILED = {"failed"}
_CANCELLED = {"cancelled"}
_STEP_TASK_TYPES = {
    "ai_text": "ai_text",
    "ai_image": "ai_image",
    "category_recognition": "category_recognition",
    "attribute_mapping": "attribute_mapping",
    "attribute_ai_fill": "attribute_ai_fill",
    "translate": "translate",
    "rich_content": "rich_content",
    "publish": "publish",
    "media": "media_rehost",
}


def _task_by_type(tasks: list[dict]) -> dict[str, dict]:
    return {str(t.get("task_type") or ""): t for t in tasks}


def _run_status(run: dict | None, fallback_done: bool = False) -> str:
    if not run:
        return "done" if fallback_done else "pending"
    status = str(run.get("status") or "").lower()
    if status in _FAILED:
        return "failed"
    if status in _DONE:
        return "done"
    if status in _RUNNING:
        return "running"
    if status == "skipped":
        return "skipped"
    if status in _CANCELLED:
        return "cancelled"
    return "pending"


def _progress(run: dict | None) -> dict:
    if not run:
        return {"current": 0, "total": 0}
    return {
        "current": int(run.get("progress_current") or 0),
        "total": int(run.get("progress_total") or 0),
    }


class PipelineMixin:
    def _latest_pipeline_task(self, draft_id: int, step_id: str) -> dict | None:
        task_type = _STEP_TASK_TYPES.get(step_id, step_id)
        for task in self.store.latest_task_runs_for_draft(draft_id):
            if str(task.get("task_type") or "") == task_type:
                return task
        return None

    def _track_sync_pipeline_action(self, draft_id: int, task_type: str, fn):
        run = self.store.create_task_run(
            draft_id,
            task_type,
            status="running",
            progress_total=1,
            source="pipeline",
            result={"phase": "start"},
        )
        try:
            result = fn()
        except Exception as exc:
            self.store.update_task_run(
                run["id"],
                {"status": "failed", "error": str(exc)[:500], "progress_current": 0, "result": {"phase": "failed"}},
            )
            raise
        self.store.update_task_run(
            run["id"],
            {"status": "done", "progress_current": 1, "result": {"phase": "done"}},
        )
        if isinstance(result, dict):
            result.setdefault("task_run_id", run["id"])
        return result

    def draft_pipeline(self, draft_id: int) -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        self.store.recover_stale_task_runs()

        tasks = self.store.latest_task_runs_for_draft(draft_id)
        by_type = _task_by_type(tasks)
        flags = step_flags(draft)
        checks = build_draft_checks(draft)
        check_items = [c.as_dict() for c in checks]
        errors = blocking_errors(checks)
        warnings = warning_messages(checks)
        draft_status = str(draft.get("status") or "draft")
        media_status = str(draft.get("media_status") or "done")
        has_preflight_risks = bool(errors or warnings)
        can_publish = media_status != "pending"

        media_run = by_type.get("media_rehost")
        media_step_status = _run_status(media_run, fallback_done=media_status != "pending")
        if media_status == "pending" and media_step_status == "pending":
            media_step_status = "running"

        publish_run = by_type.get("publish")
        publish_status = _run_status(publish_run)
        publish_message = "等待发布"
        publish_errors: list[str] = [publish_run.get("error")] if publish_run and publish_run.get("error") else []
        if draft_status == "published":
            publish_status = "done"
            publish_message = "已发布"
        elif draft_status == "publishing":
            publish_status = "running"
            publish_message = "发布中"
        elif draft_status in {"failed", "skipped"}:
            publish_status = draft_status
            publish_message = "发布失败" if draft_status == "failed" else "Ozon 跳过更新"
            publish_errors = publish_errors or list(draft.get("validation_errors") or [])
        elif publish_status == "running":
            publish_message = "发布中"
        elif publish_status == "failed":
            publish_message = "发布失败"
        elif media_status == "pending":
            publish_status = "blocked"
            publish_message = "媒体还在上传"

        steps = [
            {
                "id": "collect",
                "label": "采集草稿",
                "status": "done",
                "message": "已创建草稿",
                "errors": [],
                "progress": {"current": 1, "total": 1},
            },
            {
                "id": "media",
                "label": "媒体补传",
                "status": media_step_status,
                "message": "等待插件补传" if media_status == "pending" else "媒体已就绪",
                "errors": [media_run.get("error")] if media_run and media_run.get("error") else [],
                "progress": _progress(media_run) if media_run else {"current": 1, "total": 1},
            },
            {
                "id": "ai_text",
                "label": "AI 文案",
                "status": _run_status(by_type.get("ai_text"), fallback_done=bool(flags.get("content"))),
                "message": "标题、描述、类目与属性",
                "errors": [by_type["ai_text"].get("error")] if by_type.get("ai_text") and by_type["ai_text"].get("error") else [],
                "progress": _progress(by_type.get("ai_text")),
            },
            {
                "id": "ai_image",
                "label": "AI 图片",
                "status": _run_status(by_type.get("ai_image"), fallback_done=bool(flags.get("images"))),
                "message": "图集规划与生成",
                "errors": [by_type["ai_image"].get("error")] if by_type.get("ai_image") and by_type["ai_image"].get("error") else [],
                "progress": _progress(by_type.get("ai_image")),
            },
            {
                "id": "category_recognition",
                "label": "类目识别",
                "status": _run_status(by_type.get("category_recognition"), fallback_done=bool(draft.get("category_id") and draft.get("type_id"))),
                "message": "识别 Ozon 类目和类型",
                "errors": [by_type["category_recognition"].get("error")] if by_type.get("category_recognition") and by_type["category_recognition"].get("error") else [],
                "progress": _progress(by_type.get("category_recognition")),
            },
            {
                "id": "attribute_mapping",
                "label": "属性映射",
                "status": _run_status(by_type.get("attribute_mapping"), fallback_done=bool(flags.get("attrs"))),
                "message": "采集特征映射到 Ozon 属性",
                "errors": [by_type["attribute_mapping"].get("error")] if by_type.get("attribute_mapping") and by_type["attribute_mapping"].get("error") else [],
                "progress": _progress(by_type.get("attribute_mapping")),
            },
            {
                "id": "attribute_ai_fill",
                "label": "AI 填属性",
                "status": _run_status(by_type.get("attribute_ai_fill")),
                "message": "按当前类目补全属性",
                "errors": [by_type["attribute_ai_fill"].get("error")] if by_type.get("attribute_ai_fill") and by_type["attribute_ai_fill"].get("error") else [],
                "progress": _progress(by_type.get("attribute_ai_fill")),
            },
            {
                "id": "translate",
                "label": "翻译本地化",
                "status": _run_status(by_type.get("translate"), fallback_done=bool(flags.get("content"))),
                "message": "标题和描述翻译",
                "errors": [by_type["translate"].get("error")] if by_type.get("translate") and by_type["translate"].get("error") else [],
                "progress": _progress(by_type.get("translate")),
            },
            {
                "id": "rich_content",
                "label": "富文本",
                "status": _run_status(by_type.get("rich_content"), fallback_done=bool(flags.get("rich"))),
                "message": "生成 Ozon 富文本结构",
                "errors": [by_type["rich_content"].get("error")] if by_type.get("rich_content") and by_type["rich_content"].get("error") else [],
                "progress": _progress(by_type.get("rich_content")),
            },
            {
                "id": "preflight",
                "label": "发布前校验",
                "status": "warning" if has_preflight_risks else "done",
                "message": "可继续发布，有风险提示" if has_preflight_risks else "可发布",
                "errors": errors,
                "warnings": warnings,
                "checks": check_items,
                "progress": {"current": 1, "total": 1},
            },
            {
                "id": "publish",
                "label": "发布到 Ozon",
                "status": publish_status,
                "message": publish_message,
                "errors": publish_errors,
                "progress": _progress(publish_run) if publish_run else {"current": 1 if publish_status == "done" else 0, "total": 1},
            },
        ]
        return {
            "draft_id": draft_id,
            "draft_status": draft_status,
            "media_status": media_status,
            "can_publish": can_publish,
            "next": self.pipeline_next(draft_id, pipeline_steps=steps),
            "errors": errors,
            "warnings": warnings,
            "checks": check_items,
            "tasks": tasks,
            "steps": steps,
        }

    def pipeline_next(self, draft_id: int, pipeline_steps: list[dict] | None = None) -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        steps = pipeline_steps if pipeline_steps is not None else self.draft_pipeline(draft_id)["steps"]
        for step in steps:
            status = str(step.get("status") or "")
            step_id = str(step.get("id") or "")
            if status == "running":
                return {"action": "wait", "step_id": step_id, "reason": step.get("message") or ""}
            if status == "failed":
                return {"action": "retry", "step_id": step_id, "reason": (step.get("errors") or [""])[0]}
            if status == "blocked":
                return {"action": "fix", "step_id": step_id, "reason": (step.get("errors") or [step.get("message") or ""])[0]}
            if status == "pending" and step_id in _STEP_TASK_TYPES:
                return {"action": "run", "step_id": step_id, "reason": step.get("message") or ""}
        return {"action": "done", "step_id": "", "reason": "pipeline complete"}

    def pipeline_retry(self, draft_id: int, step_id: str) -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        step_id = str(step_id or "").strip()
        active = self._latest_pipeline_task(draft_id, step_id)
        if active and str(active.get("status") or "") in _RUNNING:
            return {"ok": True, "task": active, "already_running": True}
        if step_id == "ai_text":
            return self.submit_text_job(draft_id)
        if step_id == "ai_image":
            return self.submit_gen_job(draft_id, 10)
        if step_id == "category_recognition":
            return self._track_sync_pipeline_action(draft_id, "category_recognition", lambda: self.recognize_category(draft_id))
        if step_id == "attribute_mapping":
            return self._track_sync_pipeline_action(draft_id, "attribute_mapping", lambda: self.map_attributes(draft_id))
        if step_id == "attribute_ai_fill":
            return self._track_sync_pipeline_action(draft_id, "attribute_ai_fill", lambda: self.ai_fill_attributes(draft_id))
        if step_id == "translate":
            return self.translate_draft(draft_id)
        if step_id == "rich_content":
            return self._track_sync_pipeline_action(draft_id, "rich_content", lambda: self.make_rich_content(draft_id))
        if step_id == "publish":
            return self.publish(draft_id)
        raise ValueError(f"unsupported pipeline step: {step_id}")

    def pipeline_skip(self, draft_id: int, step_id: str, reason: str = "") -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        step_id = str(step_id or "").strip()
        task_type = _STEP_TASK_TYPES.get(step_id)
        if not task_type or step_id in {"publish", "media"}:
            raise ValueError(f"step cannot be skipped: {step_id}")
        task = self._latest_pipeline_task(draft_id, step_id)
        patch = {
            "status": "skipped",
            "progress_current": 1,
            "progress_total": 1,
            "error": None,
            "result": {"phase": "skipped", "reason": str(reason or "")},
        }
        if task:
            updated = self.store.update_task_run(task["id"], patch)
        else:
            updated = self.store.create_task_run(
                draft_id,
                task_type,
                status="skipped",
                progress_current=1,
                progress_total=1,
                source="pipeline",
                result=patch["result"],
            )
        return {"ok": True, "task": updated, "pipeline": self.draft_pipeline(draft_id)}

    def pipeline_cancel(self, draft_id: int, step_id: str, reason: str = "") -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        task = self._latest_pipeline_task(draft_id, step_id)
        if not task:
            raise ValueError(f"step has no task to cancel: {step_id}")
        status = str(task.get("status") or "")
        patch_status = "cancel_requested" if status in _RUNNING else "cancelled"
        updated = self.store.update_task_run(
            task["id"],
            {
                "status": patch_status,
                "error": str(reason or ""),
                "result": {"phase": patch_status, "reason": str(reason or "")},
            },
        )
        return {"ok": True, "task": updated, "pipeline": self.draft_pipeline(draft_id)}
