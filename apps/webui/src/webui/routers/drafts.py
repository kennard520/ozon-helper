from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from webui import app_instance
from webui.models import BatchUpdateDraftsIn

router = APIRouter()


@router.get("/api/drafts")
def get_drafts(status: str = "all", page: int = 1, page_size: int = 20,
               store_client_id: str | None = None) -> dict:
    # 草稿绑定店：前端传当前店 → 只列该店草稿；不传(None)=不按店过滤（兼容）
    return app_instance.APP.list_drafts(status=status, page=page, page_size=page_size, store_client_id=store_client_id)


@router.get("/api/drafts/{draft_id}")
def get_draft(draft_id: int) -> dict:
    """单草稿明细（点变体组里不在当前页的兄弟变体时按 id 拉取）。段数与 /drafts/{id}/... 子路由不同，不冲突。"""
    try:
        return app_instance.APP.get_draft(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/api/drafts/{draft_id}")
async def update_draft(draft_id: int, request: Request) -> dict:
    body = await request.json()
    try:
        return app_instance.APP.update_draft(draft_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/api/drafts/{draft_id}")
def delete_draft(draft_id: int) -> dict:
    try:
        return app_instance.APP.delete(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/regen-offer-id")
def regen_offer_id(draft_id: int) -> dict:
    """按 {平台}-{变体维度} 重新生成货号。"""
    try:
        return app_instance.APP.regenerate_offer_id(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/drafts/{draft_id}/variant-group")
def variant_group_siblings(draft_id: int) -> dict:
    """该草稿所属变体组的兄弟变体清单(轻量)，供编辑器展示。"""
    try:
        return app_instance.APP.variant_group_siblings(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/batch-update")
def batch_update_drafts(body: BatchUpdateDraftsIn) -> dict:
    patch = body.model_dump(exclude_none=True)
    ids = patch.pop("ids", [])
    try:
        return app_instance.APP.batch_update_drafts(ids, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/drafts/{draft_id}/required-check")
def required_check(draft_id: int, language: str = "ZH_HANS") -> dict:
    try:
        return app_instance.APP.required_check(draft_id, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
