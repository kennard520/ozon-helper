from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

_OFFER_ID_RE = re.compile(r"(?:offer/|offerId=|offer_id=)(\d{8,})")

RICH_CONTENT_ATTR_ID = 11254  # Ozon "Rich-контент JSON" 系统属性；值为 richAnnotationJson 字符串
_URL_ID_RE = re.compile(r"(\d{8,})")
BRAND_ATTR_ID = 85
HASHTAGS_ATTR_ID = 23171   # #Хештеги 主题标签：发布时每个标签必须是 values 里一个独立值
NO_BRAND = "Нет бренда"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _hashtag_values(values: Any) -> list[dict[str, str]]:
    """主题标签(23171/#Хештеги)是 Ozon 的**单值**属性(只能一个值)：所有标签放进**一个**值里，
    空格分隔、每个 # 开头、标签内部不能有空格(多词用 _)、去重、最多 30 个。
    把(可能被拆成多值 / 整串 / 下划线连写的)输入规整成单个值。"""
    tags: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        s = str((v or {}).get("value") or "")
        for part in s.replace("#", " #").split():   # 先按 # 切，再按空白切
            t = part.lstrip("#").strip().strip("_")
            if not t or ("#" + t) in seen:
                continue
            seen.add("#" + t)
            tags.append("#" + t)
            if len(tags) >= 30:
                break
        if len(tags) >= 30:
            break
    return [{"value": " ".join(tags)}] if tags else []
