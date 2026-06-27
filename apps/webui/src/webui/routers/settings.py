from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.models import SettingsIn

router = APIRouter()


@router.get("/api/state")
def get_state() -> dict:
    return app_instance.APP.state()


@router.post("/api/settings")
def save_settings(payload: SettingsIn) -> dict:
    try:
        return app_instance.APP.save_settings(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/ai/models")
def ai_models(body: dict | None = None) -> dict:
    """查某 AI 槽接口可用模型(下拉用)。body: {kind, base, key}；base/key 留空用已存配置。"""
    try:
        b = body or {}
        return app_instance.APP.list_ai_models(str(b.get("kind") or ""), str(b.get("base") or ""),
                                               str(b.get("key") or ""), str(b.get("platform") or ""))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
