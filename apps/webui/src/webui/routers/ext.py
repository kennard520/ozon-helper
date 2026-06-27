from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from webui import app_instance
from webui.models import ExtCollectParsedIn, ExtSnapshotIn, PublishGroupIn

router = APIRouter()


@router.get("/api/ext/ping")
def ext_ping() -> dict:
    return app_instance.APP.ext_ping()


@router.post("/api/ext/snapshot")
def ext_snapshot(body: ExtSnapshotIn) -> dict:
    try:
        return app_instance.APP.ext_add_snapshot(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/ext/snapshots")
def ext_snapshots(product_id: str) -> dict:
    return app_instance.APP.ext_snapshots(product_id)


@router.post("/api/ext/collect-parsed")
def ext_collect_parsed(body: ExtCollectParsedIn) -> dict:
    try:
        return app_instance.APP.ext_collect_parsed(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/ext/publish-group")
def ext_publish_group(body: PublishGroupIn) -> dict:
    try:
        return app_instance.APP.publish_variant_group(body.variant_group, body.store_client_id, body.model_name)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/ext/update-draft-media")
def ext_update_draft_media(body: dict) -> dict:
    try:
        return app_instance.APP.update_draft_media(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/ext/pending-media-drafts")
def ext_pending_media_drafts() -> dict:
    return app_instance.APP.pending_media_drafts()


@router.post("/api/drafts/{draft_id}/media")
async def upload_media(draft_id: int, file: UploadFile = File(...), kind: str = Form("image")) -> dict:
    from webui.media import save_upload  # noqa: PLC0415
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大(>20MB)")
    url = save_upload(f"draft-{draft_id}", file.filename or "upload", data)
    return {"url": url, "kind": kind}
