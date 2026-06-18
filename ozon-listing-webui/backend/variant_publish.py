"""把同一 variant_group 的多个变体草稿装配成 Ozon import items（合并成一张卡）。
纯装配逻辑：字典值解析由调用方注入 resolve_dict，便于测试 + 复用。不在此发布。"""
from __future__ import annotations

from typing import Any, Callable

from backend.drafts import loads_json, to_ozon_import_item

MODEL_NAME_ATTR_ID = 9048   # 型号名称（合并为一张商品卡片）
COLOR_DICT_ATTR_ID = 10096  # 商品颜色（字典）
COLOR_TEXT_ATTR_ID = 10097  # 颜色名称（自由文本）


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


def build_group_items(
    drafts: list[dict[str, Any]],
    category_attrs: list[dict[str, Any]],
    model_name: str,
    resolve_dict: Callable[[int, int, str], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """drafts: 同组变体草稿；resolve_dict(attr_id, dictionary_id, text)->{'dictionary_value_id','value'}|None。
    返回 import items 列表（每个含 9048 型号名 + 颜色/尺寸 aspect 属性）。"""
    size_attr = find_size_aspect_attr(category_attrs)
    items: list[dict[str, Any]] = []
    for d in drafts:
        item = to_ozon_import_item(d)  # 校验+基础结构（会 raise ValueError 若草稿不完整）
        attrs = item["attributes"]
        if not any(x.get("id") == MODEL_NAME_ATTR_ID for x in attrs):
            attrs.append({"id": MODEL_NAME_ATTR_ID, "values": [{"value": model_name}]})
        for sa in _sr(d).get("selected_aspects") or []:
            key = str(sa.get("aspect_key") or "").lower()
            val = str(sa.get("value") or "").strip()
            if not val:
                continue
            if key.startswith("color"):
                rv = resolve_dict(COLOR_DICT_ATTR_ID, 0, val)
                if rv:
                    attrs.append({"id": COLOR_DICT_ATTR_ID, "values": [{"dictionary_value_id": rv["dictionary_value_id"], "value": rv.get("value") or val}]})
                attrs.append({"id": COLOR_TEXT_ATTR_ID, "values": [{"value": val}]})
            elif size_attr:
                rv = resolve_dict(int(size_attr["id"]), int(size_attr.get("dictionary_id") or 0), val)
                if rv:
                    attrs.append({"id": int(size_attr["id"]), "values": [{"dictionary_value_id": rv["dictionary_value_id"], "value": rv.get("value") or val}]})
        items.append(item)
    return items
