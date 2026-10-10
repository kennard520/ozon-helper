"""智能推荐:据来源 + understanding(逐图角色) + 复制可用性 → 推荐路径 + 逐图默认处理。

纯函数,无 IO,可离线单测。设计见 system-design §3.8。
路径:Ozon 可复制→复制(零做图);否则按图判"俄化(换字)/重做(原创)"。
"""
from __future__ import annotations

from typing import Any

TEXT_ROLES = {"卖点", "尺寸", "包装"}      # 文字密/营销拼图 → 仅换字仍判重,倾向重做
VISUAL_ROLES = {"整体", "细节", "场景"}    # 以图为主


def _img_default(role: str, mode: str) -> str:
    """单图默认处理。mode=整品推荐。重做模式全重做;俄化模式:文字图俄化、纯视觉图保留。"""
    if mode == "重做":
        return "重做"
    return "俄化" if role in TEXT_ROLES else "保留"


def recommend_path(*, source: str, understanding: dict | None = None,
                   copyable: bool | None = None) -> dict[str, Any]:
    """
    source: 'ozon'|'wb'|'1688'(大小写无关)
    understanding: 含 images:[{idx, role}]
    copyable: True=源卡允许复制 / False=禁止 / None=未探测(可试)
    返回 {recommended, mode, copy:{available,reason}, per_image:[{idx,role,default}], reason}
    """
    src = str(source or "").strip().lower()
    imgs = [i for i in ((understanding or {}).get("images") or []) if isinstance(i, dict)]
    total = len(imgs)
    text_heavy = sum(1 for i in imgs if str(i.get("role") or "") in TEXT_ROLES)

    # 复制可用性(仅 Ozon;None=未探测可试,False=禁止)
    if src == "ozon" and copyable is not False:
        copy_avail = True
        copy_reason = "源卡允许复制" if copyable else "Ozon 源,可试官方复制"
    elif src == "ozon":
        copy_avail, copy_reason = False, "源卡禁止复制"
    else:
        copy_avail, copy_reason = False, f"{src or '非Ozon'} 来源无官方复制"

    # 整品模式
    if copy_avail:
        recommended = mode = "复制"
        reason = "Ozon 可复制 → 官方复制最快,无需做图"
    elif total and text_heavy * 2 >= total:    # 营销拼图占多数
        recommended = mode = "重做"
        reason = "图多为营销拼图/含横幅文字,仅换字仍会判重 → 建议完整重做"
    else:
        recommended = mode = "俄化"
        reason = "图多为干净产品图 → 俄化(图上中文换俄语)即可"

    per_image = [{"idx": i.get("idx"), "role": str(i.get("role") or ""),
                  "default": _img_default(str(i.get("role") or ""), mode)} for i in imgs]
    return {"recommended": recommended, "mode": mode,
            "copy": {"available": copy_avail, "reason": copy_reason},
            "per_image": per_image, "reason": reason}
