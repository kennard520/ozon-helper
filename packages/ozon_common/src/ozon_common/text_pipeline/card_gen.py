"""card_gen.py — Ozon 卡片文案 + 属性生成（纯函数，零 webui.* 依赖）。

依赖：ozon_common.text_pipeline.ai_card（由另一个子代理负责写入，包含
NO_BRAND / _extract_json / navigate_category / build_profile /
assemble_attributes / clean_hashtags）。
"""
from __future__ import annotations

import json
from typing import Any, Callable

from ozon_common.text_pipeline.ai_card import (
    NO_BRAND,
    _extract_json,
    navigate_category,
    build_profile,
    assemble_attributes,
    clean_hashtags,
)

# ---------------------------------------------------------------------------
# 系统提示词常量
# ---------------------------------------------------------------------------

# 文案请求：标题(重写优化、防降权) + 描述 + 标签
_SYS_TITLE = ("You write the Ozon listing copy in Russian. Based on the product info, output JSON "
              "{\"ozon_title\":str,\"description\":str,\"hashtags\":[str,...]}. "
              "1) ozon_title: write a FRESH, optimized Russian title (product category + key selling points), "
              "**concise, at most ~150 characters** (well within Ozon's 500-char limit; no keyword stuffing, no "
              "repeated words). DO NOT copy the source/original title verbatim — rephrase it. "
              "**The title MUST NOT contain any brand / manufacturer / trademark name** — describe the product generically. "
              "2) description: a complete Russian product description (150-350 words) that combines a **PRODUCT "
              "INTRODUCTION + MARKETING copy**: first introduce what the product IS and its key facts (category, "
              "capacity/size, core features, materials, what's included), then present them as **persuasive, "
              "benefit-oriented marketing** around the product's selling points, the buyer's needs and use scenarios. "
              "Fluent and engaging, not a dry bullet list, but factually complete. Base everything on the provided "
              "product info / selling points; do NOT fabricate. Keep it STRICTLY about the product itself (appearance, "
              "category, features, specs, materials, dimensions, usage) — NO brand / manufacturer / shop names, "
              "NO guarantees / warranties / free-trial / money-back, NO free gifts / giveaways ('赠品'/'赠送'/'买X送Y'), "
              "NO invoices ('发票'), NO customization / made-to-order ('定制'), NO shipping or service promises, "
              "NO OEM / factory / dropshipping claims, NO price / contact / promotions. "
              "IGNORE any such seller/transaction phrases even if they appear in the source product info. "
              "3) hashtags: up to 30 Russian search hashtags. Each MUST start with '#'; a multi-word tag joins words with "
              "'_' (no spaces inside a tag). NO brand, NO parameters, NO product name — only trend/style/theme. "
              "Output only JSON, no explanation.")

# 属性请求：从类目属性清单 + 商品信息填属性 + 尺寸/毛重
_SYS_ATTRS = ("You fill Ozon product attributes in Russian. Based on the product info and the attribute list, output JSON "
              "{\"attributes\":[{\"id\":int,\"value\":str}],"
              "\"weight_g\":int,\"length_cm\":int,\"width_cm\":int,\"height_cm\":int}. "
              "attributes: fill **every** attribute in the list whose value can be inferred from the product info "
              "(translate the Chinese 1688 params into the matching Russian value, e.g. color/origin/model/material/power); "
              "fill per each attribute's hint (official description) and the format its type requires (e.g. a frequency range "
              "as '100-200', numeric types give numbers only, Аннотация = marketing description); use only what is actually "
              "present; if unknown, omit it from the array — do not fabricate. "
              "weight_g = gross weight with packaging (grams), length/width/height_cm = dimensions (cm); convert units "
              "from the params (kg→g×1000, mm→cm÷10); if not found use 0. Output only JSON, no explanation.")

