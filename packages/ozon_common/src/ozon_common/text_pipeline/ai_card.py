"""category 下钻 + 商品卡片纯逻辑函数（注入式，零框架依赖）。

下沉自 apps/webui/src/webui/ai_card.py；webui/ai_card.py 保留为兼容薄层 re-export。
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

NO_BRAND = "Нет бренда"

_SYS_NAV = ("You navigate the Ozon category tree to classify a product. Given a numbered list of "
            "category options and the product info (text, possibly with an image), choose the SINGLE "
            "best-matching option. Judge by the product's PRIMARY purpose - what it fundamentally is "
            "and does - not by secondary features. Extra electronics (camera, app, Wi-Fi, voice, "
            "night-vision) do NOT turn an item into a 'gadget/electronics' category if its core "
            "function belongs elsewhere: e.g. an automatic pet feeder with a camera is still a feeder "
            "(classify under feeding/tableware), NOT under pet gadgets. Output only JSON "
            "{\"index\": int} (0-based). No explanation.")

_SYS_NAV_LEAF = ("You classify an Ozon product by choosing the SINGLE best final leaf category "
                 "from a numbered candidate list. Each option is a full category path ending in "
                 "the final product type. Judge by the product's PRIMARY purpose - what it "
                 "fundamentally is and does - not by secondary features, marketing claims, or "
                 "included accessories. Output only JSON {\"index\": int} (0-based). No explanation.")


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


def _node_name(n: dict) -> str:
    return str(n.get("category_name") or n.get("type_name") or "").strip()


def _parse_index(text: str, n: int) -> int | None:
    try:
        v = _extract_json(text)
        idx = int(v.get("index"))
        return idx if 0 <= idx < n else None
    except Exception:  # noqa: BLE001
        return None


def _flatten_type_options(roots: list) -> list[dict]:
    out: list[dict] = []

    def walk(nodes: list, path: list[str], cur_cat: int | None = None) -> None:
        for node in nodes or []:
            name = _node_name(node)
            next_path = [*path, name] if name else path
            cat = node.get("description_category_id") or cur_cat
            if node.get("type_id"):
                if not node.get("disabled") and cat:
                    out.append({
                        "description_category_id": int(cat),
                        "type_id": int(node["type_id"]),
                        "path": next_path,
                    })
                continue
            walk(node.get("children") or [], next_path, cat)

    walk(roots or [], [])
    return out


def _category_candidate_score(option: dict, profile: str) -> int:
    text = str(profile or "").lower()
    path = " / ".join(str(x) for x in option.get("path") or []).lower()
    if not text or not path:
        return 0
    score = 0
    for token in re.findall(r"[a-zа-яё0-9]+|[\u4e00-\u9fff]{2,}", text):
        if len(token) < 2:
            continue
        if token in path:
            score += min(len(token), 12)
    for name in option.get("path") or []:
        name = str(name).strip().lower()
        if len(name) >= 2 and name in text:
            score += min(len(name) * 3, 30)
    return score


def navigate_category_once(roots: list, chat, profile: str, *, candidate_limit: int = 240) -> dict | None:
    """Pick the final type with a single AI call from locally shortlisted leaf categories."""
    leaves = _flatten_type_options(roots)
    if not leaves:
        return None
    scored = [(_category_candidate_score(opt, profile), i, opt) for i, opt in enumerate(leaves)]
    best_score = max(score for score, _, _ in scored)
    if len(leaves) > candidate_limit and best_score <= 0:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    candidates = [opt for _, _, opt in scored[:candidate_limit]]
    options = [
        {"index": i, "path": " / ".join(opt.get("path") or [])}
        for i, opt in enumerate(candidates)
    ]
    user = ("Final category candidates (pick the best matching final leaf index):\n"
            + json.dumps(options, ensure_ascii=False)
            + "\n\nProduct:\n" + (profile or ""))
    idx = _parse_index(chat(_SYS_NAV_LEAF, user), len(candidates))
    if idx is None:
        idx = _parse_index(chat(_SYS_NAV_LEAF, user), len(candidates))
    if idx is None:
        return None
    chosen = candidates[idx]
    return {
        "description_category_id": int(chosen["description_category_id"]),
        "type_id": int(chosen["type_id"]),
        "path": list(chosen.get("path") or []),
        "category_fallback": False,
        "category_one_shot": True,
    }


def _navigate_category_drilldown(roots: list, chat, profile: str, *, max_depth: int = 6) -> dict | None:
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
                    "path": [*path, _node_name(chosen)], "category_fallback": fallback}
        cur_cat = chosen.get("description_category_id") or cur_cat
        path.append(_node_name(chosen))
        current = chosen.get("children") or []
    return None


def navigate_category(roots: list, chat, profile: str, *, max_depth: int = 6) -> dict | None:
    nav = navigate_category_once(roots, chat, profile)
    if nav:
        return nav
    return _navigate_category_drilldown(roots, chat, profile, max_depth=max_depth)


def category_override_from_profile(roots: list, profile: str) -> dict | None:
    """Deterministic category overrides for high-signal product words.

    Some apparel leaves are visually/textually close for the navigator. If the
    profile explicitly says "socks" or "gloves", trust that strong product noun
    and find the matching Ozon leaf in the loaded category tree.
    """
    text = str(profile or "").lower()
    rules = [
        (("袜", "袜子", "短袜", "中筒袜", "носк", "носки", "sock", "socks"), ("袜子", "носки", "socks")),
        (("手套", "перчат", "glove", "gloves"), ("手套", "перчатки", "gloves")),
    ]
    target_names: tuple[str, ...] | None = None
    for keywords, names in rules:
        if any(k in text for k in keywords):
            target_names = tuple(n.lower() for n in names)
            break
    if not target_names:
        return None

    def _walk(nodes: list, path: list[str], cur_cat: int | None = None) -> dict | None:
        for node in nodes or []:
            n = _node_name(node)
            next_path = [*path, n] if n else path
            cat = node.get("description_category_id") or cur_cat
            node_name = n.lower()
            if node.get("type_id") and any(t == node_name or t in node_name for t in target_names):
                return {
                    "description_category_id": int(cat),
                    "type_id": int(node["type_id"]),
                    "path": next_path,
                    "category_fallback": False,
                    "category_override": True,
                }
            found = _walk(node.get("children") or [], next_path, cat)
            if found:
                return found
        return None

    return _walk(roots or [], [])


def build_profile(raw: dict, *, budget: int = 6000, understanding: dict | None = None) -> str:
    """拼商品 profile 喂文案 AI。understanding(理解层事实)非空时并入——把"看图理解"的
    品类/材质/规格/卖点/场景/包装喂给文案,让简介基于图上卖点写(解决纯文本太薄)。"""
    raw = raw or {}
    parts = [f"Title: {raw.get('title') or ''}"]
    # 兼容两种格式：1688 {name, value} 和 Ozon {id, values: [{dictionary_value_id, value}]}
    for p in (raw.get("params") or raw.get("attributes") or []):
        k = p.get("k") or p.get("name") or str(p.get("id") or "")
        v = p.get("v") or p.get("value") or ""
        # Ozon 格式：从 values 数组提取
        if not v and isinstance(p.get("values"), list):
            vals = [x.get("value", "") for x in p["values"] if x.get("value")]
            if vals:
                v = ", ".join(vals)
        if k and v:
            parts.append(f"{k}: {v}")
    desc = str(raw.get("description_text") or "")
    parts.append("Description: " + desc)
    if isinstance(understanding, dict) and understanding:
        u = understanding
        if u.get("type"):
            parts.append("Type: " + str(u["type"]))
        if u.get("material"):
            parts.append("Material: " + str(u["material"]))
        specs = u.get("specs") if isinstance(u.get("specs"), dict) else {}
        for k, v in (specs or {}).items():
            if v:
                parts.append(f"{k}: {v}")
        if u.get("points"):
            parts.append("Selling points: " + "; ".join(str(x) for x in u["points"]))
        if u.get("scenes"):
            parts.append("Use scenes: " + "; ".join(str(x) for x in u["scenes"]))
        if u.get("kit"):
            parts.append("Package: " + "; ".join(str(x) for x in u["kit"]))
    text = "\n".join(parts)
    return text[:budget]


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
    """清洗 AI 出的标签 → Ozon attr 23171 单串：每个 # 前缀、去空去重、截 limit、空格拼接。
    容错：AI 常把所有标签塞进一个字符串("#a #b #c")或用 # 直接连写("#a_#b")，
    都按 # 和空白拆成独立标签，否则会被当成一个超长标签(内部空格转 _ → "#a_#b_#c")。"""
    out: list[str] = []
    seen: set[str] = set()
    for t in tags or []:
        s0 = str(t or "").strip()
        if not s0:
            continue
        for part in s0.replace("#", " #").split():   # 每个 # 起一个新标签，再按空白切开
            s = part.lstrip("#").strip().strip("_")
            if not s:
                continue
            tag = "#" + s
            if tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
            if len(out) >= limit:
                return " ".join(out)
    return " ".join(out)
