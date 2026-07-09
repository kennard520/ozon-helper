"""把同一 variant_group 的多个变体草稿装配成 Ozon import items（合并成一张卡）。
纯装配逻辑：字典值解析由调用方注入 resolve_dict，便于测试 + 复用。不在此发布。"""
from __future__ import annotations

import html
import re
from typing import Any, Callable

from webui.drafts import dedupe_publish_attributes, loads_json, to_ozon_import_item
from webui.services._helpers import _is_country_attr, _is_manufacturer_attr, _to_int

MODEL_NAME_ATTR_ID = 9048   # 型号名称（合并为一张商品卡片）
COLOR_DICT_ATTR_ID = 10096  # 商品颜色（字典）
COLOR_TEXT_ATTR_ID = 10097  # 颜色名称（自由文本）

# 颜色词启发：变化维度的值含这些字 → 判定为「颜色」aspect，否则当「尺寸/规格」
_COLOR_HINT = re.compile(r"色|绿|粉|蓝|白|黑|红|黄|灰|紫|橙|金|银|棕|褐|青|米黄|卡其|咖啡|香槟|藏青|墨")
_SPEC_SEP = re.compile(r"[>＞、;；/|]")   # 1688 多维度分隔符(spec_attrs 里常见 >)


def find_size_aspect_attr(category_attrs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """该类目里 is_aspect 且有字典、且不是颜色 的属性 = 尺寸/规格 aspect（如箱子 9381）。"""
    for a in category_attrs or []:
        if a.get("is_aspect") and a.get("dictionary_id") and a.get("id") not in (COLOR_DICT_ATTR_ID, COLOR_TEXT_ATTR_ID):
            return a
    return None


def _sr(draft: dict[str, Any]) -> dict[str, Any]:
    sr = draft.get("source_raw")
    if isinstance(sr, str):
        sr = loads_json(sr, {})
    return sr if isinstance(sr, dict) else {}


def _spec_values(spec_attrs: Any) -> list[str]:
    """spec_attrs(如 '哑光白&gt;可视款无304不锈钢盆') → 各维度值 ['哑光白','可视款无304不锈钢盆']。"""
    s = html.unescape(str(spec_attrs or "")).strip()
    if not s:
        return []
    return [p.strip() for p in _SPEC_SEP.split(s) if p.strip()]


def derive_group_aspects(drafts: list[dict[str, Any]]) -> dict[Any, list[dict[str, str]]]:
    """无 selected_aspects 时，从同组各变体的 spec_attrs **推导**变体维度。
    做法：各变体 spec_attrs 按分隔符拆成维度值列表，找跨组**变化**的维度位置——该位置的值即
    该变体的变体值；维度值含颜色词 → aspect_key='color'，否则 'size'。
    返回 {draft_id: [{'aspect_key','value'}, ...]}。不足 2 个变体 / 无变化维度 → {}。"""
    parsed = [(d, _spec_values(_sr(d).get("spec_attrs"))) for d in drafts]
    parsed = [(d, v) for d, v in parsed if v]
    if len(parsed) < 2:
        return {}
    ncol = min(len(v) for _, v in parsed)
    varying = [i for i in range(ncol) if len({v[i] for _, v in parsed}) > 1]
    if not varying:
        return {}
    dim_key = {i: ("color" if any(_COLOR_HINT.search(v[i]) for _, v in parsed) else "size")
               for i in varying}
    return {d.get("id"): [{"aspect_key": dim_key[i], "value": v[i]} for i in varying]
            for d, v in parsed}


def build_group_items(
    drafts: list[dict[str, Any]],
    category_attrs: list[dict[str, Any]],
    model_name: str,
    resolve_dict: Callable[[int, int, str], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """drafts: 同组变体草稿；resolve_dict(attr_id, dictionary_id, text)->{'dictionary_value_id','value'}|None。
    返回 import items 列表（每个含 9048 型号名 + 颜色/尺寸 aspect 属性）。"""
    size_attr = find_size_aspect_attr(category_attrs)
    # 采集没给 selected_aspects 时，从 spec_attrs 跨组推导(颜色/规格变化维度)
    derived = derive_group_aspects(drafts) if not any(_sr(d).get("selected_aspects") for d in drafts) else {}
    items: list[dict[str, Any]] = []
    for d in drafts:
        item = to_ozon_import_item(d)  # 校验+基础结构（会 raise ValueError 若草稿不完整）
        attrs = list(item["attributes"])
        fixed_attrs: list[dict[str, Any]] = []
        for a in category_attrs or []:
            aid = _to_int(a.get("id"))
            if not aid:
                continue
            if _is_country_attr(a):
                rv = resolve_dict(aid, int(a.get("dictionary_id") or 0), "Китай")
                if rv:
                    fixed_attrs.append({"id": aid, "values": [{
                        "dictionary_value_id": rv["dictionary_value_id"],
                        "value": rv.get("value") or "Китай",
                    }]})
            elif _is_manufacturer_attr(a):
                fixed_attrs.append({"id": aid, "values": [{"value": "zqr"}]})
        if fixed_attrs:
            fixed_ids = {a["id"] for a in fixed_attrs}
            attrs = [x for x in attrs if x.get("id") not in fixed_ids]
            attrs.extend(fixed_attrs)
        # 型号名(9048)强制 = model_name(整组发布权威合并 key，可由调用方指定)；
        # 覆盖单条构建时兜底塞的 variant_group，保证组内一致 + 尊重显式 model_name。
        attrs = [x for x in attrs if x.get("id") != MODEL_NAME_ATTR_ID]
        attrs.append({"id": MODEL_NAME_ATTR_ID, "values": [{"value": model_name}]})
        aspects = _sr(d).get("selected_aspects") or derived.get(d.get("id")) or []
        # 草稿已填好的属性 id(含有效值)——Part C(AI)已按本变体填了颜色/尺寸(已译俄+解析 value_id)的就别覆盖
        filled_ids = {int(a["id"]) for a in attrs
                      if a.get("id") is not None and a.get("values")
                      and any(str((v or {}).get("value") or (v or {}).get("dictionary_value_id") or "").strip()
                              for v in a["values"])}
        aspect_attrs: list[dict[str, Any]] = []
        for sa in aspects:
            key = str(sa.get("aspect_key") or "").lower()
            val = str(sa.get("value") or "").strip()
            if not val:
                continue
            if not key:   # 采集的结构化维度只给轴名(颜色/规格…) → 按轴名/值判颜色 vs 尺寸
                axis = str(sa.get("axis") or "")
                key = "color" if (_COLOR_HINT.search(axis) or _COLOR_HINT.search(val)) else "size"
            if key.startswith("color"):
                if COLOR_DICT_ATTR_ID in filled_ids or COLOR_TEXT_ATTR_ID in filled_ids:
                    continue   # 草稿已填颜色 → 保留(别用中文值覆盖)
                rv = resolve_dict(COLOR_DICT_ATTR_ID, 0, val)
                if rv:
                    aspect_attrs.append({"id": COLOR_DICT_ATTR_ID, "values": [{"dictionary_value_id": rv["dictionary_value_id"], "value": rv.get("value") or val}]})
                aspect_attrs.append({"id": COLOR_TEXT_ATTR_ID, "values": [{"value": val}]})
            elif size_attr:
                sid = int(size_attr["id"])
                # 多个非颜色轴(如 容量+材质)只能各落一个属性；现只有一个 size_attr → 第二个起跳过，
                # 否则同 id 重复条目会触发 Ozon ATTRIBUTE_IS_DUPLICATE。(多轴各映射独立属性是后续增强)
                if sid in filled_ids or any(int(a["id"]) == sid for a in aspect_attrs):
                    continue   # 草稿已填尺寸 / 该尺寸属性已被前一个非颜色轴占用 → 跳过
                rv = resolve_dict(sid, int(size_attr.get("dictionary_id") or 0), val)
                if rv:
                    aspect_attrs.append({"id": sid, "values": [{"dictionary_value_id": rv["dictionary_value_id"], "value": rv.get("value") or val}]})
        # 去重:草稿里可能已有同 id 的颜色/尺寸，用变体专属值覆盖，避免 ATTRIBUTE_IS_DUPLICATE
        aspect_ids = {a["id"] for a in aspect_attrs}
        attrs = [x for x in attrs if x.get("id") not in aspect_ids]
        attrs.extend(aspect_attrs)
        attrs = dedupe_publish_attributes(attrs)
        item["attributes"] = attrs
        items.append(item)
    return items
