from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.models import AiProposalPatchIn

router = APIRouter()


@router.post("/api/drafts/{draft_id}/recognize-category")
def recognize_category(draft_id: int) -> dict:
    """AI 识别类别(类别识别)，写入草稿。特征值识别(auto-map)的前置。"""
    try:
        return app_instance.APP.recognize_category(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/auto-map")
def auto_map(draft_id: int) -> dict:
    try:
        return app_instance.APP.auto_map_attributes(draft_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/ai-fill-attributes")
def ai_fill_attributes(draft_id: int) -> dict:
    """AI 按草稿当前类目填属性(比 auto_map 按名硬对强，适合 1688 中文参数)。"""
    try:
        return app_instance.APP.ai_fill_attributes(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/ai-generate")
def ai_generate(draft_id: int) -> dict:
    try:
        return app_instance.APP.ai_generate(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/ai-copy")
def ai_copy(draft_id: int) -> dict:
    """只生成文案(标题/简介/标签)，1 次 LLM 调用，快。结果进 ai_proposal 预览。"""
    try:
        return app_instance.APP.ai_copy(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/make-infographic")
def make_infographic(draft_id: int, body: dict) -> dict:
    """把草稿某张图做成俄语信息图(+可选店铺水印)，挂回 draft.images。"""
    try:
        return app_instance.APP.make_infographic(
            draft_id,
            source_index=int(body.get("source_index") or 0),
            heading=str(body.get("heading") or ""),
            bullets=body.get("bullets") or [],
            watermark=str(body.get("watermark") or ""))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/make-rich-content")
def make_rich_content(draft_id: int, body: dict | None = None) -> dict:
    """把草稿图拼成 Ozon 富文本(billboard 大图序列)，存草稿（发布时随属性 11254 上架）。"""
    try:
        return app_instance.APP.make_rich_content(draft_id, image_indexes=(body or {}).get("image_indexes"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/understand")
def understand_draft(draft_id: int, body: dict | None = None) -> dict:
    """理解层:多模态看图理解 → 结构化 understanding,缓存进草稿(供文案/图片复用)。"""
    try:
        return app_instance.APP.understand_draft(draft_id, force=bool((body or {}).get("force")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/drafts/{draft_id}/recommend")
def recommend(draft_id: int) -> dict:
    """智能推荐:据来源 + understanding → 推荐路径(复制/俄化/重做)+ 逐图默认处理。"""
    try:
        return app_instance.APP.recommend(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/api/drafts/{draft_id}/ai-proposal")
def patch_ai_proposal(draft_id: int, body: AiProposalPatchIn) -> dict:
    try:
        return app_instance.APP.patch_ai_proposal(draft_id, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/ai-proposal/apply")
def apply_ai_proposal(draft_id: int) -> dict:
    try:
        return app_instance.APP.apply_ai_proposal(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/drafts/{draft_id}/generate-all")
def generate_all(draft_id: int) -> dict:
    """提交合并文本生成任务(understand→category→copy→attrs)到 MQ，立即返回 job_id。"""
    try:
        return app_instance.APP.submit_text_job(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/text-jobs/{job_id}")
def get_text_job(job_id: int) -> dict:
    try:
        return app_instance.APP.get_text_job_status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/drafts/{draft_id}/text-job/latest")
def get_latest_text_job(draft_id: int) -> dict:
    try:
        return app_instance.APP.get_latest_text_job(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
