"""AiVideoMixin — App 的「AI 视频」域（Agnes 图生视频）。"""
from __future__ import annotations

import webui.ai_video as ai_video  # noqa: E402
import webui.media as _media  # noqa: E402


class AiVideoMixin:

    def start_ai_video(self, draft_id: int, *, prompt: str | None = None,
                       image_url: str | None = None) -> dict:
        """启动 Agnes 图生视频后台任务（全局单任务，约 5 秒 121帧@24fps）。
        默认用草稿主图 + 商品展示运镜提示词；完成后 _on_ai_video_done 回写草稿。"""
        from webui import agnes  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        settings = self.store.get_settings()
        agnes._conf(settings)   # 没配 key 在启动前就报错（不进后台线程才能让前端看到 400）
        img_in = str(image_url or "").strip()
        if not img_in:
            imgs = draft.get("images") or []
            if not imgs:
                raise ValueError("草稿没有图片，无法图生视频（先采集或上传图片）")
            img_in = str(imgs[0])
        image = self._resolve_image_input(img_in)
        title = str(draft.get("ozon_title") or draft.get("source_title") or "").strip()
        p = str(prompt or "").strip() or (
            "Smooth cinematic product showcase video, slow camera orbit around the product, "
            "soft studio lighting, the product stays centered and visually identical to the "
            f"reference image. Product: {title[:200]}"
        )
        create_fn = lambda: agnes.create_video_task(settings, p, image=image)  # noqa: E731
        query_fn = lambda vid: agnes.query_video(settings, vid)  # noqa: E731
        return ai_video.start_video(create_fn, query_fn, self._on_ai_video_done, draft_id)

    def _on_ai_video_done(self, draft_id: int, url: str) -> None:
        """视频任务完成回调（后台线程）：写 video_url + 下载本地预览副本。
        - 本地副本放 draft-{id}-ai key（避免覆盖采集来的源视频），overwrite=True 防重生成命中旧缓存
        - 下载完再重读草稿（下载可能数十秒，别用旧快照盖掉期间的编辑）
        - 下载失败把 video_local 置空：宁可前端回退播 video_url，也别播上一版的旧副本
        - 显式保留 status：这是后台异步写，不该把已发布草稿悄悄打回 ready/invalid"""
        try:
            vloc = _media.download_video(url, f"draft-{draft_id}-ai", overwrite=True)
        except Exception:  # noqa: BLE001  本地副本失败不影响 video_url 落库
            vloc = ""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            return
        patch: dict = {
            "video_url": url,
            "source_raw": {**(draft.get("source_raw") or {}), "video_local": vloc},
        }
        if draft.get("status"):
            patch["status"] = draft["status"]
        self.store.update_draft(draft_id, patch)

    def ai_video_status(self) -> dict:
        return ai_video.video_status()

    def stop_ai_video(self) -> dict:
        return ai_video.request_stop()
