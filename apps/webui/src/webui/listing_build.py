"""原创建卡分支的「拼装」：把 AI 文案(generate_card) + 图片 URL + 元数据 → 一张待确认草稿 dict。

纯函数，不触网；草稿形状对齐 ozon_client_adapter.ozon_to_draft，便于直接进 store 与校验。
随机货号 random_offer_id（rng 可注入便于测试）。
"""
from __future__ import annotations

import random
import re
import string
from typing import Any, Callable

NO_BRAND = "Нет бренда"
_ALPHABET = string.ascii_uppercase + string.digits

# 默认定价倍率：售价 = 进价 × SELL_MULT；划线价 = 售价 × LINE_MULT
SELL_MULT = 1.3 * 2   # 进价×1.3×2
LINE_MULT = 1.8       # 划线价=1.8×售价


def parse_dims_mm(text: Any) -> tuple[int, int, int] | None:
    """从 '335*290*185mm' / '33.5×29×18.5 cm' / '335 x 290 x 185' 解析出三维，统一成毫米(取整)。
    带单位换算(mm/мм→×1, cm/см→×10, m/м→×1000)；无单位时按数值大小猜(≥100 视作毫米，否则厘米)。
    解析不到三个数则返回 None。"""
    s = str(text or "")
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if len(nums) < 3:
        return None
    vals = [float(n) for n in nums[:3]]
    low = s.lower()
    if "mm" in low or "мм" in low or "毫米" in low:
        factor = 1.0
    elif "cm" in low or "см" in low or "厘米" in low or "公分" in low:
        factor = 10.0
    elif re.search(r"\bm\b|\bм\b|\d\s*m(?![mм])", low):
        factor = 1000.0
    else:
        factor = 1.0 if max(vals) >= 100 else 10.0   # 无单位：大数当毫米，小数当厘米
    out = tuple(int(v * factor + 0.5) for v in vals)   # 四舍五入进位
    return out if all(x > 0 for x in out) else None


def parse_weight_g(text: Any) -> int | None:
    """'1800g' / '1.8kg' / '1800 克' / '1.8 кг' → 克(取整)。无单位时小数值(<50)按千克。"""
    s = str(text or "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    v = float(m.group())
    low = s.lower()
    if "kg" in low or "кг" in low or "千克" in low or "公斤" in low:
        v *= 1000
    elif "g" in low or "г" in low or "克" in low:
        pass
    elif v < 50:   # 无单位且很小 → 多半是千克
        v *= 1000
    g = int(round(v))
    return g if g > 0 else None


def default_pricing(cost: Any, *, sell_mult: float = SELL_MULT,
                    line_mult: float = LINE_MULT) -> tuple[float, float] | None:
    """进价(CNY) → (售价, 划线价)。售价=进价×sell_mult；划线价=售价×line_mult。进价无效返回 None。"""
    try:
        c = float(cost)
    except (TypeError, ValueError):
        return None
    if c <= 0:
        return None
    price = round(c * sell_mult, 2)
    return price, round(price * line_mult, 2)


def random_offer_id(*, prefix: str = "OZ", length: int = 10,
                    rng: Callable[[str], str] | None = None) -> str:
    """随机货号：前缀 + length 位大写字母/数字。rng(alphabet)->char 可注入便于测试。"""
    pick = rng or (lambda alphabet: random.choice(alphabet))
    return prefix + "".join(pick(_ALPHABET) for _ in range(length))


def build_original_draft(
    raw: dict, *, card: dict, image_urls: list[str], offer_id: str,
    source: str = "1688", source_url: str = "",
    price: Any = "", old_price: Any = "", stock: int = 0,
) -> dict:
    """合并 generate_card 结果 + 图片 URL + 元数据 → 待确认草稿（status=ready，待人工确认）。

    card 须为 generate_card(ok=True) 的返回。draft 形状对齐 ozon_to_draft。
    """
    raw = raw or {}
    card = card or {}
    return {
        "source": source, "source_platform": source,
        "offer_id": str(offer_id), "source_offer_id": str(offer_id),
        "source_url": str(source_url),
        "ozon_title": str(card.get("ozon_title") or ""),
        "source_title": str(raw.get("title") or ""),
        "description": str(card.get("description") or ""),
        "category_id": str(card.get("category_id") or ""),
        "type_id": str(card.get("type_id") or ""),
        "category_path": card.get("category_path") or "",
        "price": str(price), "old_price": str(old_price), "stock": int(stock or 0),
        "images": list(image_urls or []),
        # 内部统一：重量 g、尺寸 mm（列名 length_mm 名实相符）
        "weight_g": int(card.get("weight_g") or 0),
        "length_mm": int(card.get("length_mm") or 0),
        "width_mm": int(card.get("width_mm") or 0),
        "height_mm": int(card.get("height_mm") or 0),
        "attributes": card.get("attributes") or [],
        "brand_id": None, "brand_name": str(card.get("brand_name") or NO_BRAND),
        "mapped": card.get("mapped") or [], "unmapped": card.get("unmapped") or [],
        "status": "ready",   # 待人工确认 → 确认后再 publish
    }


def rich_billboard(url: str) -> dict:
    """单个全宽大图 widget（Ozon richAnnotation 的 raShowcase/billboard）。"""
    u = str(url)
    return {"widgetName": "raShowcase", "type": "billboard",
            "blocks": [{"img": {"src": u, "srcMobile": u, "alt": ""}}]}


def build_rich_content(image_urls, *, version: float = 0.3) -> dict:
    """把一组图 URL 组装成 Ozon richAnnotationJson（每张一个全宽 billboard）。
    俄语文字烤进图里（信息图），故富文本=有序大图，无需文本 widget。
    存入 draft.source_raw.rich_content_json，发布时 to_ozon_import_item 自动塞属性 11254、
    rewrite_item_media 把图链换 OSS 直链。"""
    content = [rich_billboard(u) for u in (image_urls or []) if str(u or "").strip()]
    return {"content": content, "version": version}
