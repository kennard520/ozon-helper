from __future__ import annotations

from typing import Protocol


class TranslationEngine(Protocol):
    name: str
    def translate(self, text: str, *, source: str = "zh", target: str = "ru") -> str: ...


class ManualEngine:
    """占位：原样返回（用户手动翻 / 或换引擎）。不伪造俄语。"""
    name = "manual"
    def translate(self, text: str, *, source: str = "zh", target: str = "ru") -> str:
        return text


# 极小内置词典（演示可插拔 + 离线可测）；真实场景用 remote 引擎。
_GLOSSARY = {
    "收纳箱": "Коробка для хранения", "收纳": "хранение", "大号": "большой",
    "纯棉": "хлопок", "家居": "для дома", "办公": "офис", "宠物": "питомец",
}


class GlossaryEngine:
    """离线词典逐词替换（不完整翻译，仅演示引擎接口 + 可单测）。"""
    name = "glossary"
    def translate(self, text: str, *, source: str = "zh", target: str = "ru") -> str:
        out = str(text or "")
        for zh, ru in sorted(_GLOSSARY.items(), key=lambda kv: -len(kv[0])):
            out = out.replace(zh, ru)
        return out


def _chat_completions_url(base: str) -> str:
    """OpenAI 兼容 chat 端点：容忍 base 带/不带 /v1，统一打 /v1/chat/completions。
    （OpenAI/DeepSeek/Agnes 都是这个路径；少 /v1 会打到网关首页被 Cloudflare 403。）"""
    b = str(base or "").rstrip("/")
    if b.endswith("/v1"):
        b = b[:-3].rstrip("/")
    return b + "/v1/chat/completions"


class RemoteEngine:
    """OpenAI 兼容 / DeepL 等远程引擎。无 key 时抛错（接口预留，后续填 key 选型）。
    settings 优先取 ai_text 块，回退到 translate_api_base / translate_api_key / translate_model。"""
    name = "remote"
    def __init__(self, settings: dict):
        from backend.settings_migrate import ai_config  # noqa: PLC0415
        cfg = ai_config(settings or {}, "text")
        self.base = cfg["base"]
        self.key = cfg["key"]
        self.model = cfg["model"]
    def translate(self, text: str, *, source: str = "zh", target: str = "ru") -> str:
        if not self.key or not self.base:
            raise RuntimeError("未配置翻译引擎 key（translate_api_base/translate_api_key）")
        src = str(text or "").strip()
        if not src:
            return ""   # 空文本不调 API，否则模型会把"请提供内容"当译文回来
        import json as _json  # noqa: PLC0415
        from urllib.error import HTTPError  # noqa: PLC0415
        from urllib.request import Request, urlopen  # noqa: PLC0415
        sys_prompt = (
            "You are a cross-border e-commerce Russian translator. Translate the Chinese product copy "
            "in the user message into Russian. Output only the translation itself: no explanation, "
            "no quotes, no follow-up questions, no extra text."
        )
        body = _json.dumps({
            "model": self.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": src},
            ],
            "temperature": 0.3,
            "stream": False,
        }).encode("utf-8")
        req = Request(_chat_completions_url(self.base), data=body,
                      headers={"Authorization": f"Bearer {self.key}",
                               "Content-Type": "application/json",
                               "User-Agent": "Mozilla/5.0"}, method="POST")
        try:
            with urlopen(req, timeout=120) as res:  # noqa: S310
                data = _json.loads(res.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise RuntimeError(f"翻译接口报错 HTTP {exc.code}: {detail}")
        return (data["choices"][0]["message"]["content"] or "").strip()


def get_engine(name: str, settings: dict) -> TranslationEngine:
    name = (name or "manual").strip().lower()
    if name == "glossary":
        return GlossaryEngine()
    if name in ("remote", "ai", "openai", "agnes"):
        return RemoteEngine(settings or {})
    return ManualEngine()
