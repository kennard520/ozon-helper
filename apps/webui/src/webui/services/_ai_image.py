"""AiImageMixin — App 的「AI 出图」域（候选/图集计划/信息图/富文本）。"""
from __future__ import annotations

import os
from pathlib import Path

import webui.media as _media  # noqa: E402
from webui.services._helpers import _img_type_from_label  # noqa: E402

# 模块级常量（与 app_service 同步；此处独立定义避免循环 import）
_FONT_PATH = str(Path(__file__).resolve().parents[1] / "assets" / "Montserrat-VF.ttf")
_GEN_SIZE = "1024x1536"


class AiImageMixin:

    def ai_image_prompts(self, draft_id: int, n_points: int = 3) -> dict:
        """生成 ChatGPT 出图提示词(主图 + n_points 张卖点图)，不写库。
        同时返回原始图片 URL，供用户手动上传 ChatGPT 当参考图。
        AI 未配置 → deepseek_chat 抛 RuntimeError(路由转 400)。"""
        from webui.ai_card import _SYS_IMG_PROMPTS, build_image_prompt_input, parse_image_prompts  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        # 注意：不能用 `n_points or 3`——n_points=0 是 falsy 会变 3。显式判 None。
        n = max(1, min(int(n_points if n_points is not None else 3), 6))
        settings = self.store.get_settings()
        system = _SYS_IMG_PROMPTS.format(n=n)
        out = self._card_chat(settings, draft)(system, build_image_prompt_input(draft))
        parsed = parse_image_prompts(out, n)
        _sr = draft.get("source_raw") or {}
        detail_images = _sr.get("detail_images") or []
        detail_local = _sr.get("detail_local") or []   # 本地副本(避防盗链)，给缩略图显示
        return {
            "ok": True,
            "main": parsed["main"],
            "selling_points": parsed["selling_points"],
            # 两池化后:采集图在 materials(in_gallery=0),用所有 materials URL 作参考图
            "source_images": [m["url"] for m in (draft.get("materials") or [])
                              if m.get("source") == "collected"]
                             or (draft.get("images") or []),
            "local_images": draft.get("local_images") or [],
            "detail_images": detail_images,    # 源 URL，给 ChatGPT 当参考(复制全部用)
            "detail_local": detail_local,      # 本地副本，缩略图显示用(避防盗链)
        }

    def _resolve_image_input(self, url: str) -> str:
        """把前端选的源图变成 Agnes 能取到的输入：http(s) 直接用；/media/ 本地副本
        外网不可达 → 读字节转 data URI（图生图官方支持 Data URI Base64；图生视频
        官方只写了 URL，data URI 是尽力而为，被拒会以 Agnes 400 浮出来）。"""
        from webui import agnes  # noqa: PLC0415
        u = str(url or "").strip()
        if u.startswith("http"):
            return u
        if u.startswith("/media/"):
            ext = u.rsplit(".", 1)[-1].lower() if "." in u else ""
            if ext in ("mp4", "mov", "webm", "m4v"):
                raise ValueError(f"源图不能是视频文件: {u}")
            data = _media.read_media_bytes(u)
            if not data:
                raise ValueError(f"本地图读取失败: {u}")
            return agnes.to_data_uri(data, u)
        raise ValueError("源图必须是 http(s) URL 或 /media/ 本地图")

    def ai_generate_image(self, draft_id: int, *, mode: str = "text2img", prompt: str = "",
                          source_url: str | None = None, size: str | None = None,
                          as_main: bool = False) -> dict:
        """Agnes 生成商品图：text2img(营销图) / img2img(白底主图等，保构图改场景)。
        生成结果下载到本地 /media/（不依赖 Agnes URL 存活期），挂进 draft.images；
        发布时由 OSS rehost 链路把本地图上传到你的 OSS。as_main=True 插到首位当主图。"""
        from webui import agnes  # noqa: PLC0415
        import webui.app_service as _app_svc  # noqa: PLC0415  # patch 兼容
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        p = str(prompt or "").strip()
        if not p:
            raise ValueError("提示词不能为空")
        m = str(mode or "text2img").strip().lower()
        settings = self.store.get_settings()
        sources = None
        if m == "img2img":
            if not str(source_url or "").strip():
                raise ValueError("图生图需要选择一张源图")
            sources = [self._resolve_image_input(str(source_url))]
        # 出图引擎 admin 可切：ai_image.engine == gptimage → 走 gen_image；默认 agnes
        from webui.settings_migrate import ai_config  # noqa: PLC0415
        imgcfg = ai_config(settings, "image")
        if imgcfg["engine"] == "gptimage":
            from ozon_common.gen_image import create_image, edit_image, images_from_response  # noqa: PLC0415
            gcfg = self._gen_image_cfg(settings)
            tmp = None
            try:
                if str(source_url or "").strip():       # img2img：源图落临时文件给 edit
                    tmp = self._local_image_path(str(source_url))
                    resp = edit_image(gcfg, p, [tmp], size=size or _GEN_SIZE, output_format="png")
                else:                                    # text2img
                    resp = create_image(gcfg, p, size=size or _GEN_SIZE, output_format="png")
            finally:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
            picked = images_from_response(resp)
            if not picked:
                raise RuntimeError("gptimage 未返回图片")
            data = picked[0]
            remote_url = ""
            fname = "gptimage-ai.png"
        else:
            remote_url = agnes.generate_image(settings, p, size=size or _GEN_SIZE,
                                              source_images=sources)
            data = _app_svc._download_bytes(remote_url, timeout=120)
            ext = remote_url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
            fname = f"agnes-ai.{ext if ext in ('png', 'jpg', 'jpeg', 'webp') else 'png'}"
        if len(data) > 20 * 1024 * 1024:   # 与上传路由同口径的 20MB 上限
            raise RuntimeError(f"生成图过大({len(data) // 1024 // 1024}MB > 20MB)")
        local = _media.save_upload(f"draft-{draft_id}", fname, data)
        # 生图可能阻塞数分钟——写前重读草稿，别用进入时的旧快照盖掉期间的用户编辑/并发生成
        cur = self.store.get_draft(draft_id)
        if cur is None:
            raise KeyError(f"draft {draft_id} not found")
        images = list(cur.get("images") or [])
        patch: dict = {"images": images}
        if as_main:
            images.insert(0, local)
            # images↔local_images 是按下标配对的平行数组（前端 localMap），头插必须同步补位
            locs = list(cur.get("local_images") or [])
            if locs:
                patch["local_images"] = ["", *locs]
        else:
            images.append(local)
        updated = self.store.update_draft(draft_id, patch)
        return {"ok": True, "draft": updated, "image": local, "remote_url": remote_url}

    def _image_bytes(self, src: str) -> bytes:
        """读一张草稿图的字节：http(s)→下载；/media/→本地副本。"""
        import webui.app_service as _app_svc  # noqa: PLC0415  # patch 兼容
        u = str(src or "").strip()
        if u.startswith("http"):
            return _app_svc._download_bytes(u)
        if u.startswith("/media/"):
            data = _media.read_media_bytes(u)
            if not data:
                raise ValueError(f"本地图读取失败: {u}")
            return data
        raise ValueError("图片必须是 http(s) URL 或 /media/ 本地图")

    def make_infographic(self, draft_id: int, *, source_index: int = 0, heading: str = "",
                         bullets: list | None = None, watermark: str = "") -> dict:
        """把草稿第 source_index 张图做成俄语信息图（底部面板 + 标题 + 要点），可选叠店铺水印，
        存 /media/ 并追加到 draft.images。标题缺省取 ozon_title。引擎无关、纯 PIL（Montserrat）。"""
        from webui.image_compose import add_watermark, compose_infographic  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        imgs = list(draft.get("images") or [])
        if not imgs:
            raise ValueError("草稿没有图片，无法生成信息图（先采集或生成主图）")
        idx = max(0, min(int(source_index), len(imgs) - 1))
        data = self._image_bytes(str(imgs[idx]))
        h = str(heading or draft.get("ozon_title") or draft.get("source_title") or "")
        bl = [str(b) for b in (bullets or []) if str(b).strip()]
        ig = compose_infographic(data, heading=h, bullets=bl, font_path=_FONT_PATH)
        wm = str(watermark or "").strip()
        if wm:
            ig = add_watermark(ig, wm, font_path=_FONT_PATH)
        local = _media.save_upload(f"draft-{draft_id}", "infographic.jpg", ig)
        # 生成可能耗时——写前重读草稿，别盖掉期间编辑
        cur = self.store.get_draft(draft_id)
        if cur is None:
            raise KeyError(f"draft {draft_id} not found")
        images = list(cur.get("images") or [])
        images.append(local)
        updated = self.store.update_draft(draft_id, {"images": images})
        return {"ok": True, "draft": updated, "image": local}

    def _local_image_path(self, src: str) -> str:
        """把一张图(http 或 /media/)落成本地临时文件，返回路径（供 gen_image 的 edit 用）。调用方负责删。"""
        import tempfile  # noqa: PLC0415
        data = self._image_bytes(src)
        fd, path = tempfile.mkstemp(suffix=".png", prefix="ozsrc-")
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return path

    def try_copy(self, draft_id: int) -> dict:
        """Ozon 来源草稿：试官方复制(import-by-sku)。可复制→在目标店建复制卡并标记草稿；
        不可复制→返回 copyable=False（前端据此转「原创建卡」分支）。会在你店里真建一张卡。"""
        import re  # noqa: PLC0415

        from webui.listing_build import random_offer_id  # noqa: PLC0415
        from webui.ozon_client_adapter import copy_by_sku  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        # SKU：显式 sku → 商品链接末尾数字（不用 ozon_product_id，那是 Seller API 的另一种 id）
        sku = str(draft.get("sku") or "").strip()
        if not sku:
            m = re.search(r"/product/[^/?#]*?(\d+)/?(?:[?#]|$)", str(draft.get("source_url") or ""))
            sku = m.group(1) if m else ""
        if not sku.isdigit():
            raise ValueError("草稿没有可用的 Ozon SKU（只有带 Ozon 商品链接的草稿能走官方复制）")
        settings = self._settings_for_store(draft.get("store_client_id"))
        offer_id = random_offer_id()
        verdict = copy_by_sku(
            settings, sku=int(sku), offer_id=offer_id,
            price=str(draft.get("price") or "") or None,
            old_price=str(draft.get("old_price") or "") or None,
            currency_code="RUB",
            name=str(draft.get("ozon_title") or draft.get("source_title") or "")[:200] or None)
        if verdict["copyable"]:
            self.store.update_draft(draft_id, {
                "offer_id": offer_id,
                "status": "published" if verdict["status"] == "created" else "draft",
                "publish_response": {"copy": verdict},
            })
        return {"copyable": verdict["copyable"], "status": verdict["status"],
                "offer_id": offer_id if verdict["copyable"] else None,
                "task_id": verdict.get("task_id")}

    def make_rich_content(self, draft_id: int, *, image_indexes: list | None = None) -> dict:
        """把草稿图拼成 Ozon 富文本(billboard 大图序列)，存 draft.source_raw.rich_content_json。
        默认跳过主图(索引0)、其余全进；俄语文字烤在图里(先用「生成俄语信息图」做几张再来这步)。
        发布时 to_ozon_import_item 自动塞属性 11254、rewrite_item_media 把图链换 OSS 直链。"""
        from webui.drafts import loads_json  # noqa: PLC0415
        from webui.listing_build import build_rich_content  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        imgs = list(draft.get("images") or [])
        if not imgs:
            raise ValueError("草稿没有图片，无法生成富文本（先采集/生成图片）")
        if image_indexes:
            sel = [imgs[i] for i in image_indexes if isinstance(i, int) and 0 <= i < len(imgs)]
        else:
            sel = imgs[1:] if len(imgs) > 1 else imgs   # 默认跳过主图，其余进富文本
        if not sel:
            raise ValueError("没有可用于富文本的图片")
        rc = build_rich_content(sel)
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = dict(sr or {})
        sr["rich_content_json"] = rc
        updated = self.store.update_draft(draft_id, {"source_raw": sr})
        return {"ok": True, "draft": updated, "blocks": len(rc["content"])}

    def _add_candidate(self, draft_id: int, data: bytes, label: str, *, slot: str = "") -> str:
        """生成的图直接 INSERT draft_images 表行；记 image_types + slot_images 进 source_raw。
        返回本地 URL。方法名沿用以减少调用点改动。"""
        if len(data) > 20 * 1024 * 1024:
            raise RuntimeError("生成图过大(>20MB)")
        local = _media.save_upload(f"draft-{draft_id}-gen", "gen.png", data)
        img_type = _img_type_from_label(label)
        with self._cand_lock:
            self.store.add_draft_image(draft_id, local, type=img_type, source="generated")
            draft = self.store.get_draft(draft_id)
            if draft is None:
                raise KeyError(f"draft {draft_id} not found")
            sr = dict(draft.get("source_raw") or {})
            types = dict(sr.get("image_types") or {})
            types[local] = img_type
            sr["image_types"] = types
            if slot:
                slot_imgs = dict(sr.get("slot_images") or {})
                slot_imgs[str(slot)] = local
                sr["slot_images"] = slot_imgs
            self.store.update_draft(draft_id, {"source_raw": sr, "status": draft.get("status")})
        return local

    def _gen_image_cfg(self, settings: dict | None = None):
        """按 DB 的 ai_image 槽（接口地址/Key/模型）构造 GenImageConfig；字段留空回退 GPTPLUS5_* 环境变量。
        俄化/重做/AI生图统一走它 → 生图 AI 配置可全部存数据库。"""
        from ozon_common.gen_image import GenImageConfig  # noqa: PLC0415
        from webui.settings_migrate import ai_config  # noqa: PLC0415
        s = settings if settings is not None else self.store.get_settings()
        c = ai_config(s, "image")
        return GenImageConfig(api_key=(c.get("key") or None),
                              base_url=(c.get("base") or None),
                              model=(c.get("model") or None))

    def _edit_source_image(self, draft_id: int, source_index: int, prompt: str) -> bytes:
        """对草稿第 source_index 张图做 gpt-image edit(传源图保产品一致),返回结果字节。"""
        from ozon_common.gen_image import edit_image, images_from_response  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        imgs = list(draft.get("images") or [])
        if not imgs:
            raise ValueError("草稿没有图片（先采集/生成）")
        idx = max(0, min(int(source_index), len(imgs) - 1))
        tmp = self._local_image_path(str(imgs[idx]))
        try:
            resp = edit_image(self._gen_image_cfg(), prompt, [tmp], size=_GEN_SIZE, output_format="png")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        picked = images_from_response(resp)
        if not picked:
            raise RuntimeError("出图未返回图片")
        return picked[0]

    def localize_image(self, draft_id: int, source_index: int = 0) -> dict:
        """单张俄化:把第 source_index 张图上的中文换成俄语(gpt-image edit,保图不变),结果进候选区。"""
        from ozon_common.gen_image import LOCALIZE_PROMPT  # noqa: PLC0415
        data = self._edit_source_image(draft_id, source_index, LOCALIZE_PROMPT)
        url = self._add_candidate(draft_id, data, f"俄化#{source_index}")
        return {"ok": True, "candidate": url, "draft": self.store.get_draft(draft_id)}

    def regen_image(self, draft_id: int, source_index: int = 0, *, role: str = "",
                    heading: str = "", bullets: list | None = None) -> dict:
        """单张重做:按角色 + 俄语文字 重新生成(gpt-image edit 源图),结果进候选区。数字需 QC。"""
        from ozon_common.gen_image import build_infographic_prompt  # noqa: PLC0415
        prompt = build_infographic_prompt(role=role, heading=heading, bullets=bullets)
        data = self._edit_source_image(draft_id, source_index, prompt)
        url = self._add_candidate(draft_id, data, f"重做#{source_index}")
        return {"ok": True, "candidate": url, "draft": self.store.get_draft(draft_id)}

    def whiten_main(self, draft_id: int, source_index: int = 0) -> dict:
        """选第 source_index 张图做白底电商主图(gpt-image edit + 白底提示词),结果进候选区。"""
        from ozon_common.gen_image import WHITE_MAIN_PROMPT  # noqa: PLC0415
        data = self._edit_source_image(draft_id, source_index, WHITE_MAIN_PROMPT)
        url = self._add_candidate(draft_id, data, f"白底主图#{source_index}")
        return {"ok": True, "candidate": url, "draft": self.store.get_draft(draft_id)}

    def scene_image(self, draft_id: int, source_index: int = 0, *, hint: str = "") -> dict:
        """选第 source_index 张图做场景/氛围图(保产品一致 + 放进使用场景),可带场景提示。结果进候选区。"""
        from ozon_common.gen_image import SCENE_PROMPT  # noqa: PLC0415
        prompt = SCENE_PROMPT + (f" Scene hint: {str(hint).strip()}" if str(hint or "").strip() else "")
        data = self._edit_source_image(draft_id, source_index, prompt)
        url = self._add_candidate(draft_id, data, f"场景图#{source_index}")
        return {"ok": True, "candidate": url, "draft": self.store.get_draft(draft_id)}

    def _load_image_plan(self, draft_id: int, *, force: bool = False):
        """取/建图集计划(缓存 source_raw.image_plan)。返回 (draft, sr, plan)。"""
        from ozon_common.image_plan import build_image_plan  # noqa: PLC0415
        from webui.drafts import loads_json  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = dict(sr or {})
        plan = sr.get("image_plan")
        if force or not isinstance(plan, list) or not plan:
            understanding = sr.get("understanding") if isinstance(sr.get("understanding"), dict) else None
            plan = build_image_plan(understanding, draft.get("images"))
            sr["image_plan"] = plan
            self.store.update_draft(draft_id, {"source_raw": sr})
        return draft, sr, plan

    def image_plan(self, draft_id: int, *, force: bool = False) -> dict:
        """图集计划 + 每槽状态(todo 待做 / applied 已生成)。生成图直接进 images、不再有候选态；
        据 slot_images(槽→已生成图url) 是否仍在 draft.images 判断该槽是否已出图。"""
        draft, sr, plan = self._load_image_plan(draft_id, force=force)
        images = {str(u) for u in (draft.get("images") or [])}
        slot_imgs = sr.get("slot_images") or {}
        out = []
        for s in plan:
            u = str(slot_imgs.get(str(s.get("slot_id"))) or "")
            done = bool(u and u in images)   # 用户删了该图 → 回到 todo，可重出
            out.append({**s, "status": "applied" if done else "todo",
                        "candidate_url": u if done else ""})
        return {"ok": True, "plan": out}

    def design_image_plan(self, draft_id: int, *, target: int = 10) -> dict:
        """**AI 设计图集**：把看图理解 + 源图清单(角色) 喂给 LLM 当"美术总监"，设计 ~target 张
        符合 Ozon 的商品图方案(白底主图/细节俄化/场景/卖点·规格信息图)，产出与规则版同形状的槽位，
        覆盖写入 source_raw.image_plan(后续渲染/界面照旧用)。LLM 失败/空 → 回退规则版 build_image_plan。"""
        import json as _json  # noqa: PLC0415

        from ozon_common.image_plan import build_image_plan  # noqa: PLC0415
        from webui.ai_card import _SYS_IMG_PLAN, _extract_json, build_profile  # noqa: PLC0415
        from webui.drafts import loads_json  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = dict(sr or {})
        images = list(draft.get("images") or [])
        if not images:
            raise ValueError("草稿没有图片，无法设计图集（先采集/生成图片）")
        und = sr.get("understanding") if isinstance(sr.get("understanding"), dict) else {}
        if not und:   # 设计强依赖看图理解(图片角色/卖点/规格)——没有就先自动跑一遍
            self.understand_draft(draft_id)
            draft = self.store.get_draft(draft_id)
            sr = draft.get("source_raw")
            if isinstance(sr, str):
                sr = loads_json(sr, {})
            sr = dict(sr or {})
            und = sr.get("understanding") if isinstance(sr.get("understanding"), dict) else {}
        n = len(images)
        roles = {im["idx"]: str(im.get("role") or "") for im in (und.get("images") or [])
                 if isinstance(im, dict) and isinstance(im.get("idx"), int) and 0 <= im["idx"] < n}
        inventory = [{"idx": i, "role": roles.get(i, "")} for i in range(n)]
        profile = build_profile(sr, understanding=und)
        user = (f"Target image count: {int(target)}\nSource photos (use source_idx from this inventory):\n"
                + _json.dumps(inventory, ensure_ascii=False) + "\n\nProduct understanding:\n" + profile)
        chat = self._card_chat(self.store.get_settings(), draft)
        valid: list[dict] = []
        try:
            out = _extract_json(chat(_SYS_IMG_PLAN, user))
            seen: set = set()
            for i, s in enumerate(out.get("slots") or []):
                action = str(s.get("action") or "").strip().lower()
                if action not in ("white", "localize", "scene", "infographic"):
                    continue
                try:
                    si = int(s.get("source_idx"))
                except (TypeError, ValueError):
                    si = 0
                si = si if 0 <= si < n else 0
                sid = str(s.get("slot_id") or "").strip() or f"s{i}"
                if sid in seen:
                    sid = f"{sid}_{i}"
                seen.add(sid)
                valid.append({"slot_id": sid, "role": str(s.get("role") or ""),
                              "label": str(s.get("label") or sid), "action": action, "source_idx": si,
                              "heading": str(s.get("heading") or ""),
                              "bullets": [str(b) for b in (s.get("bullets") or []) if str(b).strip()],
                              "scene_hint": str(s.get("scene_hint") or ""),
                              "prompt": str(s.get("prompt") or "").strip()})
        except Exception as exc:  # noqa: BLE001  设计失败 → 回退规则版，不阻断
            valid = []
        if not valid:
            valid = build_image_plan(und, images)
            fallback = True
        else:
            fallback = False
        sr["image_plan"] = valid
        self.store.update_draft(draft_id, {"source_raw": sr})
        return {"ok": True, "plan": valid, "count": len(valid), "fallback": fallback}

    def generate_plan_slot(self, draft_id: int, slot_id: str) -> dict:
        """生成图集计划某个槽位的图(按 action 选生成器,用槽的 source_idx 为源)→ 进候选区,标 slot。"""
        from ozon_common.gen_image import (  # noqa: PLC0415
            LOCALIZE_PROMPT,
            NON_PRODUCT_RULE,
            OZON_RU_RULE,
            SCENE_PROMPT,
            WHITE_MAIN_PROMPT,
            build_infographic_prompt,
        )
        _, _, plan = self._load_image_plan(draft_id)
        slot = next((s for s in plan if s.get("slot_id") == slot_id), None)
        if slot is None:
            raise ValueError(f"图集计划里没有槽位 {slot_id}")
        src = int(slot.get("source_idx") or 0)
        action = slot.get("action")
        designed = str(slot.get("prompt") or "").strip()
        if designed:   # 设计模型为这张图输出的整段提示词 → 直接用，强制追加去非产品+Ozon俄语硬规则(双保险)
            prompt = designed + " " + NON_PRODUCT_RULE + OZON_RU_RULE
        elif action == "white":
            prompt = WHITE_MAIN_PROMPT
        elif action == "localize":
            prompt = LOCALIZE_PROMPT
        elif action == "scene":
            hint = str(slot.get("scene_hint") or slot.get("heading") or "").strip()
            prompt = SCENE_PROMPT + (f" Scene context: {hint}" if hint else "")
        elif action == "infographic":
            prompt = build_infographic_prompt(role=str(slot.get("role") or ""),
                                              heading=str(slot.get("heading") or ""),
                                              bullets=slot.get("bullets") or [])
        else:
            raise ValueError(f"未知 action {action}")
        data = self._edit_source_image(draft_id, src, prompt)
        url = self._add_candidate(draft_id, data, str(slot.get("label") or slot_id), slot=slot_id)
        return {"ok": True, "slot_id": slot_id, "candidate": url, "draft": self.store.get_draft(draft_id)}

    def apply_image_candidates(self, draft_id: int, indices: list[int] | None = None) -> dict:
        """把候选区的图加入正式图集 draft.images，清空候选区。
        indices 为空 → 应用全部候选(前端"全部应用"/一键自动都是全应用，不靠前端传索引，
        避免前端响应式滞后导致传空 → 静默不应用)。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = dict(draft.get("source_raw") or {})
        cands = list(sr.get("ai_image_candidates") or [])
        if not cands:
            raise ValueError("没有候选图可应用")
        if indices:
            picked = [cands[i] for i in indices
                      if isinstance(i, int) and 0 <= i < len(cands)]
        else:
            picked = list(cands)   # 不传索引 = 全部应用
        sel = [str(c.get("url") or "") for c in picked if str(c.get("url") or "")]
        if not sel:
            raise ValueError("未选择任何候选图")
        # 记录每张应用图的类型(白底/细节/场景/尺寸/卖点…)，供图集分类/排序/标签
        types = dict(sr.get("image_types") or {})
        for c in picked:
            u = str(c.get("url") or "")
            if u:
                types[u] = _img_type_from_label(c.get("angle") or c.get("slot") or "")
        sr["image_types"] = types
        images = list(draft.get("images") or []) + sel
        sr["ai_image_candidates"] = []   # 应用后清空候选区
        updated = self.store.update_draft(draft_id, {"images": images, "source_raw": sr})
        return {"ok": True, "draft": updated, "added": len(sel)}

    def discard_image_candidates(self, draft_id: int) -> dict:
        """清空候选区（全部丢弃）。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = dict(draft.get("source_raw") or {})
        sr["ai_image_candidates"] = []
        updated = self.store.update_draft(draft_id, {"source_raw": sr, "status": draft.get("status")})
        return {"ok": True, "draft": updated}
