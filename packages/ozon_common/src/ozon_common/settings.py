"""从 settings 字典解析 AI / OSS 配置(跨 webui 与 worker 共用)。"""

from __future__ import annotations

_KIND_ENGINE = {"text": "agnes", "multimodal": "agnes", "image": "gptimage", "video": "agnes"}


def _engine_for_platform(kind: str, platform: str, base: str) -> str:
    sig = f"{platform} {base}".lower()
    if "nvidia" in sig:
        return "nvidia"
    if "deepseek" in sig or "openai" in sig or "gptplus" in sig:
        return "openai"
    if "agnes" in sig:
        return "agnes"
    return _KIND_ENGINE.get(kind, "agnes")


def _model_for_platform(platform: str, base: str, model: str) -> str:
    value = str(model or "").strip()
    sig = f"{platform} {base}".lower()
    if "deepseek" in sig and value.startswith("deepseek-ai/"):
        return value.split("/", 1)[1]
    return value


def _ai_platforms(settings: dict) -> dict:
    out: dict = {}
    for p in settings.get("ai_platforms") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        out[name] = {"base": str(p.get("base") or p.get("api_base") or "").strip(),
                     "key": str(p.get("key") or p.get("api_key") or "").strip()}
    return out


def ai_config(settings: dict, kind: str) -> dict:
    """kind ∈ text/image/video/multimodal → {engine, base, key, model}。"""
    slot = settings.get(f"ai_{kind}") if isinstance(settings.get(f"ai_{kind}"), dict) else {}
    plat_name = str(slot.get("platform") or "").strip()
    if plat_name:
        p = _ai_platforms(settings).get(plat_name)
        if p:
            return {"engine": _engine_for_platform(kind, plat_name, p["base"]),
                    "base": p["base"], "key": p["key"],
                    "model": _model_for_platform(plat_name, p["base"], str(slot.get("model") or ""))}
    eng = str(slot.get("engine") or "").strip().lower()
    return {"engine": eng, "base": str(slot.get("api_base") or "").strip(),
            "key": str(slot.get("api_key") or "").strip(),
            "model": str(slot.get("model") or "").strip()}


def oss_config(settings: dict) -> dict:
    return {
        "endpoint": str(settings.get("oss_endpoint") or ""),
        "bucket_name": str(settings.get("oss_bucket") or ""),
        "access_key_id": str(settings.get("oss_access_key_id") or ""),
        "access_key_secret": str(settings.get("oss_access_key_secret") or ""),
        "public_base": str(settings.get("oss_public_base") or ""),
    }
