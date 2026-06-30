"""SettingsMixin —— 状态读取 / AI 平台迁移 / 设置保存 / 店铺解析 / 可用模型列举。"""
from __future__ import annotations

from pathlib import Path

from webui.services._helpers import _models_url
from webui.settings_migrate import migrate_ai, normalize_stores

# 路径常量（与 app_service.py 保持一致）
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]          # apps/webui/
_REPO = _ROOT.parents[1]           # repo 根
AUTH_ROOT = _REPO / ".auth"
PROFILE_1688 = AUTH_ROOT / "1688_profile"

# save_settings 里用到的 utc_now_iso（来自 webui.drafts）
from webui.drafts import utc_now_iso  # noqa: E402


class SettingsMixin:
    def state(self) -> dict:
        self._migrate_ai_platforms()   # 一次性:旧 AI 配置 → 平台列表(已迁移则空转)
        settings = self.store.get_settings()
        _ai = migrate_ai(settings)

        def _ai_public(blk: dict) -> dict:
            out = {"engine": blk["engine"], "api_base": blk["api_base"],
                   "model": blk["model"], "api_key_saved": bool(blk["api_key"])}
            if "multimodal" in blk:
                out["multimodal"] = bool(blk["multimodal"])
            return out

        def _slot_public(kind: str) -> dict:
            out = _ai_public(_ai[f"ai_{kind}"])
            raw = settings.get(f"ai_{kind}") if isinstance(settings.get(f"ai_{kind}"), dict) else {}
            out["platform"] = str(raw.get("platform") or "")   # 新结构:槽引用的平台名
            if raw.get("model"):
                out["model"] = str(raw.get("model"))
            return out

        return {
            "settings": {
                "ozon_client_id": settings.get("ozon_client_id", ""),
                "ozon_api_key_saved": bool(settings.get("ozon_api_key")),
                "rub_cny": settings.get("rub_cny", ""),
                "rub_cny_at": settings.get("rub_cny_at", ""),
                # 合同货币：草稿 price 字段按 RUB 录入，发布时换算成合同币提交（默认 CNY）
                "contract_currency": settings.get("contract_currency", "CNY"),
                # 翻译引擎（功能③）：manual / glossary / remote；key 不回传，只回传是否已存
                "translate_engine": settings.get("translate_engine", "manual"),
                "translate_api_base": settings.get("translate_api_base", ""),
                "translate_model": settings.get("translate_model", ""),
                "translate_api_key_saved": bool(settings.get("translate_api_key")),
                # AI 卡片应用模式（功能③）：true=自动应用 / false=人工确认（默认）
                "ai_auto_apply": bool(settings.get("ai_auto_apply")),
                # 采集后自动发布到 Ozon：true=采集即自动发 / false=只建草稿（默认）
                "auto_publish": bool(settings.get("auto_publish")),
                # 卡片生成聊天引擎：remote=沿用翻译引擎配置(DeepSeek) / agnes=Agnes-2.0-Flash
                "ai_chat_provider": settings.get("ai_chat_provider", "remote"),
                # agnes 时是否把商品图发给模型做图片理解（标题/属性更贴图）
                "ai_card_vision": bool(settings.get("ai_card_vision")),
                # Agnes AI（聊天/生图/生视频共用一个 key）；key 不回传，只回传是否已存
                "agnes_api_base": settings.get("agnes_api_base", ""),
                "agnes_api_key_saved": bool(settings.get("agnes_api_key")),
                "agnes_chat_model": settings.get("agnes_chat_model", ""),
                "agnes_image_model": settings.get("agnes_image_model", ""),
                "agnes_video_model": settings.get("agnes_video_model", ""),
                "ozon_stores": [
                    {"name": st["name"], "client_id": st["client_id"],
                     "is_default": st["is_default"], "api_key_saved": bool(st["api_key"])}
                    for st in normalize_stores(settings)
                ],
                "last_publish_store": settings.get("last_publish_store", ""),
                "oss_endpoint": settings.get("oss_endpoint", ""),
                "oss_bucket": settings.get("oss_bucket", ""),
                "oss_access_key_id": settings.get("oss_access_key_id", ""),
                "oss_public_base": settings.get("oss_public_base", ""),
                "oss_access_key_secret_saved": bool(settings.get("oss_access_key_secret")),
                "ai_text": _slot_public("text"),
                "ai_image": _slot_public("image"),
                "ai_video": _slot_public("video"),
                "ai_multimodal": _slot_public("multimodal"),
                # 平台列表(只地址+Key，配一次多用途复用)；key 不回传，只回 key_saved
                "ai_platforms": [
                    {"name": str(p.get("name") or ""),
                     "base": str(p.get("base") or p.get("api_base") or ""),
                     "key_saved": bool(p.get("key") or p.get("api_key"))}
                    for p in (settings.get("ai_platforms") or [])
                    if isinstance(p, dict) and str(p.get("name") or "").strip()
                ],
                "translate_mode": _ai["translate_mode"],
            },
            "paths": {
                "db": str(self.store.path),
                "auth_root": str(AUTH_ROOT),
                "profile_1688": str(PROFILE_1688),
            },
            "status": {
                "ozon_api": "connected" if settings.get("ozon_client_id") and settings.get("ozon_api_key") else "not_configured",
                "profile_1688": "present" if PROFILE_1688.exists() else "not_created",
            },
        }

    def _migrate_ai_platforms(self) -> None:
        """一次性迁移：旧 ai_text/ai_image/... 的 {engine,api_base,api_key} → ai_platforms(地址+Key)
        + 槽改成引用平台名。已有 ai_platforms 则跳过。保留各槽 model + ai_text.multimodal。"""
        s = self.store.get_settings()
        if s.get("ai_platforms"):
            return
        olds = {}
        for kind in ("text", "multimodal", "image", "video"):
            slot = s.get(f"ai_{kind}")
            if (isinstance(slot, dict) and str(slot.get("api_base") or "").strip()
                    and not str(slot.get("platform") or "").strip()):
                olds[kind] = slot
        if not olds:
            return

        def _name(base: str, idx: int) -> str:
            h = base.lower()
            if "agnes" in h:
                return "Agnes"
            if "gptplus5" in h or "gptplus" in h:
                return "GPTPlus5"
            if "openai" in h:
                return "OpenAI"
            if "deepseek" in h:
                return "DeepSeek"
            return f"平台{idx + 1}"

        platforms: list[dict] = []
        sig_to_name: dict = {}
        new_slots: dict = {}
        for kind, slot in olds.items():
            base = str(slot.get("api_base") or "").strip()
            key = str(slot.get("api_key") or "").strip()
            sig = (base, key)
            if sig not in sig_to_name:
                nm = _name(base, len(platforms))
                while any(p["name"] == nm for p in platforms):
                    nm += "2"
                sig_to_name[sig] = nm
                platforms.append({"name": nm, "base": base, "key": key})
            blk = {"platform": sig_to_name[sig], "model": str(slot.get("model") or "").strip()}
            if kind == "text":
                blk["multimodal"] = bool(slot.get("multimodal"))
            new_slots[f"ai_{kind}"] = blk
        self.store.save_settings({"ai_platforms": platforms, **new_slots})

    @staticmethod
    def _clean_secret(value: object) -> str:
        # 去掉粘贴时常带进来的反引号/引号/空白（曾导致 Invalid Api-Key）
        return str(value or "").strip().strip("`'\"").strip()

    def save_settings(self, payload: dict) -> dict:
        allowed: dict = {}
        if "ozon_client_id" in payload:
            allowed["ozon_client_id"] = self._clean_secret(payload.get("ozon_client_id"))
        if payload.get("contract_currency"):
            allowed["contract_currency"] = str(payload["contract_currency"]).strip().upper()
        if payload.get("ozon_api_key"):
            allowed["ozon_api_key"] = self._clean_secret(payload["ozon_api_key"])
        # 翻译引擎（功能③）：引擎名 / API base / model 非空才存；key 走 _clean_secret 且非空才存
        if payload.get("translate_engine"):
            allowed["translate_engine"] = str(payload["translate_engine"]).strip().lower()
        if payload.get("translate_api_base"):
            allowed["translate_api_base"] = str(payload["translate_api_base"]).strip()
        if payload.get("translate_model"):
            allowed["translate_model"] = str(payload["translate_model"]).strip()
        if payload.get("translate_api_key"):
            allowed["translate_api_key"] = self._clean_secret(payload["translate_api_key"])
        # AI 卡片自动应用开关：False 是有意义的值，用 is not None 判断（不能 falsy 判断，否则关不掉）
        if payload.get("ai_auto_apply") is not None:
            allowed["ai_auto_apply"] = bool(payload["ai_auto_apply"])
        # 采集后自动发布开关：False 是有意义的值，用 is not None 判断（不能 falsy 判断，否则关不掉）
        if payload.get("auto_publish") is not None:
            allowed["auto_publish"] = bool(payload["auto_publish"])
        # Agnes AI：provider/base/model 非空才存（空字段不覆盖已存值）；key 走 _clean_secret
        if payload.get("ai_chat_provider"):
            allowed["ai_chat_provider"] = str(payload["ai_chat_provider"]).strip().lower()
        if payload.get("ai_card_vision") is not None:
            allowed["ai_card_vision"] = bool(payload["ai_card_vision"])
        if payload.get("agnes_api_base"):
            allowed["agnes_api_base"] = str(payload["agnes_api_base"]).strip()
        if payload.get("agnes_api_key"):
            allowed["agnes_api_key"] = self._clean_secret(payload["agnes_api_key"])
        for k in ("agnes_chat_model", "agnes_image_model", "agnes_video_model"):
            if payload.get(k):
                allowed[k] = str(payload[k]).strip()
        # 汇率：随时间戳一起持久化（CLAUDE.md 硬规矩，不存无日期汇率）
        if payload.get("rub_cny") not in (None, ""):
            try:
                allowed["rub_cny"] = float(payload["rub_cny"])
                allowed["rub_cny_at"] = utc_now_iso()
            except (TypeError, ValueError):
                pass
        if payload.get("ozon_stores") is not None:
            from webui.settings_migrate import mirror_of, normalize_stores  # noqa: PLC0415
            prev = {str(st.get("client_id")): str(st.get("api_key") or "")
                    for st in (self.store.get_settings().get("ozon_stores") or [])}
            incoming = []
            for st in payload["ozon_stores"]:
                cid = self._clean_secret(st.get("client_id"))
                name = str(st.get("name") or "").strip()
                key = self._clean_secret(st.get("api_key")) or prev.get(cid, "")
                if cid and name:
                    incoming.append({"name": name, "client_id": cid, "api_key": key,
                                     "is_default": bool(st.get("is_default"))})
            stores = normalize_stores({"ozon_stores": incoming})
            # 店铺配额：非 admin 按 max_stores 限制店铺数（admin 豁免）。后端强制。
            from webui.store import current_user_id  # noqa: PLC0415
            actor = self.store.get_user_by_id(current_user_id.get())
            if actor and actor.get("role") != "admin":
                limit = int(actor.get("max_stores") or 1)
                if len(stores) > limit:
                    raise ValueError(f"最多 {limit} 个店铺，请联系管理员调整上限")
            allowed["ozon_stores"] = stores
            mcid, mkey = mirror_of(stores)
            allowed["ozon_client_id"] = mcid
            allowed["ozon_api_key"] = mkey
        if payload.get("translate_mode"):
            allowed["translate_mode"] = str(payload["translate_mode"]).strip().lower()
        # 平台列表：地址+Key 配一次，多用途复用。key 留空 = 沿用同名平台已存 key。
        if payload.get("ai_platforms") is not None:
            prev_plats = {str(p.get("name") or ""): str(p.get("key") or p.get("api_key") or "")
                          for p in (self.store.get_settings().get("ai_platforms") or [])
                          if isinstance(p, dict)}
            out_plats = []
            for p in payload["ai_platforms"]:
                if not isinstance(p, dict):
                    continue
                name = str(p.get("name") or "").strip()
                if not name:
                    continue
                key = self._clean_secret(p.get("key") or p.get("api_key")) or prev_plats.get(name, "")
                out_plats.append({"name": name,
                                  "base": str(p.get("base") or p.get("api_base") or "").strip(),
                                  "key": key})
            allowed["ai_platforms"] = out_plats
        for kind in ("ai_text", "ai_image", "ai_video", "ai_multimodal"):
            blk = payload.get(kind)
            if isinstance(blk, dict):
                prev_blk = self.store.get_settings().get(kind) or {}
                prev_key = str(prev_blk.get("api_key") or "") if isinstance(prev_blk, dict) else ""
                blk_out = {
                    "engine": str(blk.get("engine") or "").strip().lower(),
                    "api_base": str(blk.get("api_base") or "").strip(),
                    "api_key": self._clean_secret(blk.get("api_key")) or prev_key,
                    "model": str(blk.get("model") or "").strip(),
                    "platform": str(blk.get("platform") or "").strip(),   # 新:槽引用的平台名
                }
                if kind == "ai_text":
                    blk_out["multimodal"] = bool(blk.get("multimodal"))
                allowed[kind] = blk_out
        for k in ("oss_endpoint", "oss_bucket", "oss_access_key_id", "oss_public_base"):
            if payload.get(k) is not None:
                allowed[k] = str(payload[k]).strip()
        if payload.get("oss_access_key_secret"):
            allowed["oss_access_key_secret"] = self._clean_secret(payload["oss_access_key_secret"])
        if payload.get("last_publish_store") is not None:
            allowed["last_publish_store"] = str(payload["last_publish_store"]).strip()
        if allowed:
            self.store.save_settings(allowed)
        return self.state()

    def _settings_for_store(self, store_client_id: str | None) -> dict:
        """返回目标店的 settings：client_id/api_key 替换成目标店，其余全局字段（rub_cny/
        contract_currency 等）不变。空或 == 主店 → 主店；额外店在 ozon_stores 里按 client_id
        匹配；找不到抛 ValueError。"""
        s = self.store.get_settings()
        cid = str(store_client_id or "").strip()
        if not cid or cid == str(s.get("ozon_client_id") or "").strip():
            return s
        for st in s.get("ozon_stores") or []:
            if str(st.get("client_id") or "").strip() == cid:
                return {**s, "ozon_client_id": cid, "ozon_api_key": str(st.get("api_key") or "")}
        raise ValueError(f"目标店未配置: {cid}")

    def list_ai_models(self, kind: str = "", base: str = "", key: str = "",
                       platform: str = "") -> dict:
        """查接口可用模型(GET /v1/models，OpenAI 兼容)。来源优先级：
        ① 传了 platform(平台名) → 用该平台已存的地址+Key；② 传了 base/key → 用传的;
        ③ 都没传 → 用 kind 槽解析出的地址/Key。便于"选平台配模型"和"边配平台边试"两种。"""
        import json as _json  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415

        from webui.settings_migrate import ai_config, ai_platforms  # noqa: PLC0415
        b = str(base or "").strip()
        key2 = str(key or "").strip()
        if str(platform or "").strip():
            p = ai_platforms(self.store.get_settings()).get(str(platform).strip())
            if p:
                b = b or p["base"]
                key2 = key2 or p["key"]
        if not b and kind:
            cfg = ai_config(self.store.get_settings(),
                            kind if kind in ("text", "image", "video", "multimodal") else "text")
            b = b or str(cfg.get("base") or "")
            key2 = key2 or str(cfg.get("key") or "")
        if not b:
            return {"models": [], "error": "未配置接口地址"}
        import time as _time  # noqa: PLC0415
        url = _models_url(b)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {key2}", "User-Agent": "Mozilla/5.0"})
        data = None
        for attempt in range(3):   # SSL 瞬断/超时退避重试
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                    data = _json.loads(resp.read())
                break
            except Exception as exc:  # noqa: BLE001
                if attempt < 2:
                    _time.sleep(1.2 * (attempt + 1))
                    continue
                return {"models": [], "error": f"拉取失败(已重试): {exc}"}
        items = data.get("data") if isinstance(data, dict) else data
        models = sorted({str(m.get("id")) for m in (items or [])
                         if isinstance(m, dict) and m.get("id")})
        return {"models": models}