# 增强版属性填充：每个属性带「kind(单选/多选/文本/数字/布尔)+选项清单」，AI 从选项里按 id 选。
_SYS_ATTRS_PICK = (
    "You fill Ozon product attributes from the product info. You get an attribute list; each item has "
    "id, name, required, kind, hint, and for option kinds an 'options' list (each option is {id,value}) "
    "and possibly max_values. Output ONLY JSON {\"attributes\":[ ... ]}, no explanation. "
    "Add one entry per attribute you can fill, shaped by its kind:\n"
    "- select_one: choose the SINGLE option whose meaning best matches the product; "
    "entry = {\"id\":attr_id,\"value_ids\":[chosen_option_id]}. Choose ONLY from the given options (by their id); "
    "if none truly matches, skip this attribute.\n"
    "- select_many: choose ALL and ONLY the options that genuinely apply to THIS product, at most max_values; "
    "entry = {\"id\":attr_id,\"value_ids\":[option_id, ...]}. ONLY ids from the given options. "
    "Match strictly to the product's real facts — do NOT add options the product is not for (e.g. don't add "
    "'for rodents' if it serves only cats and dogs), and do NOT miss ones that clearly apply.\n"
    "- text_ru: entry = {\"id\":attr_id,\"value\":\"<value in RUSSIAN>\"}. The product info may be in Chinese — "
    "you MUST write the value in fluent Russian; NEVER output Chinese characters.\n"
    "- number: entry = {\"id\":attr_id,\"value\":\"<digits only, no unit>\"}.\n"
    "- boolean: entry = {\"id\":attr_id,\"value\":\"true\"} or {\"id\":attr_id,\"value\":\"false\"}.\n"
    "Fill EVERY required attribute if the product info allows, plus as many others as the info supports. "
    "Attributes flagged is_aspect are the variant-distinguishing ones (color/size/volume/material/type). When the "
    "product info gives a single variant's distinguishing spec, you MUST decompose it and fill those is_aspect "
    "attributes to match exactly THIS variant (so variants merge into one Ozon card and stay selectable). "
    "Follow each attribute's hint. Use only facts present in the product info; never fabricate. Output only JSON.")

# 兜底翻译：属性自由文本若 AI 照抄了中文(没遵守 text_ru 必须俄语)，批量翻成俄语再填
_SYS_TRANSLATE_RU = (
    "Translate each product attribute value into fluent, natural Russian. Input is JSON "
    "[{\"id\":int,\"name\":str,\"value_zh\":str}] (name is the Russian attribute name for context). "
    "Output ONLY JSON {\"items\":[{\"id\":int,\"value_ru\":str}]}. value_ru MUST be Russian, NEVER Chinese. "
    "Preserve separators like '; ' between items. Translate every input id.")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _to_int0(value: object) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------

def generate_card(raw: dict, *, chat: Callable[[str, str], str],
                  category_roots: list,
                  fetch_required_attrs: Callable[[int, int], list[dict]],
                  resolve_values: Callable, understanding: dict | None = None) -> dict:
    profile = build_profile(raw, understanding=understanding)
    nav = navigate_category(category_roots, chat, profile)
    if not nav:
        return {"ok": False, "error": "类目下钻失败（类目树为空或无可选项）"}
    cat, typ = nav["description_category_id"], nav["type_id"]
    category_fallback = nav["category_fallback"]
    all_attrs = [a for a in (fetch_required_attrs(cat, typ) or []) if int(a.get("id") or 0) != 85]
    required = [a for a in all_attrs if a.get("is_required")]
    # 把【全部】属性(必填+可选)都给 AI，让它从源数据尽量填满"特征"，未知留空。
    # 必填排前并标记，限 80 条控 token（必填优先保留）。
    ordered = required + [a for a in all_attrs if not a.get("is_required")]
    brief = [{"id": a.get("id"), "name": a.get("name"), "required": bool(a.get("is_required")),
              "dictionary": bool(a.get("dictionary_id")), "collection": bool(a.get("is_collection")),
              "type": a.get("type") or "",                       # 值类型(String/Decimal/Boolean…)
              "hint": str(a.get("description") or "")[:120]}      # Ozon 官方填写说明/格式提示
             for a in ordered[:80]]
    # 请求②：文案（标题 + 描述 + 标签）
    try:
        body = _extract_json(chat(_SYS_TITLE, "Product:\n" + profile))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"AI 文案输出解析失败: {exc}", "category_id": str(cat), "type_id": str(typ)}
    # 请求③：属性（含尺寸/毛重）
    try:
        card = _extract_json(chat(_SYS_ATTRS,
            "Attribute list (required=true must be filled; fill as many as possible, leave unknown blank):\n"
            + json.dumps(brief, ensure_ascii=False) + "\n\nProduct:\n" + profile))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"AI 属性输出解析失败: {exc}", "category_id": str(cat), "type_id": str(typ)}
    # 用全部属性做解析底表(可选属性 AI 填了也能组装)，但 unmapped 只报"必填里没填上的"
    attributes, mapped, _ = assemble_attributes(
        card.get("attributes") or [], all_attrs, cat, typ, resolve_values)
    # 标签 → attr 23171（单串空格分隔，进 mapped 供待确认草案展示/编辑）
    tags_value = clean_hashtags(body.get("hashtags"))
    if tags_value:
        attributes.append({"id": 23171, "values": [{"value": tags_value}]})
        mapped.append({"id": 23171, "name": "#Хештеги", "value": tags_value})
    filled_ids = {a["id"] for a in attributes}
    unmapped = [{"id": a.get("id"), "name": a.get("name")}
                for a in required if int(a.get("id") or 0) not in filled_ids]
    path = " / ".join(nav["path"])   # nav["path"] 是层级名列表 → 存成字符串(与 recognize_category 一致)
    return {
        "ok": True,
        "category_id": str(cat), "type_id": str(typ), "category_path": path,
        "category_fallback": category_fallback,
        "ozon_title": str(body.get("ozon_title") or ""),
        "description": str(body.get("description") or ""),
        "attributes": attributes,
        "brand_id": None, "brand_name": NO_BRAND,
        # AI 从参数表解析的毛重(g)/尺寸(cm)，找不到为 0（上层只在 >0 时回填，不覆盖已填值）
        # 尺寸列统一存「毫米」→ AI 给的厘米 ×10 转毫米
        "weight_g": _to_int0(card.get("weight_g")),
        "length_mm": _to_int0(card.get("length_cm")) * 10,
        "width_mm": _to_int0(card.get("width_cm")) * 10,
        "height_mm": _to_int0(card.get("height_cm")) * 10,
        "mapped": mapped, "unmapped": unmapped,
    }


