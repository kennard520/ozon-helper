from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[2]   # backend/ → ozon-listing-webui → tools
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from ozon_api import OzonSellerClient  # noqa: E402


def build_client(settings: dict[str, Any]) -> OzonSellerClient:
    client_id = str(settings.get("ozon_client_id") or "").strip()
    api_key = str(settings.get("ozon_api_key") or "").strip()
    if not client_id or not api_key:
        raise ValueError("请先在设置里保存 Ozon Client-Id 和 Api-Key")
    return OzonSellerClient(client_id=client_id, api_key=api_key)


_client = build_client  # 兼容旧引用


def publish_items(settings: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    return _client(settings).import_products(items)


def delete_products(settings: dict[str, Any], offer_ids: list[str]) -> dict[str, Any]:
    return _client(settings).delete_products(offer_ids)


def get_import_info(settings: dict[str, Any], task_id: int) -> dict[str, Any]:
    return _client(settings).get_import_info(task_id)


def get_category_attributes(
    settings: dict[str, Any], description_category_id: int, type_id: int,
    language: str = "ZH_HANS",
) -> dict[str, Any]:
    return _client(settings).get_category_attributes(
        description_category_id, type_id, language=language
    )


def search_attribute_values(
    settings: dict[str, Any], description_category_id: int, type_id: int,
    attribute_id: int, value: str, limit: int = 20, language: str = "ZH_HANS",
) -> dict[str, Any]:
    return _client(settings).search_attribute_values(
        description_category_id, type_id, attribute_id, value, limit=limit, language=language
    )


# ---------- 功能①：拉取 Ozon 已有商品 ----------
def list_ozon_products(settings: dict, visibility: str = "ALL") -> list[dict]:
    """分页拉全部 (product_id, offer_id)。"""
    client = build_client(settings)
    items, last_id = [], ""
    while True:
        r = client.list_products(visibility=visibility, last_id=last_id, limit=1000)
        result = r.get("result") or {}
        batch = result.get("items") or []
        items.extend(batch)
        last_id = result.get("last_id") or ""
        if len(batch) < 1000 or not last_id:
            break
    return items


def get_ozon_info(settings: dict, offer_ids: list[str]) -> dict[str, dict]:
    client = build_client(settings)
    out: dict[str, dict] = {}
    for i in range(0, len(offer_ids), 1000):
        chunk = offer_ids[i:i + 1000]
        r = client.get_products_info(offer_ids=chunk)
        for it in (r.get("items") or []):
            out[str(it.get("offer_id"))] = it
    return out


def get_ozon_descriptions(settings: dict, offer_ids: list[str]) -> dict[str, str]:
    """逐 offer_id 调 /v1/product/info/description，返回 {offer_id: description_text}。
    单个失败不中断整体（返回空字符串占位）。"""
    client = build_client(settings)
    out: dict[str, str] = {}
    for oid in offer_ids:
        try:
            r = client.get_product_description(offer_id=oid)
            result = r.get("result") or {}
            out[oid] = str(result.get("description") or "")
        except Exception:  # noqa: BLE001
            out[oid] = ""
    return out


def get_ozon_attributes(settings: dict, offer_ids: list[str]) -> dict[str, dict]:
    client = build_client(settings)
    out: dict[str, dict] = {}
    limit = 1000
    for i in range(0, len(offer_ids), limit):
        chunk = offer_ids[i:i + limit]
        last_id = ""
        while True:
            r = client.get_products_attributes(offer_ids=chunk, limit=limit, last_id=last_id)
            batch = r.get("result") or []
            for it in batch:
                out[str(it.get("offer_id"))] = it
            last_id = r.get("last_id") or ""
            if not last_id or len(batch) < limit:
                break
    return out


def _stock_of(info: dict) -> int:
    st = (info.get("stocks") or {}).get("stocks") or []
    for s in st:
        if s.get("present") is not None:
            return int(s.get("present") or 0)
    return 0


def _to_cm(value: object, unit: object) -> int:
    """Ozon 尺寸归一成 cm（工具内部统一 cm；发布时再 ×10 转 mm 给 Ozon）。"""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return 0
    u = str(unit or "mm").strip().lower()
    factor = {"mm": 0.1, "cm": 1.0, "m": 100.0, "in": 2.54, "inch": 2.54}.get(u, 0.1)
    return int(round(v * factor))


def _video_from_complex(complex_attrs: object) -> str:
    """从 v4 complex_attributes 里取视频 URL（id 21841）。"""
    for a in (complex_attrs or []):
        if isinstance(a, dict) and int(a.get("id") or 0) == 21841:
            vals = a.get("values") or []
            if vals and isinstance(vals[0], dict):
                return str(vals[0].get("value") or "").strip()
    return ""


def _to_g(value: object, unit: object) -> int:
    """Ozon 克重归一成 g（工具内部统一 g；发布也按 g 送）。"""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return 0
    u = str(unit or "g").strip().lower()
    factor = {"g": 1.0, "kg": 1000.0, "mg": 0.001, "lb": 453.592, "pound": 453.592}.get(u, 1.0)
    return int(round(v * factor))


def fetch_warehouses(settings: dict) -> list[dict]:
    """拉 Ozon FBS/rFBS 仓库列表（/v2/warehouse/list，cursor + has_next 游标翻页）。"""
    client = build_client(settings)
    items: list[dict] = []
    cursor = ""
    while True:
        r = client.list_warehouses(cursor=cursor)
        batch = r.get("warehouses") or r.get("result") or []
        items.extend(batch)
        cursor = r.get("cursor") or ""
        if not r.get("has_next") or not cursor:
            break
    return items


# ---------- 功能⑤：FBS 备货发货 ----------
def pull_fbs_postings(settings: dict, status: str = "awaiting_packaging", days: int = 14) -> list[dict]:
    """拉 FBS 待处理单（v4 游标翻页），归一成 store.upsert_postings 形状。"""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415
    client = build_client(settings)
    now = datetime.now(timezone.utc)
    cf = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # 往前 30 天，确保逾期单（cutoff 已过的最紧急订单）也被拉入
    ct = (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    out, cursor = [], ""
    while True:
        r = client.list_unfulfilled_fbs_v4(cutoff_from=cf, cutoff_to=ct, status=status, cursor=cursor)
        result = r.get("result") or {}
        for p in (result.get("postings") or []):
            out.append({
                "posting_number": p.get("posting_number"),
                "ozon_order_id": str(p.get("order_id") or p.get("order_number") or ""),
                "status": p.get("status"), "ship_by": p.get("shipment_date"),
                "warehouse_id": None,
                "products": [{"offer_id": str(x.get("offer_id") or ""),
                              "sku": x.get("sku"),
                              "quantity": x.get("quantity") or 1} for x in (p.get("products") or [])],
                "raw": p,
            })
        cursor = result.get("cursor") or ""
        if not result.get("has_next") or not cursor:
            break
    return out


def ship_fbs(settings: dict, posting_number: str, packages: list[dict]) -> dict:
    return build_client(settings).ship_fbs_v4(posting_number, packages)


def fbs_label_pdf(settings: dict, posting_numbers: list[str]) -> bytes:
    return build_client(settings).get_package_label_pdf(posting_numbers)


def ozon_to_draft(info: dict, attrs: dict | None) -> dict:
    """合并 info/list + v4 attributes → 草稿 dict（source=ozon，已发布态）。纯函数、无 IO。"""
    attrs = attrs or {}
    imgs = list(info.get("images") or []) or list(info.get("primary_image") or [])
    return {
        "source": "ozon",
        "source_platform": "ozon",
        "ozon_product_id": info.get("id"),
        "offer_id": str(info.get("offer_id") or ""),
        "source_offer_id": str(info.get("offer_id") or ""),
        "source_url": "",
        "ozon_title": str(info.get("name") or ""),
        "source_title": str(info.get("name") or ""),
        "description": "",  # info/list 不返回描述；编辑时再补
        "category_id": str(info.get("description_category_id") or attrs.get("description_category_id") or ""),
        "type_id": str(info.get("type_id") or attrs.get("type_id") or ""),
        "price": str(info.get("price") or ""),
        "old_price": str(info.get("old_price") or ""),
        "stock": _stock_of(info),
        "images": imgs,
        # 内部统一：重量 g、尺寸 cm（列名 length_mm 为历史名，实存厘米）。
        # Ozon 返回按 dimension_unit/weight_unit，换算成 g/cm，避免 round-trip 失真。
        "weight_g": _to_g(attrs.get("weight"), attrs.get("weight_unit")),
        "length_mm": _to_cm(attrs.get("depth"), attrs.get("dimension_unit")),   # Ozon depth=长
        "width_mm": _to_cm(attrs.get("width"), attrs.get("dimension_unit")),
        "height_mm": _to_cm(attrs.get("height"), attrs.get("dimension_unit")),
        "attributes": attrs.get("attributes") or [],
        "video_url": _video_from_complex(attrs.get("complex_attributes")),
        "status": "published",
    }

