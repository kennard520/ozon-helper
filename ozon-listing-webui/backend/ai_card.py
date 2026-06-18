from __future__ import annotations
import json
from typing import Any, Callable

NO_BRAND = "Нет бренда"
# 文案请求：标题(重写优化、防降权) + 描述 + 标签
_SYS_TITLE = ("You write the Ozon listing copy in Russian. Based on the product info, output JSON "
              "{\"ozon_title\":str,\"description\":str,\"hashtags\":[str,...]}. "
              "1) ozon_title: write a FRESH, optimized Russian title (product category + key selling points). "
              "DO NOT copy the source/original title verbatim — rephrase it. "
              "**The title MUST NOT contain any brand / manufacturer / trademark name** — describe the product generically. "
              "2) description: a complete Russian description (80-250 words), fluent, based on known info, no fabrication. "
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
    "Output only JSON, no explanation.")


def _to_int0(value: object) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def build_profile(raw: dict, *, budget: int = 6000) -> str:
    raw = raw or {}
    parts = [f"Title: {raw.get('title') or ''}"]
    for p in (raw.get("params") or []):
        k = p.get("k") or p.get("name") or ""
        v = p.get("v") or p.get("value") or ""
        if k:
            parts.append(f"{k}: {v}")
    desc = str(raw.get("description_text") or "")
    parts.append("Description: " + desc)
    text = "\n".join(parts)
    return text[:budget]


def _extract_json(text: str) -> Any:
    s = str(text or "").strip()
    # 去掉 ```json ``` 围栏
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("\n") + 1:] if "\n" in s else s
    a, b = s.find("{"), s.rfind("}")
    c, d = s.find("["), s.rfind("]")
    blob = s
    if a != -1 and (c == -1 or a < c):
        blob = s[a:b + 1]
    elif c != -1:
        blob = s[c:d + 1]
    return json.loads(blob)


def assemble_attributes(card_attrs: list[dict], required: list[dict],
                        cat: int, typ: int,
                        resolve_values: Callable) -> tuple[list[dict], list[dict], list[dict]]:
    """把 AI 出的 [{id,value}] 解析成上架 [{id,values}]；返回 (attributes, mapped, unmapped)。"""
    by_id = {int(a["id"]): a for a in required if a.get("id") is not None}
    out, mapped, unmapped = [], [], []
    for ca in card_attrs or []:
        try:
            aid = int(ca.get("id"))
        except (TypeError, ValueError):
            continue
        meta = by_id.get(aid)
        if not meta:
            continue
        val = str(ca.get("value") or "").strip()
        if not val:
            continue
        if meta.get("dictionary_id"):
            texts = [t.strip() for t in val.replace("，", ",").split(",") if t.strip()]
            vals = resolve_values(cat, typ, aid, texts, bool(meta.get("is_collection")))
            if vals:
                out.append({"id": aid, "values": vals})
                mapped.append({"id": aid, "name": meta.get("name"), "value": val})
            else:
                unmapped.append({"id": aid, "name": meta.get("name"), "value": val})
        else:
            out.append({"id": aid, "values": [{"value": val}]})
            mapped.append({"id": aid, "name": meta.get("name"), "value": val})
    return out, mapped, unmapped


def clean_hashtags(tags: list, *, limit: int = 30) -> str:
    """清洗 AI 出的标签 → Ozon attr 23171 单串：每个 # 前缀、标签内空格转 _、去空去重、截 limit、空格拼接。"""
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        s = str(t or "").strip().lstrip("#").strip().replace(" ", "_")
        if not s:
            continue
        tag = "#" + s
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
        if len(out) >= limit:
            break
    return " ".join(out)


