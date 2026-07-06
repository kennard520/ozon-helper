from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.models import PublishIn

router = APIRouter()


@router.post("/api/drafts/batch-publish")
def batch_publish(body: dict) -> dict:
    ids = body.get("ids") or []
    return app_instance.APP.batch_publish(ids, body.get("store_client_id"))


@router.post("/api/drafts/{draft_id}/copy-to-store")
def copy_draft_to_store(draft_id: int, body: dict) -> dict:
    try:
        return app_instance.APP.copy_draft_to_store(draft_id, body.get("store_client_id"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/drafts/{draft_id}/publish-preview")
def publish_preview(draft_id: int, store_client_id: str | None = None) -> dict:
    try:
        return app_instance.APP.publish_preview(draft_id, store_client_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/drafts/{draft_id}/publish-preflight")
def publish_preflight(draft_id: int) -> dict:
    """发布前核对清单(硬拦/建议/待核对/已就绪)。"""
    try:
        return app_instance.APP.publish_preflight(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/publish")
def publish(draft_id: int, body: PublishIn | None = None) -> dict:
    try:
        scid = body.store_client_id if body else None
        return app_instance.APP.publish(draft_id, scid)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/translate")
def translate_draft(draft_id: int) -> dict:
    try:
        return app_instance.APP.translate_draft(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        tasks = app_instance.APP.store.latest_task_runs_for_draft(draft_id)
        task = next((t for t in tasks if t.get("task_type") == "translate"), None)
        if task:
            app_instance.APP.store.update_task_run(
                task["id"],
                {"status": "failed", "error": str(exc)[:500], "progress_current": 0, "result": {"phase": "failed"}},
            )
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/try-copy")
def try_copy(draft_id: int) -> dict:
    """Ozon 来源草稿试官方复制(import-by-sku)；可复制会在目标店建复制卡。"""
    try:
        return app_instance.APP.try_copy(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
