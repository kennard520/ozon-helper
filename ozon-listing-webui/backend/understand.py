"""理解层：一次多模态调用，把商品(标题+图+详情+描述+参数)理解成结构化 understanding，缓存复用。

设计见 docs/.../2026-06-22-auto-listing-system-design.md §3.3。
- vision 只跑这一次，文案/图片/属性复用 understanding（不再读图）。
- 纯函数(输入构造/解析)可离线单测；多模态调用以 chat_fn 注入。
"""
from __future__ import annotations

import json
from typing import Any, Callable

# 系统提示：让多模态模型"看图+读字+理解"，输出结构化 JSON
SYS_UNDERSTAND = (
    "You are a cross-border e-commerce product analyst for the Ozon (Russia) marketplace. "
    "Look at the product IMAGES and read ALL on-image text (Chinese marketing text, sizes, "
    "parameters, package lists), together with the given title / params / description. "
    "Then OUTPUT ONLY a JSON object (no explanation, no markdown), with this shape:\n"
    "{\n"
    '  "type": "品类(中文简述)",\n'
    '  "material": "材质",\n'
    '  "specs": {"容量":"", "尺寸":"", "重量":"", "颜色":""},\n'
    '  "points": ["卖点(从图上文字+外观提炼,中文)"],\n'
    '  "scenes": ["使用场景"],\n'
    '  "kit": ["包装/配件清单"],\n'
    '  "audience": "适用人群",\n'
    '  "images": [{"idx": 0, "role": "整体|细节|卖点|尺寸|包装|场景"}],\n'
    '  "confidence": {"<字段路径>": "用户确认|图片识别|合理推断|待确认"},\n'
    '  "copy_seed": {"title_kw": ["核心关键词"], "desc_points": ["可写进描述的要点"]}\n'
    "}\n"
    "Rules:\n"
    "- specs 必须给带标签的值(分清哪个数字是高/容量/重量),不要裸数字堆叠;"
    "**尺寸和重量必须带单位**(如 尺寸 '335×290×185 mm'、重量 '1800 g' 或 '1.8 kg'),"
    "单位以图上/参数上标注的为准,绝不丢单位、不擅自换算。\n"
    "- 数字/规格来源:图上读到的→confidence '图片识别';用户参数给的→'用户确认';"
    "外观合理推断→'合理推断';不确定→省略或'待确认'。绝不编造没有的参数。\n"
    "- images: 给每张图(按提供顺序 idx)标一个角色。\n"
    "- points 只写**产品本身**的卖点/功能;**剔除一切非产品内容**:品牌/厂商/店名、保证质保(如'X天免费试用/无理由退换/终身质保')、"
    "送货上门/免费配送、源头工厂/支持OEM·ODM/厂家直供/一件代发、促销折扣、价格、联系方式、二维码、链接。"
)

_DEFAULTS = {"specs": dict, "points": list, "scenes": list, "kit": list,
             "images": list, "confidence": dict, "copy_seed": dict}


def build_understand_input(draft: dict, *, max_images: int = 6) -> tuple[str, list[str]]:
    """构造喂多模态的 (user_text, image_urls)。
    图片:详情图(卖点密)优先 + 主图,去重,≤max_images;并带 idx 让模型标角色。"""
    draft = draft or {}
    raw = draft.get("source_raw")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    raw = raw if isinstance(raw, dict) else {}

    title = draft.get("source_title") or draft.get("ozon_title") or raw.get("title") or ""
    params = raw.get("params") or (draft.get("attributes") if isinstance(draft.get("attributes"), list) else []) or []
    desc = raw.get("description_text") or draft.get("description") or ""

    lines = [f"Title: {title}"]
    for p in params:
        if not isinstance(p, dict):
            continue
        k = p.get("k") or p.get("name") or ""
        v = p.get("v") or p.get("value") or ""
        if k:
            lines.append(f"{k}: {v}")
    if desc:
        lines.append("Description: " + str(desc)[:2000])

    imgs: list[str] = []
    for u in (raw.get("detail_images") or []):
        if str(u or "").strip() and str(u) not in imgs:
            imgs.append(str(u))
    for u in (draft.get("images") or []):
        if str(u or "").strip() and str(u) not in imgs:
            imgs.append(str(u))
    imgs = imgs[:max_images]
    if imgs:
        lines.append(f"\nImages provided in order, idx 0..{len(imgs) - 1}. Tag each image's role by idx.")
    return "\n".join(lines), imgs


def parse_understanding(text: str) -> dict[str, Any]:
    """解析多模态返回的 JSON(容错 ```json 围栏 + 前后噪声)。失败抛 ValueError。"""
    s = str(text or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("\n") + 1:] if "\n" in s else s
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b <= a:
        raise ValueError("理解层未返回有效 JSON")
    obj = json.loads(s[a:b + 1])
    if not isinstance(obj, dict):
        raise ValueError("理解层 JSON 不是对象")
    for key, factory in _DEFAULTS.items():
        if not isinstance(obj.get(key), factory):
            obj[key] = factory()
    return obj


def understand(draft: dict, chat_fn: Callable[[str, str, list[str]], str], *,
               max_images: int = 6, resolve_image: Callable[[str], str] | None = None) -> dict[str, Any]:
    """一次多模态理解。chat_fn(system, user, image_urls) -> str 注入(生产=多模态模型)。
    resolve_image(url)->可取链接 注入(生产: http 直用 / /media/ 转 data URI);失败的图跳过。
    返回结构化 understanding dict。"""
    user, imgs = build_understand_input(draft, max_images=max_images)
    if resolve_image is not None:
        resolved: list[str] = []
        for u in imgs:
            try:
                resolved.append(resolve_image(u))
            except Exception:  # noqa: BLE001 - 取不到的图跳过，不阻断理解
                pass
        imgs = resolved
    raw_out = chat_fn(SYS_UNDERSTAND, user, imgs)
    return parse_understanding(raw_out)
