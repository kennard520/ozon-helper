"""纯工具函数（无业务状态），从 app_service 抽出以便跨模块复用。"""
from __future__ import annotations

import urllib.request


# ---------------------------------------------------------------------------
# 语言常量
# ---------------------------------------------------------------------------

OZON_ATTRIBUTE_LANGUAGES = {"DEFAULT", "EN", "RU", "TR", "ZH_HANS"}

# 物理量属性关键词(按 Ozon 属性名判定)：重量/尺寸/容量——这些由代码按单位确定填，不让 AI 猜
_WEIGHT_KW = ("重量", "净重", "毛重", "克重", "вес", "масса")
_DIM_KW = ("尺寸", "размер", "габарит")
_VOL_KW = ("容量", "体积", "容积", "объ", "вмести", "вмещ")

# step_flags 中排除的属性 id（固定/系统属性）
_ATTR_EXCL = {9048, 23171, 85}


# ---------------------------------------------------------------------------
# 数值解析
# ---------------------------------------------------------------------------

def _money_to_float(row: dict, keys: tuple[str, ...]) -> dict:
    """把 dict 中指定钱字段的 Decimal 转 float（None 保留），返回新 dict。"""
    out = dict(row)
    for k in keys:
        v = out.get(k)
        if v is not None:
            out[k] = float(v)
    return out


def _to_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_dims_mm(text: object) -> tuple | None:
    """'190×190×340 mm' / '20.5x20.5x30.5 cm' → (L,W,H) 毫米(int)。取前3个数，按单位换算到 mm；不足3个→None。"""
    import re  # noqa: PLC0415
    s = str(text or "")
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if len(nums) < 3:
        return None
    vals = [float(x) for x in nums[:3]]
    low = s.lower()
    if ("cm" in low) or ("см" in low) or ("厘米" in low):
        vals = [v * 10 for v in vals]   # cm→mm
    return tuple(int(round(v)) for v in vals)


def _parse_volume_ml(text: object) -> int | None:
    """提体积:数字紧跟体积单位才算('4 L'/'50ml'/'净含量4升')→毫升(int)。
    无体积单位→None(避免把型号/规格里的裸数字误当容量)。"""
    import re  # noqa: PLC0415
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|мл|毫升|cc|l|л|升|литр)", str(text or "").lower())
    if not m:
        return None
    v = float(m.group(1))
    return int(round(v * 1000)) if m.group(2) in ("l", "л", "升", "литр") else int(round(v))


def _parse_weight_g(text: object) -> int | None:
    """提重量:数字紧跟重量单位才算('1.8kg'/'50克'/'净含量50g')→克(int)。无单位→None。"""
    import re  # noqa: PLC0415
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|кг|千克|公斤|g|克|г|mg|мг)", str(text or "").lower())
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)
    if u in ("kg", "кг", "千克", "公斤"):
        return int(round(v * 1000))
    if u in ("mg", "мг"):
        return int(round(v / 1000))
    return int(round(v))


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------

def _has_cjk(text: object) -> bool:
    """是否含中日韩表意文字（CJK 统一汉字）。用于拦未本地化的 1688 草稿。"""
    return any("一" <= ch <= "鿿" for ch in str(text or ""))


def _attr_language(language: str | None) -> str:
    lang = str(language or "ZH_HANS").strip().upper()
    if lang in {"ZH", "ZH-HANS", "ZH_CN", "ZH-CN"}:
        return "ZH_HANS"
    return lang if lang in OZON_ATTRIBUTE_LANGUAGES else "ZH_HANS"


def _models_url(base: str) -> str:
    """OpenAI 兼容 /v1/models 端点：容忍 base 带/不带 /v1（同 chat 端点处理）。"""
    b = str(base or "").rstrip("/")
    if b.endswith("/v1"):
        b = b[:-3].rstrip("/")
    return b + "/v1/models"


def _is_country_attr(attr: dict) -> bool:
    """是否「原产国/制造国」属性（写死中国，发布时强制填，不在 UI 让用户填）。
    名按中文(原产国/制造国/生产国/产地)或俄文(страна/произв)匹配。"""
    nm = str(attr.get("name") or "")
    low = nm.lower()
    return ("原产国" in nm or "制造国" in nm or "生产国" in nm or "产地" in nm
            or "страна" in low or "произв" in low)


def _download_bytes(url: str, *, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def _img_type_from_label(label: object) -> str:
    """候选图 label/slot → 图集类型(白底/主图/细节/场景/尺寸/卖点/包装/其他)，供图集分类与排序。"""
    s = str(label or "")
    for kw, t in (("白底", "白底"), ("主图", "白底"), ("细节", "细节"), ("场景", "场景"),
                  ("尺寸", "尺寸"), ("卖点", "卖点"), ("包装", "包装")):
        if kw in s:
            return t
    return "其他"


# ---------------------------------------------------------------------------
# 草稿工作流标志
# ---------------------------------------------------------------------------

def step_flags(draft: dict) -> dict:
    """从草稿字段派生 7 步完成标志(等价前端 DraftDetail.wfDone，移到源头算)。

    content 兼容新流水线的合并步骤: category + copy + attrs 全部完成。
    """
    d = draft or {}
    sr = d.get("source_raw") or {}
    if isinstance(sr, str):
        from webui.drafts import loads_json  # noqa: PLC0415

        sr = loads_json(sr, {}) or {}

    und = sr.get("understanding")
    attrs = d.get("attributes") if isinstance(d.get("attributes"), list) else []

    def _attr_done(a):
        try:
            return (
                a is not None
                and a.get("id") is not None
                and int(a["id"]) not in _ATTR_EXCL
                and isinstance(a.get("values"), list)
                and len(a["values"]) > 0
            )
        except (TypeError, ValueError):
            return False

    # rich_content_json 是前端 richContentJson computed 实际读的键(DraftDetail.vue:1998)
    workflow_status = sr.get("workflow_status") if isinstance(sr.get("workflow_status"), dict) else {}
    rich_status = workflow_status.get("rich") if isinstance(workflow_status.get("rich"), dict) else {}
    rich = bool(rich_status.get("status") == "done")

    category_done = bool(d.get("category_id") and d.get("type_id"))
    copy_done = bool(d.get("ozon_title") and d.get("description"))
    attrs_done = any(_attr_done(a) for a in attrs)
    return {
        "understand": isinstance(und, dict) and bool(und),
        "category": category_done,
        "copy": copy_done,
        "attrs": attrs_done,
        "content": category_done and copy_done and attrs_done,
        "images": bool(d.get("images")) or bool(sr.get("image_types")),
        "rich": rich,
        "publish": bool(d.get("ozon_product_id")) or d.get("status") == "published",
    }
