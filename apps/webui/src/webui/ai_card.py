from __future__ import annotations


from ozon_common.text_pipeline.ai_card import (  # noqa: F401
    NO_BRAND,
    _SYS_NAV,
    _extract_json,
    _node_name,
    _parse_index,
    category_override_from_profile,
    navigate_category,
    build_profile,
    assemble_attributes,
    clean_hashtags,
)
from ozon_common.text_pipeline.card_gen import (  # noqa: F401
    _SYS_TITLE,
    _SYS_ATTRS,
    _SYS_ATTRS_PICK,
    _SYS_TRANSLATE_RU,
    _to_int0,
    generate_card,
    build_proposal_draft,
)
# _SYS_TITLE / _SYS_ATTRS / _SYS_ATTRS_PICK / _SYS_TRANSLATE_RU / _to_int0 / generate_card / build_proposal_draft
# 已下沉到 ozon_common.text_pipeline.card_gen，通过上方 re-export 引入。
# 以下保留出图/翻译/deepseek_chat 等 webui 专属功能。

# 图集设计：全模态/文本 LLM 当"美术总监"，据看图理解+源图清单设计一整套 Ozon 商品图(目标张数在 user 里给)
_SYS_IMG_PLAN = (
    "You are an e-commerce art director planning the image set for an Ozon (Russia) product card. "
    "DESIGN FOR THE RUSSIAN OZON SHOPPER: they respond to information-dense, benefit-driven cards — bold legible "
    "Russian headlines, big numbers, key specs and simple icons; clear trust/quality cues (warranty, material, "
    "what's in the box / комплектация); bright, clean, high-contrast and practical visuals; realistic everyday "
    "Russian-home context for lifestyle shots; avoid gaudy colors, fake luxury and clutter. "
    "You are given the product understanding (type, selling points, use scenes, specs, materials, what's included) "
    "and an inventory of available source photos (each with an index and a role tag). Design the number of images "
    "requested (Target image count in the user message) that together make a strong, Ozon-compliant card. "
    "Output ONLY JSON {\"slots\":[{\"slot_id\":str,\"role\":str,\"label\":str,\"action\":str,"
    "\"source_idx\":int,\"heading\":str,\"bullets\":[str],\"scene_hint\":str,\"prompt\":str}]}. "
    "action is one of: \n"
    "- \"white\": clean WHITE-background main product shot. Exactly ONE, placed first; source_idx = the best overall product photo.\n"
    "- \"localize\": reuse a source photo as-is but translate any Chinese on it to Russian (good for detail/feature shots "
    "that already look fine); source_idx = that photo.\n"
    "- \"scene\": a lifestyle/usage photo of the product in a real context; put the concrete scene (where/how used, from "
    "the use scenes) in English in \"scene_hint\"; source_idx = the overall photo.\n"
    "- \"infographic\": product photo + overlaid RUSSIAN text; for selling-point cards and a size/spec card; give a short "
    "Russian \"heading\" and 1-3 short Russian \"bullets\" (translated from the selling points / specs); source_idx = a relevant photo.\n"
    "CRITICAL — for EVERY slot also write \"prompt\": a complete, self-contained ENGLISH image-generation prompt for the "
    "image model, describing exactly what this single image should look like (composition, framing, background, which "
    "product detail/angle to highlight, lighting/mood). The image model receives the chosen source photo as the reference "
    "— so the prompt MUST instruct it to keep the product visually IDENTICAL to that reference (same shape, color, "
    "material, proportions, details). For any text that should appear ON the image (infographic heading/bullets, a "
    "translated label, etc.), spell it out IN FLUENT RUSSIAN inside the prompt — this is the Ozon marketplace in Russia, "
    "so the image must contain ZERO Chinese characters (translate or remove any Chinese on the product/packaging). "
    "STRICT — headings/bullets/prompts must describe ONLY the product (features, specs, materials, dimensions, usage). "
    "NEVER put free gifts / giveaways ('赠品'/'赠送'/buy-X-get-Y), invoices ('发票'), customization ('定制'), shipping, "
    "warranty, brand/shop names, price or any seller/transaction terms on the images — IGNORE such phrases even if they "
    "appear in the product info or selling points. "
    "Compose a balanced set: 1 white main, 1-2 detail(localize), 1-2 scene, the rest infographic cards covering the key "
    "selling points + a size/容量/重量 spec card. All on-image text MUST be fluent Russian. source_idx MUST be a valid index "
    "from the given inventory. label is a short Chinese tag for the UI. Output only JSON, no explanation.")
