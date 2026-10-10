from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance

router = APIRouter()


@router.post("/api/drafts/{draft_id}/copy-images-to")
def copy_images_to_target(draft_id: int, body: dict) -> dict:
    b = body or {}
    targets = b.get("target_draft_ids")
    if not targets and b.get("target_draft_id"):
        targets = [b["target_draft_id"]]
    try:
        return app_instance.APP.copy_images_to_draft(draft_id, b.get("image_urls") or [], targets or [])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/gallery/add")
def gallery_add(draft_id: int, body: dict) -> dict:
    return app_instance.APP.gallery_add(draft_id, (body or {}).get("image_ids") or [])


@router.post("/api/drafts/{draft_id}/gallery/remove")
def gallery_remove(draft_id: int, body: dict) -> dict:
    return app_instance.APP.gallery_remove(draft_id, (body or {}).get("image_ids") or [])


@router.post("/api/drafts/{draft_id}/gallery/reorder")
def gallery_reorder(draft_id: int, body: dict) -> dict:
    return app_instance.APP.gallery_reorder(draft_id, (body or {}).get("image_ids") or [])


@router.delete("/api/drafts/{draft_id}/images/{image_id}")
def delete_draft_image(draft_id: int, image_id: int) -> dict:
    return app_instance.APP.gallery_delete(draft_id, image_id)