def generate_card(raw: dict, *, chat: Callable[[str, str], str],
                  category_roots: list,
                  fetch_required_attrs: Callable[[int, int], list[dict]],
                  resolve_values: Callable) -> dict:
    profile = build_profile(raw)
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
    path = nav["path"]
    return {
        "ok": True,
        "category_id": str(cat), "type_id": str(typ), "category_path": path,
        "category_fallback": category_fallback,
        "ozon_title": str(body.get("ozon_title") or ""),
        "description": str(body.get("description") or ""),
        "attributes": attributes,
        "brand_id": None, "brand_name": NO_BRAND,
        # AI 从参数表解析的毛重(g)/尺寸(cm)，找不到为 0（上层只在 >0 时回填，不覆盖已填值）
        # 注：内部列名 length_mm 等为历史名，实际存厘米
        "weight_g": _to_int0(card.get("weight_g")),
        "length_mm": _to_int0(card.get("length_cm")),
        "width_mm": _to_int0(card.get("width_cm")),
        "height_mm": _to_int0(card.get("height_cm")),
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


def deepseek_chat(settings: dict, system: str, user: str, images: list[str] | None = None) -> str:
    """真实 AI 调用，复用 ai_text 块配置（兼容旧 translate_api_base/key/model）（OpenAI 兼容）。
    images 非空 → 按 OpenAI vision 格式把 user 内容换成内容块(text + image_url)。"""
    from backend.settings_migrate import ai_config  # noqa: PLC0415
    cfg = ai_config(settings, "text")
    base, key, model = cfg["base"], cfg["key"], cfg["model"]
    model = model or "deepseek-v4-flash"
    if not base or not key:
        raise RuntimeError("未配置 AI 引擎（设置里选 remote 并填 base/key/model）")
    import json as _json  # noqa: PLC0415
    from urllib.error import HTTPError  # noqa: PLC0415
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
    try:
        with urlopen(req, timeout=180) as res:  # noqa: S310  DeepSeek 长 prompt 可能慢
            data = _json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"AI 接口报错 HTTP {exc.code}: {exc.read().decode('utf-8','replace')[:200]}")
    return (data["choices"][0]["message"]["content"] or "").strip()


_SYS_NAV = ("You navigate the Ozon category tree to classify a product. Given a numbered list of "
            "category options and the product info (text, possibly with an image), choose the SINGLE "
            "best-matching option. Output only JSON {\"index\": int} (0-based). No explanation.")


def _node_name(n: dict) -> str:
    return str(n.get("category_name") or n.get("type_name") or "").strip()


def _parse_index(text: str, n: int) -> int | None:
    try:
        v = _extract_json(text)
        idx = int(v.get("index"))
        return idx if 0 <= idx < n else None
    except Exception:  # noqa: BLE001
        return None


def navigate_category(roots: list, chat, profile: str, *, max_depth: int = 6) -> dict | None:
    """从根逐层让 AI 选，下钻到末级类型。
    返回 {description_category_id, type_id, path, category_fallback} 或 None(树空/无可选)。"""
    current = roots or []
    cur_cat = None
    path: list[str] = []
    fallback = False
    for _ in range(max_depth):
        opts = [n for n in current if not (n.get("type_id") and n.get("disabled"))]
        if not opts:
            return None
        options = [{"index": i, "name": _node_name(n)} for i, n in enumerate(opts)]
        user = ("Options (pick the best matching category index):\n"
                + json.dumps(options, ensure_ascii=False) + "\n\nProduct:\n" + (profile or ""))
        idx = _parse_index(chat(_SYS_NAV, user), len(opts))
        if idx is None:
            idx = _parse_index(chat(_SYS_NAV, user), len(opts))   # 重试一次
        if idx is None:
            idx, fallback = 0, True
        chosen = opts[idx]
        if chosen.get("type_id"):
            cat = chosen.get("description_category_id") or cur_cat
            return {"description_category_id": int(cat), "type_id": int(chosen["type_id"]),
                    "path": " / ".join([*path, _node_name(chosen)]), "category_fallback": fallback}
        cur_cat = chosen.get("description_category_id") or cur_cat
        path.append(_node_name(chosen))
        current = chosen.get("children") or []
    return None