HIGH_RISK_BRANDS = {
    "apple", "iphone", "ipad", "macbook", "airpods",
    "samsung", "xiaomi", "huawei",
    "nike", "adidas", "puma", "reebok", "new balance",
    "lego", "disney", "marvel", "pokemon", "barbie",
    "dyson", "sony", "jbl", "bosch", "philips",
}
FORBIDDEN_RU_AD_WORDS = {
    "скидка", "акция", "распродажа", "дешево", "дёшево",
    "лучший", "лучшая", "лучшее", "лучшие",
    "№1", "номер 1", "топ", "хит", "хит продаж",
    "новинка", "выгодно", "суперцена", "подарок",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_1688_url(url: str) -> str:
    value = url.strip()
    if not value:
        raise ValueError("empty url")
    parsed = urlparse(value)
    if not parsed.scheme:
        value = f"https://{value}"
        parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported url scheme: {parsed.scheme}")
    if not parsed.netloc:
        raise ValueError("url host is required")
    # 1688 offer 页：去掉 spm 等查询跟踪参数(每次打开都不同)，只留 offer 路径 + #sku 变体片段。
    # 目的：同一(商品,变体)的 source_url 稳定→重采能去重；不同变体(#sku 不同)各自唯一→各建一张草稿；
    # url 也短，不会被唯一键 uq_draft 的 source_url(255) 前缀截断而把不同变体误判成同一条(导致 500/收敛)。
    if "1688.com" in (parsed.netloc or "") and "/offer/" in (parsed.path or ""):
        rebuilt = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.fragment:
            rebuilt += f"#{parsed.fragment}"
        return rebuilt
    return value


def extract_offer_id(url: str) -> str | None:
    match = _OFFER_ID_RE.search(url)
    if match:
        return match.group(1)
    host = urlparse(url).netloc.lower()
    if "wildberries." in host:
        m = re.search(r"/catalog/(\d+)", url)
        return m.group(1) if m else None
    if "ozon." in host:
        # /product/4585365823/ 或 /product/slug-...-1117478728/ → 取末尾数字段为 SKU
        m = re.search(r"/product/(?:.*-)?(\d{6,})/?", urlparse(url).path)
        return m.group(1) if m else None
    if "1688.com" not in host and "alibaba.com" not in host:
        return None
    match = _URL_ID_RE.search(url)
    return match.group(1) if match else None


def create_draft_from_url(
    url: str, *, source_platform: str = "1688", scraped: dict[str, Any] | None = None
) -> dict[str, Any]:
    normalized = normalize_1688_url(url)
    offer_id = extract_offer_id(normalized)
    now = utc_now_iso()
    suffix = offer_id or "manual"
    platform = source_platform.strip().lower() or "manual"
    platform_name = {"1688": "1688商品", "ozon": "Ozon商品", "wb": "WB商品"}.get(platform, "手工商品")
    s = scraped or {}
    return {
        "source_platform": platform,
        "source_url": normalized,
        "source_offer_id": offer_id,
        "source_title": str(s.get("source_title") or "").strip() or f"{platform_name} {suffix}",
        "purchase_url": normalized if platform == "1688" else "",
        "purchase_note": "",
        "ozon_title": str(s.get("ozon_title") or "").strip(),
        "description": str(s.get("description") or "").strip(),
        "category_id": str(s.get("category_id") or "").strip(),
        "type_id": str(s.get("type_id") or "").strip(),
        "brand_id": None,
        "brand_name": NO_BRAND,
        "price": str(s.get("price") or "").strip(),
        "old_price": str(s.get("old_price") or "").strip(),
        "cost_cny": s.get("cost_cny"),
        "video_url": str(s.get("video_url") or "").strip(),
        "local_images": _as_list(s.get("local_images")),
        "stock": 1,
        "weight_g": _to_int(s.get("weight_g")) or None,
        "length_mm": _to_int(s.get("length_mm")) or None,
        "width_mm": _to_int(s.get("width_mm")) or None,
        "height_mm": _to_int(s.get("height_mm")) or None,
        "images": _as_list(s.get("images")),
        "attributes": s.get("attributes") if isinstance(s.get("attributes"), (list, dict)) else {},
        "status": "draft",
        "validation_errors": [],
        "publish_response": None,
        "created_at": now,
        "updated_at": now,
    }


def _has_rich_content(draft: dict[str, Any]) -> bool:
    """草稿是否带富文本(A+ Rich 内容)；有富文本时描述可留空。"""
    sr = draft.get("source_raw")
    if isinstance(sr, str):
        sr = loads_json(sr, {})
    return bool(isinstance(sr, dict) and sr.get("rich_content_json"))


def validate_draft(draft: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    title = str(draft.get("ozon_title") or "").strip()
    brand_name = str(draft.get("brand_name") or "").strip()
    if not title:
        errors.append("Ozon俄语标题不能为空")
    else:
        if not CYRILLIC_RE.search(title):
            errors.append("违规：标题必须包含俄语西里尔字符，不能仅使用中文/英文")
        for word in _forbidden_ru_ad_words_in(title):
            errors.append(f"违规：标题包含违禁广告词 {word}，请删除后重新提交")
        for brand in _blacklisted_brands_in(title):
            errors.append(
                f"检测到未授权品牌在黑名单：{brand}，缺少俄罗斯官方授权，禁止上架，请改为无品牌{NO_BRAND}"
            )
    if brand_name and brand_name != NO_BRAND:
        errors.append(
            f"检测到未授权品牌在黑名单：{brand_name}，缺少俄罗斯官方授权，禁止上架，请改为无品牌{NO_BRAND}"
        )
    # 描述与富文本(Rich)二选一即可：纯富文本商品可不填描述
    if not str(draft.get("description") or "").strip() and not _has_rich_content(draft):
        errors.append("描述不能为空（或需有富文本 Rich 内容）")
    if not str(draft.get("category_id") or "").strip():
        errors.append("description_category_id 不能为空（在类目搜索里选）")
    if not str(draft.get("type_id") or "").strip():
        errors.append("type_id 不能为空（类目搜索里一起选）")
    if _to_float(draft.get("price")) <= 0:
        errors.append("售价必须大于0")
    if _to_int(draft.get("stock")) < 0:
        errors.append("库存不能为负数")
    if not _as_list(draft.get("images")):
        errors.append("至少需要1张图片URL")
    # 密度荒谬(明显单位错误)→拦发布，省去发到 Ozon 才被退的往返。尺寸列统一存「毫米」。
    d = _pack_density_kg_m3(draft)
    if d is not None and d < 8:
        errors.append(
            f"尺寸/重量密度仅 ~{d:.1f} kg/m³，几乎可断定尺寸/重量单位填错(尺寸列存「毫米」)，"
            f"请核对长宽高(mm)与克重，否则 Ozon 必报 INCORRECT_DENSITY（Неверные габариты или вес）"
        )
    return errors


def _blacklisted_brands_in(text: str) -> list[str]:
    hay = f" {text.lower()} "
    hits: list[str] = []
    for brand in sorted(HIGH_RISK_BRANDS, key=len, reverse=True):
        pattern = rf"(?<![a-z0-9]){re.escape(brand)}(?![a-z0-9])"
        if re.search(pattern, hay, flags=re.IGNORECASE):
            hits.append(brand)
    return hits


def _forbidden_ru_ad_words_in(text: str) -> list[str]:
    hay = text.lower()
    hits: list[str] = []
    for word in sorted(FORBIDDEN_RU_AD_WORDS, key=len, reverse=True):
        if re.search(rf"(?<![а-яёa-z0-9]){re.escape(word.lower())}(?![а-яёa-z0-9])", hay, flags=re.IGNORECASE):
            hits.append(word)
    return hits


def _pack_density_kg_m3(draft: dict[str, Any]) -> float | None:
    """包装密度(kg/m³)。length_mm/width_mm/height_mm 统一存「毫米」，体积按毫米算。缺值返回 None。"""
    L = _to_int(draft.get("length_mm")); W = _to_int(draft.get("width_mm"))
    H = _to_int(draft.get("height_mm")); wt = _to_int(draft.get("weight_g"))
    if min(L, W, H) <= 0 or wt <= 0:
        return None
    vol_m3 = (L / 1000.0) * (W / 1000.0) * (H / 1000.0)   # 列存毫米 → m³
    return (wt / 1000.0) / vol_m3 if vol_m3 > 0 else None


def dimension_warnings(draft: dict[str, Any]) -> list[str]:
    """克重/包装尺寸缺失 → 软警告（不阻断发布，发到 Ozon 后台再补；Ozon 会按密度校验回显）。"""
    warnings: list[str] = []
    if _to_int(draft.get("weight_g")) <= 0:
        warnings.append("克重(g)未填，建议补（Ozon 可能按密度报错）")
    for k, label in (("length_mm", "长"), ("width_mm", "宽"), ("height_mm", "高")):
        if _to_int(draft.get(k)) <= 0:
            warnings.append(f"包装{label}(mm)未填，建议补")
    # 密度合理性预检：尺寸列统一存「毫米」，单位填错会让密度暴跌/暴涨，Ozon 必报
    # 「Неверные габариты или вес / INCORRECT_DENSITY」。在发布前就提醒。
    d = _pack_density_kg_m3(draft)
    if d is not None:
        if d < 25:
            warnings.append(f"密度异常偏低(~{d:.0f} kg/m³)：核对尺寸(mm)与克重单位，否则 Ozon 报габариты/вес错误")
        elif d > 3000:
            warnings.append(f"密度异常偏高(~{d:.0f} kg/m³)：核对尺寸/重量是否填反或单位有误")
    return warnings


def normalize_category_attrs(raw: Any) -> list[dict[str, Any]]:
    """把 /v1/description-category/attribute 的返回拍平成精简属性元数据。"""
    result = raw.get("result") if isinstance(raw, dict) else raw
    out: list[dict[str, Any]] = []
    for a in result or []:
        if not isinstance(a, dict):
            continue
        aid = _to_int(a.get("id"))
        if not aid:
            continue
        out.append({
            "id": aid,
            "name": str(a.get("name") or ""),
            "description": str(a.get("description") or ""),   # Ozon 官方填写说明/格式提示，喂 AI
            "is_required": bool(a.get("is_required")),
            # is_collection=true：多选(可填多个值)；max_value_count=该多选最多几个(下拉限选)
            "is_collection": bool(a.get("is_collection")),
            "max_value_count": _to_int(a.get("max_value_count")),
            # is_aspect=true：变体维度/「区别特征」(合并成一张卡时各变体不同的属性，如商品颜色)
            "is_aspect": bool(a.get("is_aspect")),
            "dictionary_id": _to_int(a.get("dictionary_id")),
            "type": str(a.get("type") or ""),
            "group_name": str(a.get("group_name") or ""),
            # category_dependent=true 的属性（如"类型"）由 type_id 表达：发布时无需单独填、
            # Ozon 拉取 attributes 时也不返回它。不能当作"缺失"，否则已完整的商品被误报缺类型。
            "category_dependent": bool(a.get("category_dependent")),
        })
    return out


def filled_attribute_ids(draft: dict[str, Any]) -> set[int]:
    """草稿里已经填了值的属性 id 集合（上架格式 [{id, values:[...]}]）。品牌(85)由专用字段判定。"""
    filled: set[int] = set()
    raw = draft.get("attributes")
    if isinstance(raw, list):
        for a in raw:
            if not isinstance(a, dict):
                continue
            aid = _to_int(a.get("id"))
            values = a.get("values") if isinstance(a.get("values"), list) else []
            has_value = any(
                (_to_float(v.get("dictionary_value_id")) > 0) or str(v.get("value") or "").strip()
                for v in values if isinstance(v, dict)
            )
            if aid and has_value:
                filled.add(aid)
    if _to_int(draft.get("brand_id")) > 0:
        filled.add(85)
    return filled


def missing_required_attributes(
    draft: dict[str, Any], category_attrs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """返回该类目必填、但草稿还没填的属性 [{id, name}]。
    跳过 category_dependent 属性（如"类型"）——它们由 type_id 表达，无需单独填，
    Ozon 拉取时不返回，算缺失会误报已完整商品。"""
    filled = filled_attribute_ids(draft)
    missing = []
    for a in category_attrs or []:
        if a.get("category_dependent"):
            continue
        if a.get("is_required") and _to_int(a.get("id")) not in filled:
            missing.append({"id": _to_int(a.get("id")), "name": a.get("name") or f"属性{a.get('id')}"})
    return missing


def _norm_attr_name(s: Any) -> str:
    """属性名归一：小写、去首尾空白、去结尾的冒号/标点，便于俄文名比对。"""
    return re.sub(r"[\s:：,，.。]+$", "", str(s or "").strip().lower())


def collected_chars(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """草稿里采集来的参考特征 [{name, value, key?}]（区别于上架格式 {id, values}）。"""
    raw = draft.get("attributes")
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, dict) and a.get("name") and a.get("value") and "values" not in a:
                out.append(a)
    return out


def match_chars_to_attributes(
    chars: list[dict[str, Any]], category_attrs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """按俄文名把采集特征对到类目属性，返回 [{attr, char}]。优先名字精确匹配。"""
    by_name: dict[str, dict[str, Any]] = {}
    for ch in chars:
        key = _norm_attr_name(ch.get("name"))
        if key and key not in by_name:
            by_name[key] = ch
    pairs: list[dict[str, Any]] = []
    for a in category_attrs or []:
        ch = by_name.get(_norm_attr_name(a.get("name")))
        if ch:
            pairs.append({"attr": a, "char": ch})
    return pairs


def split_collection_value(text: str) -> list[str]:
    """把采集到的多值文本（Ozon 用 ' , ' 分隔）拆成单值列表。"""
    parts = [p.strip() for p in re.split(r"\s*,\s*", str(text or "")) if p.strip()]
    return parts or ([text.strip()] if str(text or "").strip() else [])


def offer_id_for(draft: dict[str, Any]) -> str:
    """草稿在 Ozon 上的 offer_id（与发布时一致），用于删除/更新/备货 JOIN。
    变体组：offer_id **必须每个变体唯一**——同组各 SKU 采集到的 offer_id 都是同一个 1688 商品 id，
    若直接发会同 offer_id 互相覆盖、合不成多变体卡。故用 variant_group + sku_id 拼成稳定唯一货号。
    否则优先用已存的 offer_id 列（发布后会回写，成为单一真相，且功能⑤拉单按它 JOIN），
    其次 source_offer_id（采集得到的源货号），最后 manual-{id} 兜底。"""
    sr = draft.get("source_raw")
    if isinstance(sr, str):
        sr = loads_json(sr, {})
    if isinstance(sr, dict):
        vg = str(sr.get("variant_group") or "").strip()
        sku = str(sr.get("sku_id") or "").strip()
        if vg and sku:
            return f"{vg}-{sku}"
    explicit = str(draft.get("offer_id") or "").strip()
    if explicit:
        return explicit
    return str(draft.get("source_offer_id") or f"manual-{draft.get('id')}")


def to_ozon_import_item(draft: dict[str, Any]) -> dict[str, Any]:
    errors = validate_draft(draft)
    if errors:
        raise ValueError("; ".join(errors))
    offer_id = offer_id_for(draft)
    # 只透传 Ozon 上架结构 [{id, values:[...]}]，采集的 {name,value} 非上架格式 → 丢掉
    raw_attrs = draft.get("attributes")
    publish_attrs: list[dict[str, Any]] = []
    if isinstance(raw_attrs, list):
        publish_attrs = [
            a for a in raw_attrs
            if isinstance(a, dict) and "id" in a and "values" in a and _to_int(a.get("id")) != BRAND_ATTR_ID
        ]
    # 品牌(attr 85)统一按无品牌发布；不透传采集源或 AI 识别出的品牌，避免未授权侵权风险。
    brand_id = _to_int(draft.get("brand_id"))
    if brand_id > 0 and str(draft.get("brand_name") or "").strip() == NO_BRAND:
        publish_attrs.append({
            "id": BRAND_ATTR_ID,
            "values": [{
                "dictionary_value_id": brand_id,
                "value": NO_BRAND,
            }],
        })
    # 富文本(A+)：把采集到的原始 richAnnotationJson 作为 Rich 内容属性发布
    sr = draft.get("source_raw")
    if isinstance(sr, str):
        sr = loads_json(sr, {})
    # 型号名(9048)：变体组草稿**强制** = variant_group——组内一致 → Ozon 合并为一张多变体卡，
    # 并覆盖采集到的杂值(如中文"喂食")。与整组发布 publish_variant_group 的 mname 保持一致。
    _vg = str(sr.get("variant_group") or "").strip() if isinstance(sr, dict) else ""
    if _vg:
        publish_attrs = [a for a in publish_attrs if _to_int(a.get("id")) != 9048]
        publish_attrs.append({"id": 9048, "values": [{"value": _vg}]})
    if isinstance(sr, dict) and sr.get("rich_content_json"):
        publish_attrs.append({
            "id": RICH_CONTENT_ATTR_ID,
            "complex_id": 0,
            "values": [{"value": dumps_json(sr["rich_content_json"])}],
        })
    # 主题标签(23171/#Хештеги)：Ozon 要求**每个标签是 values 里一个独立值**(以#开头、内部无空格)，
    # 不能整串塞一个值(否则报"标签内有空格/超30")。把已存值(可能整串/下划线连写)拆成单个标签，≤30。
    publish_attrs = [
        ({**a, "values": _hashtag_values(a.get("values"))} if _to_int(a.get("id")) == HASHTAGS_ATTR_ID else a)
        for a in publish_attrs
    ]
    publish_attrs = dedupe_publish_attributes(publish_attrs)
    item = {
        "offer_id": str(offer_id),
        "name": str(draft["ozon_title"]).strip(),
        "description": str(draft["description"]).strip(),
        "description_category_id": int(str(draft["category_id"]).strip()),
        "type_id": int(str(draft["type_id"]).strip()),
        "price": str(draft["price"]).strip(),
        "old_price": str(draft.get("old_price") or draft["price"]).strip(),
        "currency_code": "RUB",
        "vat": "0",
        "weight": _to_int(draft.get("weight_g")),
        "weight_unit": "g",
        # 尺寸列统一存「毫米」(列名 *_mm 名实相符)；Ozon 也用毫米 → 直发，不换算。depth=长 width=宽 height=高。
        "depth": _to_int(draft.get("length_mm")),
        "width": _to_int(draft.get("width_mm")),
        "height": _to_int(draft.get("height_mm")),
        "dimension_unit": "mm",
        "images": _as_list(draft.get("images")),
        "attributes": publish_attrs,
    }
    # 视频：Ozon 走 complex_attributes（complex_id=100001，id 21841=链接、21837=名称）。
    # 要求 MP4/MOV、8s~5min；Ozon 按 URL 抓取（须公网可达）。
    video_url = str(draft.get("video_url") or "").strip()
    if video_url:
        video_name = (str(draft.get("ozon_title") or "").strip() or "video")[:200]
        item["complex_attributes"] = [{
            "attributes": [
                {"complex_id": 100001, "id": 21841, "values": [{"value": video_url}]},
                {"complex_id": 100001, "id": 21837, "values": [{"value": video_name}]},
            ],
        }]
    return item


def _attribute_has_value(attr: dict[str, Any]) -> bool:
    values = attr.get("values") if isinstance(attr.get("values"), list) else []
    for v in values:
        if not isinstance(v, dict):
            continue
        if _to_int(v.get("dictionary_value_id")) > 0 or str(v.get("value") or "").strip():
            return True
    return False


def dedupe_publish_attributes(attrs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one publish attribute per id, preferring the latest non-empty value."""
    order: list[int] = []
    by_id: dict[int, dict[str, Any]] = {}
    for raw in attrs or []:
        if not isinstance(raw, dict):
            continue
        aid = _to_int(raw.get("id"))
        if not aid:
            continue
        attr = {**raw, "id": aid}
        if aid not in by_id:
            order.append(aid)
            by_id[aid] = attr
            continue
        if _attribute_has_value(attr) or not _attribute_has_value(by_id[aid]):
            by_id[aid] = attr
    return [by_id[aid] for aid in order if _attribute_has_value(by_id[aid])]


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, dict):
        return [value]
    return []


def video_needs_upload(video_url: object) -> bool:
    """视频是否需要先上传到 Ozon 再发布。非空且域名不含 ozone.ru → True。
    Ozon 只收它自己能 fetch 的源；淘宝/1688 CDN 视频它会静默丢弃。"""
    url = str(video_url or "").strip()
    if not url:
        return False
    return "ozone.ru" not in url.lower()


def local_image_paths(images: object) -> list[str]:
    """挑出 /media/ 开头的本地自传图(Ozon 抓不到，须先上传)。公网源图不动。"""
    if not isinstance(images, list):
        return []
    return [str(u) for u in images if isinstance(u, str) and str(u).startswith("/media/")]
