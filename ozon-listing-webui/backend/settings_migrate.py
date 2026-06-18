"""设置规范化与旧字段迁移（纯函数，无 I/O，可单测）。"""
from __future__ import annotations


def _clean(v: object) -> str:
    return str(v or "").strip()


def normalize_stores(settings: dict) -> list[dict]:
    """把 settings 规整成统一店铺列表 [{name, client_id, api_key, is_default}]。
    - 旧主店(ozon_client_id/api_key)若不在列表里则合成一条「主店」放最前并设默认。
    - 保证非空列表恰好一个 is_default（无→第一条；多→保留第一个 True）。"""
    settings = settings or {}
    raw = settings.get("ozon_stores") or []
    stores: list[dict] = []
    seen: set[str] = set()
    for st in raw:
        cid = _clean(st.get("client_id"))
        if not cid or cid in seen:
            continue
        seen.add(cid)
        stores.append({
            "name": _clean(st.get("name")) or cid,
            "client_id": cid,
            "api_key": _clean(st.get("api_key")),
            "is_default": bool(st.get("is_default")),
        })
    main_cid = _clean(settings.get("ozon_client_id"))
    if main_cid and main_cid not in seen:
        stores.insert(0, {
            "name": "主店", "client_id": main_cid,
            "api_key": _clean(settings.get("ozon_api_key")), "is_default": True,
        })
    if not stores:
        return []
    defaults = [x for x in stores if x["is_default"]]
    if not defaults:
        stores[0]["is_default"] = True
    elif len(defaults) > 1:
        first = defaults[0]
        for x in stores:
            x["is_default"] = (x is first)
    return stores


def mirror_of(stores: list[dict]) -> tuple[str, str]:
    """返回默认店的 (client_id, api_key)；空列表→("","")。"""
    for x in stores or []:
        if x.get("is_default"):
            return (_clean(x.get("client_id")), _clean(x.get("api_key")))
    return ("", "")


def _ai_block(settings: dict, new_key: str, *, default_engine: str,
              legacy_base: str, legacy_key: str, legacy_model: str,
              legacy_engine_val: str | None = None) -> dict:
    cur = (settings or {}).get(new_key)
    if isinstance(cur, dict) and any(_clean(cur.get(k)) for k in ("engine", "api_base", "api_key", "model")):
        return {"engine": _clean(cur.get("engine")) or default_engine,
                "api_base": _clean(cur.get("api_base")), "api_key": _clean(cur.get("api_key")),
                "model": _clean(cur.get("model"))}
    return {"engine": legacy_engine_val or default_engine,
            "api_base": _clean((settings or {}).get(legacy_base)),
            "api_key": _clean((settings or {}).get(legacy_key)),
            "model": _clean((settings or {}).get(legacy_model))}


def migrate_ai(settings: dict) -> dict:
    """把旧 translate_*/agnes_*/ai_chat_provider 迁移成 ai_text/ai_image/ai_video/translate_mode。
    新结构存在则优先用新结构。"""
    settings = settings or {}
    legacy_provider = _clean(settings.get("ai_chat_provider")).lower()
    text_engine = "agnes" if legacy_provider == "agnes" else "openai"
    ai_text = _ai_block(settings, "ai_text", default_engine="openai",
                        legacy_base="translate_api_base", legacy_key="translate_api_key",
                        legacy_model="translate_model", legacy_engine_val=text_engine)
    ai_image = _ai_block(settings, "ai_image", default_engine="agnes",
                         legacy_base="agnes_api_base", legacy_key="agnes_api_key",
                         legacy_model="agnes_image_model", legacy_engine_val="agnes")
    ai_video = _ai_block(settings, "ai_video", default_engine="agnes",
                         legacy_base="agnes_api_base", legacy_key="agnes_api_key",
                         legacy_model="agnes_video_model", legacy_engine_val="agnes")
    cur_text = settings.get("ai_text") if isinstance(settings.get("ai_text"), dict) else {}
    if "multimodal" in (cur_text or {}):
        ai_text["multimodal"] = bool(cur_text.get("multimodal"))
    else:
        ai_text["multimodal"] = bool(settings.get("ai_card_vision"))
    tm = _clean(settings.get("translate_mode"))
    if not tm:
        legacy_te = _clean(settings.get("translate_engine")).lower()
        tm = legacy_te if legacy_te in ("manual", "glossary") else "ai"
    return {"ai_text": ai_text, "ai_image": ai_image, "ai_video": ai_video, "translate_mode": tm}


def ai_config(settings: dict, kind: str) -> dict:
    """解析某套 AI 配置成 {engine, base, key, model}（给引擎直接用）。kind ∈ text/image/video。"""
    block = migrate_ai(settings)[f"ai_{kind}"]
    return {"engine": block["engine"], "base": block["api_base"],
            "key": block["api_key"], "model": block["model"]}