def build_proposal_draft(proposal: dict, report: dict,
                         required: list[dict], optional: list[dict],
                         *, ts: str) -> dict:
    """把 generate_card 的 proposal+report + 类目必填/可选属性组装成待确认草案 JSON。
    - fields: 标量字段(标题/描述/类目/品牌/重量尺寸)
    - attributes: AI 已填(source=ai) + 类目要求但 AI 没填(source=missing)，品牌 85 排除
    - annotation/keywords: 取 report
    """
    proposal = proposal or {}
    report = report or {}
    fields = {
        "ozon_title": proposal.get("ozon_title") or "",
        "description": proposal.get("description") or "",
        "category_id": str(proposal.get("category_id") or ""),
        "type_id": str(proposal.get("type_id") or ""),
        "category_path": report.get("category_path") or "",
        "brand_name": proposal.get("brand_name") or "",
    }
    if proposal.get("brand_id"):
        fields["brand_id"] = int(proposal["brand_id"])
    for k in ("weight_g", "length_mm", "width_mm", "height_mm"):
        if proposal.get(k):
            fields[k] = int(proposal[k])

    attributes: list[dict] = []
    filled_ids: set[int] = set()
    for m in (report.get("mapped") or []):
        try:
            aid = int(m.get("id"))
        except (TypeError, ValueError):
            continue
        if aid == 85:
            continue
        attributes.append({"id": aid, "name": m.get("name") or f"属性{aid}",
                           "value": str(m.get("value") or ""), "source": "ai"})
        filled_ids.add(aid)

    for grp, is_req in ((required or [], True), (optional or [], False)):
        for a in grp:
            try:
                aid = int(a.get("id"))
            except (TypeError, ValueError):
                continue
            if aid == 85 or aid in filled_ids:
                continue
            attributes.append({"id": aid, "name": a.get("name") or f"属性{aid}",
                               "value": "", "source": "missing", "required": is_req})
            filled_ids.add(aid)

    annotation = ""
    for m in (report.get("mapped") or []):
        if int(m.get("id") or 0) == 4191 or "Аннотация" in str(m.get("name") or ""):
            annotation = str(m.get("value") or "")
            break

    return {
        "ts": ts,
        "fields": fields,
        "attributes": attributes,
        "annotation": annotation,
        "keywords": list(report.get("keywords") or []),
    }


# ---------------------------------------------------------------------------
# TODO(controller): 待 ozon_common.text_pipeline.ai_card 由另一个子代理写入后，
# 在 apps/webui/src/webui/ai_card.py 里把以下符号的原始定义删掉，
# 改成 re-export：
#   from ozon_common.text_pipeline.card_gen import (  # noqa: F401
#       _SYS_TITLE, _SYS_ATTRS, _SYS_ATTRS_PICK, _SYS_TRANSLATE_RU,
#       _to_int0, generate_card, build_proposal_draft,
#   )
# ---------------------------------------------------------------------------
