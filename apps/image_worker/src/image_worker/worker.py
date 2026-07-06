"""AI 出图 Worker：消费 RabbitMQ → 设计图集计划 → 并发生成各槽 → OSS → draft_images 表。
入口：python worker.py"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
import traceback
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from ozon_common.dal.engine import engine_for
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo
from ozon_common.dal.repositories.gen_job_repo import GenJobRepo
from ozon_common.dal.repositories.settings_repo import SettingsRepo
from ozon_common.dal.repositories.task_run_repo import TaskRunRepo
from ozon_common.dal.session import bind_engine, session_scope
from ozon_common.gen_image import (
    LOCALIZE_PROMPT,
    SCENE_PROMPT,
    WHITE_MAIN_PROMPT,
    GenImageConfig,
    build_infographic_prompt,
    create_image,
    edit_image,
    images_from_response,
)
from ozon_common.image_plan import build_image_plan
from ozon_common.mq import consume_gen_jobs
from ozon_common.oss import OssClient
from ozon_common.settings import ai_config

log = logging.getLogger("ozon.worker")
GEN_CONCURRENCY = int(os.environ.get("GEN_CONCURRENCY") or 10)
_GEN_SIZE = "1024x1536"
_GEN_MAX_RETRIES = 3
_USER_ID = 1  # worker 固定读取 admin 用户 settings


def _sync_gen_task(job_id: int, *, status: str | None = None, error: str | None = None, result: dict | None = None) -> None:
    repo = GenJobRepo()
    job = repo.get_gen_job(job_id)
    if job is None:
        return
    counts = repo.count_gen_job_images_by_status(job_id)
    done = int(counts.get("done", 0))
    failed = int(counts.get("failed", 0))
    total = int(job.get("total") or job.get("target") or 0)
    TaskRunRepo().upsert_external(
        job["draft_id"],
        "ai_image",
        "gen_jobs",
        job["id"],
        job.get("user_id"),
        status=status or str(job.get("status") or "running"),
        progress_current=done + failed,
        progress_total=total,
        error=error if error is not None else job.get("error"),
        result={"succeeded": done, "failed": failed, **(result or {})},
    )


def _gen_task_cancelled(job_id: int) -> bool:
    run = TaskRunRepo().get_by_external("ai_image", "gen_jobs", job_id)
    return bool(run and str(run.get("status") or "") in {"cancel_requested", "cancelled"})


def _build_slot_prompt(slot: dict) -> str:
    action = slot.get("action", "")
    designed = str(slot.get("prompt") or "").strip()
    if designed:
        return designed
    if action == "white":
        return WHITE_MAIN_PROMPT
    if action == "localize":
        return LOCALIZE_PROMPT
    if action == "scene":
        hint = str(slot.get("scene_hint") or slot.get("heading") or "").strip()
        return SCENE_PROMPT + (f" Scene context: {hint}" if hint else "")
    if action == "infographic":
        return build_infographic_prompt(
            role=str(slot.get("role") or ""),
            heading=str(slot.get("heading") or ""),
            bullets=slot.get("bullets") or [],
        )
    raise ValueError(f"未知 action: {action}")


def _download_source(url: str) -> str:
    u = str(url or "")
    if u.startswith("/media/"):
        media_root = os.environ.get("IMAGE_WORKER_MEDIA_ROOT") or "/app/ozon-listing-webui/data/images"
        rel = u[len("/media/"):].lstrip("/")
        local = os.path.abspath(os.path.join(media_root, rel))
        root = os.path.abspath(media_root)
        if local.startswith(root + os.sep) and os.path.exists(local):
            fd, path = tempfile.mkstemp(suffix=os.path.splitext(local)[1] or ".png", prefix="ozsrc-")
            try:
                with open(local, "rb") as src:
                    os.write(fd, src.read())
            finally:
                os.close(fd)
            return path
    if u.startswith("/media/"):
        u = f"http://8.152.196.119:8585{u}"
    fd, path = tempfile.mkstemp(suffix=".png", prefix="ozsrc-")
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        os.write(fd, data)
    finally:
        os.close(fd)
    return path


def _generate_image(src_url: str, prompt: str, cfg: GenImageConfig) -> bytes:
    tmp = _download_source(src_url)
    try:
        resp = edit_image(cfg, prompt, [tmp], size=_GEN_SIZE, output_format="png")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    picked = images_from_response(resp)
    if not picked:
        raise RuntimeError("出图未返回图片")
    return picked[0]


def _generate_with_retry(src_url: str, prompt: str, cfg: GenImageConfig,
                         max_retries: int = _GEN_MAX_RETRIES) -> bytes:
    last = None
    for attempt in range(max_retries):
        try:
            return _generate_image(src_url, prompt, cfg)
        except Exception as exc:
            last = exc
            if attempt < max_retries - 1:
                time.sleep(min(4.0 * (2 ** attempt), 60.0))
    raise last


def _generate_with_retry_multi(src_urls: list[str], prompt: str, cfg: GenImageConfig,
                               max_retries: int = _GEN_MAX_RETRIES) -> bytes:
    """多源图生图：下载每张到临时文件，传多路径给 edit_image。"""
    last = None
    for attempt in range(max_retries):
        try:
            tmp_files = [_download_source(u) for u in src_urls]
            try:
                resp = edit_image(cfg, prompt, tmp_files, size=_GEN_SIZE, output_format="png")
            finally:
                for fp in tmp_files:
                    if os.path.exists(fp):
                        os.remove(fp)
            picked = images_from_response(resp)
            if not picked:
                raise RuntimeError("出图未返回图片")
            return picked[0]
        except Exception as exc:
            last = exc
            if attempt < max_retries - 1:
                time.sleep(min(4.0 * (2 ** attempt), 60.0))
    raise last


def _generate_text2img(prompt: str, cfg: GenImageConfig,
                       max_retries: int = _GEN_MAX_RETRIES) -> bytes:
    """文生图：无源图，纯 prompt 生成。"""
    last = None
    for attempt in range(max_retries):
        try:
            resp = create_image(cfg, prompt, size=_GEN_SIZE, output_format="png")
            picked = images_from_response(resp)
            if not picked:
                raise RuntimeError("出图未返回图片")
            return picked[0]
        except Exception as exc:
            last = exc
            if attempt < max_retries - 1:
                time.sleep(min(4.0 * (2 ** attempt), 60.0))
    raise last


def _img_type_from_label(label: str) -> str:
    s = str(label or "")
    for kw, t in (("白底", "白底"), ("主图", "白底"), ("细节", "细节"),
                  ("场景", "场景"), ("尺寸", "尺寸"), ("卖点", "卖点"), ("包装", "包装")):
        if kw in s:
            return t
    return "其他"


def _design_image_plan(draft: dict, target: int, settings: dict) -> list[dict]:
    und = (draft.get("source_raw") or {}).get("understanding")
    if isinstance(und, dict) and und:
        images = draft.get("images") or []
        plan = build_image_plan(und, images)
        if plan:
            return plan
    return build_image_plan(None, draft.get("images") or [])


def handle_job(job_id: int, draft_id: int, target: int, mode: str = "plan") -> None:
    try:
        log.info(f"[job {job_id}] start, draft={draft_id}, target={target}, mode={mode}")
        with session_scope():
            if _gen_task_cancelled(job_id):
                GenJobRepo().update_gen_job(job_id, {"status": "cancelled", "error": "cancelled"})
                _sync_gen_task(job_id, status="cancelled", error="cancelled", result={"phase": "cancelled"})
                log.info(f"[job {job_id}] cancelled before start")
                return

        # 读取 settings + draft（只读，单 scope）
        with session_scope():
            settings = SettingsRepo().get_settings(_USER_ID)
            draft = DraftImageRepo().get_draft(draft_id)
        if not draft:
            raise RuntimeError(f"draft {draft_id} not found")

        img_cfg_data = ai_config(settings, "image")
        cfg = GenImageConfig(api_key=img_cfg_data.get("key") or None,
                             base_url=img_cfg_data.get("base") or None,
                             model=img_cfg_data.get("model") or None)

        # 0. 幂等：读已有图片槽
        with session_scope():
            existing_images = GenJobRepo().get_gen_job_images(job_id)
        done_slots = {str(i["slot_id"]) for i in existing_images if i["status"] == "done"}

        # 1. 设计/读取图集计划
        if _gen_task_cancelled(job_id):
            with session_scope():
                GenJobRepo().update_gen_job(job_id, {"status": "cancelled", "error": "cancelled"})
                _sync_gen_task(job_id, status="cancelled", error="cancelled", result={"phase": "cancelled"})
            return
        if mode in ("custom", "batch"):
            # 槽位已在 API 侧创建，跳过设计
            if not existing_images:
                raise RuntimeError(f"{mode} 模式缺少 gen_job_images 槽位")
        elif not existing_images:
            with session_scope():
                GenJobRepo().set_gen_job_status(job_id, "designing")
                _sync_gen_task(job_id, status="designing", result={"phase": "design"})
            images = list(draft.get("images") or [])
            if not images:
                raise RuntimeError("草稿没有图片，无法出图")
            plan = _design_image_plan(draft, target, settings)
            with session_scope():
                GenJobRepo().update_gen_job(job_id, {"total": len(plan)})
                _sync_gen_task(job_id, status="designing", result={"phase": "design", "planned": len(plan)})
            with session_scope():
                GenJobRepo().create_gen_job_images(job_id, plan)
                _sync_gen_task(job_id, status="designing", result={"phase": "design", "planned": len(plan)})

        with session_scope():
            plan_images = GenJobRepo().get_gen_job_images(job_id)
        if not plan_images:
            raise RuntimeError("图集计划为空")

        with session_scope():
            GenJobRepo().set_gen_job_status(job_id, "running")
            _sync_gen_task(job_id, status="running", result={"phase": "generate"})

        # 2. 读取 slot 元信息
        sr = draft.get("source_raw") or {}
        image_plan = sr.get("image_plan") or []
        images = list(draft.get("images") or [])

        def _find_slot_meta(slot_id: str) -> dict:
            for x in image_plan:
                if str(x.get("slot_id") or "") == slot_id:
                    return x
            return {}

        # 3. 并发生成
        def _process_one(t: tuple) -> dict:
            image_id, slot_id, label = t
            try:
                if _gen_task_cancelled(job_id):
                    return {"id": image_id, "ok": False, "cancelled": True}
                with session_scope():
                    GenJobRepo().set_gen_job_image_status(image_id, "running")
                    _sync_gen_task(job_id, status="running", result={"phase": "generate", "slot_id": slot_id})
                slot = _find_slot_meta(slot_id)
                surl = str(slot.get("source_url") or "")
                ref_url = str(slot.get("ref_url") or "")
                prompt = str(slot.get("prompt") or "").strip()
                if not prompt:
                    prompt = _build_slot_prompt(slot) if slot else WHITE_MAIN_PROMPT

                if mode == "custom" and surl:
                    img_paths = [surl]
                    if ref_url:
                        img_paths.append(ref_url)
                    img_bytes = _generate_with_retry_multi(img_paths, prompt, cfg)
                elif mode == "custom" and not surl:
                    img_bytes = _generate_text2img(prompt, cfg)
                elif mode == "batch":
                    # 批量出图：用 source_idx 从草稿取源图
                    src_idx = slot.get("source_idx", 0)
                    src_url = images[max(0, min(int(src_idx), len(images) - 1))]
                    img_bytes = _generate_with_retry(src_url, prompt, cfg)
                else:
                    # Plan 模式：从草稿图片取源图
                    src_idx = slot.get("source_idx", 0)
                    src_url = images[max(0, min(int(src_idx), len(images) - 1))]
                    img_bytes = _generate_with_retry(src_url, prompt, cfg)

                oss_client = OssClient(settings)
                oss_url = oss_client.upload_bytes(img_bytes, "png")
                with session_scope():
                    DraftImageRepo().add_draft_image(draft_id, oss_url, type=_img_type_from_label(label), source="generated")
                with session_scope():
                    GenJobRepo().set_gen_job_image_status(image_id, "done", url=oss_url)
                    _sync_gen_task(job_id, status="running", result={"phase": "generate", "slot_id": slot_id})
                return {"id": image_id, "ok": True, "url": oss_url}
            except Exception as exc:
                tb = traceback.format_exc()
                log.error(f"[job {job_id}] slot {slot_id} failed: {exc}\\n{tb[-500:]}")
                with session_scope():
                    GenJobRepo().set_gen_job_image_status(image_id, "failed", error=str(exc)[:500])
                    _sync_gen_task(job_id, status="running", result={"phase": "generate", "slot_id": slot_id})
                return {"id": image_id, "ok": False, "error": str(exc)}

        pending = [(pi["id"], pi["slot_id"], pi["label"]) for pi in plan_images
                   if pi["status"] not in ("done", "failed") and pi["slot_id"] not in done_slots]

        with ThreadPoolExecutor(max_workers=GEN_CONCURRENCY) as ex:
            futures = [ex.submit(_process_one, t) for t in pending]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:
                    log.error(f"[job {job_id}] task exception: {exc}")

        # 4. 汇总
        with session_scope():
            if _gen_task_cancelled(job_id):
                GenJobRepo().update_gen_job(job_id, {"status": "cancelled", "error": "cancelled"})
                _sync_gen_task(job_id, status="cancelled", error="cancelled", result={"phase": "cancelled"})
                log.info(f"[job {job_id}] cancelled")
                return
            counts = GenJobRepo().count_gen_job_images_by_status(job_id)
        succeeded = counts.get("done", 0)
        failed = counts.get("failed", 0)
        final_status = "done" if succeeded > 0 else "failed"
        with session_scope():
            GenJobRepo().update_gen_job(job_id, {"status": final_status, "succeeded": succeeded, "failed": failed})
            _sync_gen_task(job_id, status=final_status, result={"phase": "done"})
        log.info(f"[job {job_id}] {final_status}: {succeeded} ok / {failed} fail")

    except Exception as exc:
        log.exception(f"[job {job_id}] fatal: {exc}")
        try:
            with session_scope():
                status = "cancelled" if _gen_task_cancelled(job_id) else "failed"
                GenJobRepo().update_gen_job(job_id, {"status": status, "error": str(exc)[:500]})
                _sync_gen_task(job_id, status=status, error=str(exc)[:500], result={"phase": "fatal"})
        except Exception:
            pass
        raise


def main() -> None:
    os.environ.setdefault("OSS_DISABLE_CRC64", "1")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
    sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
    log.info(f"Worker started, concurrency={GEN_CONCURRENCY}")
    # 绑定 SQLAlchemy engine（MySQL env 优先）
    bind_engine(engine_for(None))
    consume_gen_jobs(lambda job_id, draft_id, target, mode: handle_job(job_id, draft_id, target, mode))


if __name__ == "__main__":
    main()