# Image prompts: for manually pasting into ChatGPT Pro to generate images. {n} is formatted to the selling-point count at call time.
_SYS_IMG_PROMPTS = (
    "You are a cross-border e-commerce visual planner generating «AI image-generation prompts» for an Ozon (Russia) "
    "product, to be pasted manually into ChatGPT. Based on the product info, output JSON "
    "{{\"main\": str, \"selling_points\": [str, ...]}}. Requirements:\n"
    "1) main = the main-image prompt: e-commerce hero style, clean/light background, product centered and dominant in "
    "the frame, crisp highlights, professional studio quality; describe the scene/composition/lighting/material texture "
    "in English.\n"
    "2) selling_points = exactly {n} selling-point image prompts, each focused on a different selling point "
    "(material/use/size detail/usage scene/packaging, etc.), describe the image in English, and explicitly give the "
    "**Russian text** to overlay on that image (inside the prompt, e.g. add Russian caption \"...\").\n"
    "3) Any text on the images must be in Russian — no Chinese/English text.\n"
    "4) Use only features actually present in the product info; do not fabricate functions or appearance the product lacks.\n"
    "5) **Every prompt (the main image and all selling-point images) must end by specifying: vertical 3:4 aspect ratio, "
    "portrait 1080x1440, high resolution, ultra-detailed, sharp focus, professional studio quality**.\n"
    "6) **Every prompt MUST instruct to show ONLY the product and product-relevant content, and to NOT include any "
    "brand / manufacturer / shop / store names or logos, guarantees / warranties / free-trial / money-back, gift or "
    "coupon offers, shipping or service promises (free delivery, door-to-door), OEM / ODM / factory / dropshipping "
    "claims, promotions / discounts / 'hot sale' / 'best seller' badges, awards, ratings, sales counts, price, "
    "contact info, phone, QR codes, links or watermarks. Keep only the product's appearance, features, specs, "
    "materials, dimensions and usage.**\n"
    "Output only JSON, no explanation.")


def build_image_prompt_input(draft: dict) -> str:
    """把草稿拼成给 AI 出图提示词的商品画像。
    优先用已本地化的俄语内容(ozon_title/description/可读属性)——更贴 Ozon 语境；
    都没有再回退 source_raw(走 build_profile) 或 source_title。"""
    draft = draft or {}
    parts: list[str] = []
    title = str(draft.get("ozon_title") or "").strip()
    desc = str(draft.get("description") or "").strip()
    if title:
        parts.append(f"Title: {title}")
    # 可读属性：采集格式 {name,value}（上架格式 {id,values} 无可读名，跳过）
    for a in (draft.get("attributes") or []):
        if isinstance(a, dict) and a.get("name") and a.get("value") and "values" not in a:
            parts.append(f"{a['name']}: {a['value']}")
    if desc:
        parts.append("Description: " + desc)
    if parts:
        return "\n".join(parts)[:6000]
    # 回退：source_raw → source_title
    raw = draft.get("source_raw") or {}
    if raw:
        return build_profile(raw)
    return f"Title: {draft.get('source_title') or ''}"[:6000]


def parse_image_prompts(text: str, n_points: int) -> dict:
    """解析 AI 返回的图片提示词 JSON → {main:str, selling_points:[str...]}。
    容错：坏 JSON 不崩(返回空)、卖点不足补空串、超出截断到 n_points。"""
    n = max(1, int(n_points or 1))
    try:
        d = _extract_json(text)
    except Exception:  # noqa: BLE001
        d = {}
    if not isinstance(d, dict):
        d = {}
    main = str(d.get("main") or "").strip()
    sp_raw = d.get("selling_points")
    pts = [str(x).strip() for x in sp_raw if str(x).strip()] if isinstance(sp_raw, list) else []
    pts = pts[:n] + [""] * max(0, n - len(pts))   # 截断到 n / 不足补空
    return {"main": main, "selling_points": pts}


def deepseek_chat(settings: dict, system: str, user: str, images: list[str] | None = None,
                  kind: str = "text") -> str:
    """真实 AI 调用（OpenAI 兼容）。kind 指定用哪套配置块（text/multimodal/...），默认 text。
    images 非空 → 按 OpenAI vision 格式把 user 内容换成内容块(text + image_url)。"""
    from webui.settings_migrate import ai_config  # noqa: PLC0415
    cfg = ai_config(settings, kind)
    base, key, model = cfg["base"], cfg["key"], cfg["model"]
    model = model or "deepseek-v4-flash"
    if not base or not key:
        raise RuntimeError("未配置 AI 引擎（设置里选 remote 并填 base/key/model）")
    import json as _json  # noqa: PLC0415
    import time as _time  # noqa: PLC0415
    from urllib.error import HTTPError, URLError  # noqa: PLC0415
    from urllib.request import Request, urlopen  # noqa: PLC0415
    if images:
        content: object = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in images]
    else:
        content = user
    body = _json.dumps({"model": model, "temperature": 0.3, "stream": False,
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": content}]}).encode("utf-8")
    req = Request(base.rstrip("/") + "/chat/completions", data=body,
                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                  method="POST")
    # 网关偶发 429/5xx 或超时 → 退避重试(0.8s,2s,4s)；非可重试错或重试用尽才抛
    _RETRYABLE = {429, 500, 502, 503, 504}
    last_exc = None
    for attempt in range(4):
        try:
            with urlopen(req, timeout=180) as res:  # noqa: S310  长 prompt/视觉可能慢
                data = _json.loads(res.read().decode("utf-8"))
            return (data["choices"][0]["message"]["content"] or "").strip()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            if exc.code in _RETRYABLE and attempt < 3:
                last_exc = RuntimeError(f"AI 接口报错 HTTP {exc.code}: {detail}")
                _time.sleep([0.8, 2, 4][attempt])
                continue
            raise RuntimeError(f"AI 接口报错 HTTP {exc.code}: {detail}")
        except (URLError, TimeoutError, OSError) as exc:  # 连接/超时类同样退避重试
            if attempt < 3:
                last_exc = exc
                _time.sleep([0.8, 2, 4][attempt])
                continue
            raise RuntimeError(f"AI 接口连接失败：{exc}")
    raise last_exc or RuntimeError("AI 接口重试用尽")
