from __future__ import annotations


class GenJobMixin:
    """生图 MQ 任务（gen_jobs）。"""

    def submit_gen_job(self, draft_id: int, target: int) -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        if self.store.has_active_gen_job(draft_id):
            raise ValueError("该草稿已有进行中的出图任务，请等待完成")
        job = self.store.create_gen_job(draft_id, target)
        run = self.store.create_task_run(
            draft_id,
            "ai_image",
            status="queued",
            progress_total=target,
            source="gen_jobs",
            external_id=job["id"],
        )
        try:
            from ozon_common.mq import publish_gen_job  # noqa: PLC0415
            publish_gen_job(job["id"], draft_id, target)
        except Exception as exc:
            self.store.update_gen_job(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            self.store.update_task_run(run["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")
        return {"job_id": job["id"], "task_run_id": run["id"], "status": job["status"]}

    def submit_gen_images_custom(self, draft_id: int, payload: dict) -> dict:
        """用户自定义出图（AiImageDialog）：选 N 张源图 + 提示词 + 可选参考图 → 建 gen_job → MQ → worker。
        每张源图一个槽，源图为空(文生图)则建 1 个空槽。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        source_urls = [str(u).strip() for u in (payload.get("source_urls") or []) if str(u).strip()]
        if not source_urls:
            source_urls = [""]   # text2img: 一个空槽
        ref_url = str(payload.get("ref_url") or "").strip() or None
        prompt = str(payload.get("prompt") or "").strip()
        size = str(payload.get("size") or "1024x1536").strip()
        as_main = bool(payload.get("as_main"))
        target = len(source_urls)
        job = self.store.create_gen_job(draft_id, target)
        run = self.store.create_task_run(
            draft_id,
            "ai_image",
            status="queued",
            progress_total=target,
            source="gen_jobs",
            external_id=job["id"],
        )
        # 构造 image_plan（worker 读它来获取 prompt 和 source_url）
        slots = []
        for i, surl in enumerate(source_urls):
            sid = f"custom_{i}"
            slots.append({
                "slot_id": sid, "label": f"自定义出图{i+1}",
                "action": "custom", "source_idx": 0,
                "prompt": prompt, "size": size, "as_main": (as_main and i == 0),
                "source_url": surl or None, "ref_url": ref_url,
            })
        self.store.create_gen_job_images(job["id"], slots)
        # 存 image_plan 到 source_raw 供 worker 读取
        sr = dict(draft.get("source_raw") or {})
        sr["image_plan"] = [(sr.get("image_plan") or []) + slots][0]
        self.store.update_draft(draft_id, {"source_raw": sr})
        try:
            from ozon_common.mq import publish_gen_job  # noqa: PLC0415
            publish_gen_job(job["id"], draft_id, target, mode="custom")
        except Exception as exc:
            self.store.update_gen_job(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            self.store.update_task_run(run["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")
        return {"job_id": job["id"], "task_run_id": run["id"], "status": job["status"]}

    def submit_batch_gen_job(self, draft_id: int, source_indices: list[int], action: str) -> dict:
        """批量出图（白底/俄化/场景/细节/重做）：每个 source_index 一个槽，走 worker 异步。"""
        from ozon_common.gen_image import (  # noqa: PLC0415
            LOCALIZE_PROMPT,
            SCENE_PROMPT,
            WHITE_MAIN_PROMPT,
            build_infographic_prompt,
        )
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        if self.store.has_active_gen_job(draft_id):
            raise ValueError("该草稿已有进行中的出图任务")
        indices = [int(i) for i in source_indices if isinstance(i, int)]
        if not indices:
            raise ValueError("未选择图片")
        label_map = {"white": "白底图", "localize": "俄化", "scene": "场景图",
                     "detail": "细节图", "redo": "重做"}
        label = label_map.get(action, action)
        job = self.store.create_gen_job(draft_id, len(indices))
        run = self.store.create_task_run(
            draft_id,
            "ai_image",
            status="queued",
            progress_total=len(indices),
            source="gen_jobs",
            external_id=job["id"],
        )
        slots = []
        for si in indices:
            p = ""
            if action == "white":
                p = WHITE_MAIN_PROMPT
            elif action == "localize":
                p = LOCALIZE_PROMPT
            elif action == "scene":
                p = SCENE_PROMPT
            elif action in ("detail", "redo"):
                p = build_infographic_prompt(role="细节" if action == "detail" else "")
            sid = f"batch_{action}_{si}"
            slots.append({"slot_id": sid, "label": f"{label}#{si}", "action": "batch",
                         "source_idx": si, "prompt": p})
        self.store.create_gen_job_images(job["id"], slots)
        sr = dict(draft.get("source_raw") or {})
        sr["image_plan"] = (sr.get("image_plan") or []) + slots
        self.store.update_draft(draft_id, {"source_raw": sr})
        try:
            from ozon_common.mq import publish_gen_job  # noqa: PLC0415
            publish_gen_job(job["id"], draft_id, len(indices), mode="batch")
        except Exception as exc:
            self.store.update_gen_job(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            self.store.update_task_run(run["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")
        return {"job_id": job["id"], "task_run_id": run["id"], "status": job["status"]}

    def get_gen_job_status(self, job_id: int) -> dict:
        job = self.store.get_gen_job(job_id)
        if job is None:
            raise KeyError(f"job {job_id} not found")
        images = self.store.get_gen_job_images(job_id)
        succeeded = sum(1 for i in images if i["status"] == "done")
        failed = sum(1 for i in images if i["status"] == "failed")
        self.store.upsert_task_run_external(
            job["draft_id"],
            "ai_image",
            "gen_jobs",
            job["id"],
            job.get("user_id"),
            status=job["status"],
            progress_current=succeeded + failed,
            progress_total=job["target"],
            error=job.get("error"),
            result={"succeeded": succeeded, "failed": failed},
        )
        return {"job_id": job["id"], "status": job["status"],
                "target": job["target"], "total": job["total"],
                "succeeded": job["succeeded"], "failed": job["failed"],
                "error": job.get("error"), "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "images": [{"slot_id": i["slot_id"], "label": i["label"],
                            "status": i["status"], "url": i.get("url"),
                            "error": i.get("error")} for i in images]}

    def get_latest_gen_job(self, draft_id: int) -> dict:
        job = self.store.get_latest_gen_job(draft_id)
        if job is None:
            raise KeyError(f"draft {draft_id} 没有出图任务")
        return self.get_gen_job_status(job["id"])

    def batch_latest_gen_jobs(self, draft_ids: list[int]) -> dict:
        """批量查多个草稿的全部出图任务（卡片列表展示用）。返回 {draft_id: [jobs]}。"""
        out = {}
        for did in draft_ids:
            try:
                jobs = self.store.list_gen_jobs(did)
            except Exception:
                continue
            if jobs:
                summaries = []
                for j in jobs:
                    imgs = self.store.get_gen_job_images(j["id"])
                    done = sum(1 for i in imgs if i["status"] == "done")
                    fail = sum(1 for i in imgs if i["status"] == "failed")
                    run = sum(1 for i in imgs if i["status"] == "running")
                    summaries.append({
                        "job_id": j["id"], "status": j["status"],
                        "target": j["target"],
                        "total": j["total"] or len(imgs),
                        "succeeded": done, "failed": fail, "running": run,
                        "created_at": j.get("created_at"),
                        "updated_at": j.get("updated_at"),
                    })
                out[str(did)] = summaries
        return {"jobs": out}
