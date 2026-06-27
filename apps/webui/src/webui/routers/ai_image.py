from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.models import AiImageBatchIn, AiImageIn, ImagePromptsIn

router = APIRouter()


@router.post("/api/drafts/{draft_id}/localize-image")
def localize_image(draft_id: int, body: dict | None = None) -> dict:
    """单张俄化:图上中文→俄语(保图不变),结果进候选区。"""
    try:
        return app_instance.APP.localize_image(draft_id, int((body or {}).get("source_index") or 0))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/regen-image")
def regen_image(draft_id: int, body: dict) -> dict:
    """单张重做:按角色 + 俄语文字 重新生成,结果进候选区。"""
    try:
        b = body or {}
        return app_instance.APP.regen_image(draft_id, int(b.get("source_index") or 0),
                               role=str(b.get("role") or ""), heading=str(b.get("heading") or ""),
                               bullets=b.get("bullets") or [])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/whiten-main")
def whiten_main(draft_id: int, body: dict | None = None) -> dict:
    """选一张图做白底电商主图，结果进候选区。"""
    try:
        return app_instance.APP.whiten_main(draft_id, int((body or {}).get("source_index") or 0))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/scene-image")
def scene_image(draft_id: int, body: dict | None = None) -> dict:
    """选一张图做场景/氛围图(保产品一致)，结果进候选区。"""
    try:
        b = body or {}
        return app_instance.APP.scene_image(draft_id, int(b.get("source_index") or 0), hint=str(b.get("hint") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/drafts/{draft_id}/image-plan")
def image_plan(draft_id: int, force: bool = False) -> dict:
    """图集计划 + 每槽状态(待做/候选中/已应用)。force=true 据当前理解/图重建。"""
    try:
        return app_instance.APP.image_plan(draft_id, force=bool(force))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/design-image-plan")
def design_image_plan(draft_id: int, body: dict | None = None) -> dict:
    """AI 设计图集：据看图理解+源图设计 ~target 张 Ozon 商品图方案，写入 image_plan。"""
    try:
        target = int((body or {}).get("target") or 10)
        return app_instance.APP.design_image_plan(draft_id, target=target)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/generate-plan-slot")
def generate_plan_slot(draft_id: int, body: dict) -> dict:
    """生成图集计划某槽位的图，结果进候选区。"""
    try:
        return app_instance.APP.generate_plan_slot(draft_id, str((body or {}).get("slot_id") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/apply-candidates")
def apply_candidates(draft_id: int, body: dict | None = None) -> dict:
    """把候选区的图加入正式图集 draft.images。不传 indices = 应用全部。"""
    try:
        return app_instance.APP.apply_image_candidates(draft_id, (body or {}).get("indices") or None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/discard-candidates")
def discard_candidates(draft_id: int) -> dict:
    """清空候选区(全部丢弃)。"""
    try:
        return app_instance.APP.discard_image_candidates(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/ai-image-prompts")
def ai_image_prompts(draft_id: int, body: ImagePromptsIn) -> dict:
    try:
        return app_instance.APP.ai_image_prompts(draft_id, body.n_points)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/ai-image")
def ai_image(draft_id: int, body: AiImageIn) -> dict:
    try:
        return app_instance.APP.ai_generate_image(draft_id, mode=body.mode, prompt=body.prompt,
                                     source_url=body.source_url, size=body.size,
                                     as_main=bool(body.as_main))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/gen-images-batch")
def submit_gen_images_batch(draft_id: int, body: dict) -> dict:
    try:
        return app_instance.APP.submit_batch_gen_job(
            draft_id, (body or {}).get("source_indices") or [],
            str((body or {}).get("action") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/api/drafts/{draft_id}/gen-images-custom")
def submit_gen_images_custom(draft_id: int, body: dict) -> dict:
    try:
        return app_instance.APP.submit_gen_images_custom(draft_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/api/drafts/{draft_id}/gen-images")
def submit_gen_images(draft_id: int, body: dict) -> dict:
    try:
        return app_instance.APP.submit_gen_job(draft_id, int((body or {}).get("target") or 10))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/api/gen-jobs/{job_id}")
def gen_job_status(job_id: int) -> dict:
    try:
        return app_instance.APP.get_gen_job_status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/drafts/{draft_id}/gen-job/latest")
def latest_gen_job(draft_id: int) -> dict:
    try:
        return app_instance.APP.get_latest_gen_job(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/gen-jobs/batch-latest")
def batch_latest_gen_jobs(body: dict) -> dict:
    return app_instance.APP.batch_latest_gen_jobs((body or {}).get("draft_ids") or [])
