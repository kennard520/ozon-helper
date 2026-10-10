from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.models import AiVideoIn

router = APIRouter()


@router.post("/api/drafts/{draft_id}/ai-video")
def ai_video_start(draft_id: int, body: AiVideoIn) -> dict:
    try:
        return app_instance.APP.start_ai_video(draft_id, prompt=body.prompt, image_url=body.image_url)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/ai-video/status")
def ai_video_status_route() -> dict:
    return app_instance.APP.ai_video_status()


@router.post("/api/ai-video/stop")
def ai_video_stop_route() -> dict:
    return app_instance.APP.stop_ai_video()
