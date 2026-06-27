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
    return OzonSellerClient(client_id=client_id, api_key=api_key, timeout=60.0)


_client = build_client  # 兼容旧引用


def publish_items(settings: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    # 发布前把媒体 URL 从国内 ECS 代理换成 OSS 公网直链（Ozon 抓图服务器够不到代理地址→图空白）
    from webui.media_rehost import rewrite_item_media  # noqa: PLC0415
    items = [rewrite_item_media(it, settings) for it in (items or [])]
    return _client(settings).import_products(items)


def delete_products(settings: dict[str, Any], offer_ids: list[str]) -> dict[str, Any]:
    return _client(settings).delete_products(offer_ids)


def get_import_info(settings: dict[str, Any], task_id: int) -> dict[str, Any]:
    return _client(settings).get_import_info(task_id)


def import_by_sku(settings: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """官方复制：基于已有 Ozon SKU 复制建卡（POST /v1/product/import-by-sku）。"""
    return _client(settings).import_by_sku(items)


def copy_by_sku(settings: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """官方复制 + 轮询，返回 verdict（copyable/status/task_id/...）。
    copyable=False → 调用方转「原创建卡」分支。参数见 ozon_api.copy_flow.copy_by_sku。"""
    from ozon_api import copy_flow  # noqa: PLC0415
    return copy_flow.copy_by_sku(build_client(settings), **kwargs)


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


def get_attribute_values(
    settings: dict[str, Any], description_category_id: int, type_id: int,
    attribute_id: int, *, language: str = "RU", max_total: int = 2000,
) -> dict[str, Any]:
    return _client(settings).get_attribute_values(
        description_category_id, type_id, attribute_id, language=language, max_total=max_total
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


def _to_mm(value: object, unit: object) -> int:
    """Ozon 尺寸归一成 mm（工具内部统一 mm；发布时直发给 Ozon，不换算）。"""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return 0
    u = str(unit or "mm").strip().lower()
    factor = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4}.get(u, 1.0)
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


def fetch_delivery_methods(settings: dict, warehouse_ids: list[int]) -> list[dict]:
    """拉配送方式（/v2/delivery-method/list，filter.warehouse_ids 数组 + cursor 翻页），归一成 store 入参形状。
    v2 filter 收仓库 ID 数组，一次即可传全部仓库，无需逐仓多次调用。"""
    wids = [w for w in (warehouse_ids or []) if w is not None]
    if not wids:
        return []
    client = build_client(settings)
    out: list[dict] = []
    cursor = ""
    while True:
        r = client.list_delivery_methods(warehouse_ids=wids, cursor=cursor, limit=100)
        batch = r.get("result") or r.get("delivery_methods") or []
        for d in batch:
            dp = d.get("tpl_dropoff_point") or {}      # 自提点(PUDO)：用户最关心的地址在这里
            coord = dp.get("address_coordinates") or {}
            out.append({
                "delivery_method_id": d.get("id"),
                "warehouse_id": d.get("warehouse_id"),
                "name": d.get("name"),
                "status": d.get("status"),
                "provider_id": d.get("provider_id"),
                "template_id": d.get("template_id"),
                "tpl_integration_type": d.get("tpl_integration_type"),
                "is_express": d.get("is_express"),
                "cutoff": d.get("cutoff"),
                "sla_cut_in": d.get("sla_cut_in"),
                "dropoff_name": dp.get("name"),
                "dropoff_code": dp.get("code"),
                "dropoff_address": dp.get("address"),
                "dropoff_lat": coord.get("latitude"),
                "dropoff_lng": coord.get("longitude"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
                "raw": d,
            })
        cursor = r.get("cursor") or ""
        if not r.get("has_next") or not cursor:
            break
    return out


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


# ---------- 功能⑥：Analytics 数据拉取 ----------

# /v1/analytics/data 漏斗指标（dimension=sku）
_ANALYTICS_METRICS = [
    "hits_view", "session_view", "hits_tocart",
    "ordered_units", "revenue",
]

# /v1/analytics/data 降级指标（Premium 不可用时）
_ANALYTICS_METRICS_DEGRADED = ["ordered_units", "revenue"]

# /v1/analytics/data 流量趋势指标（dimension=[sku, day]）
_TRAFFIC_METRICS = [
    "hits_view", "session_view", "hits_tocart", "ordered_units",
]


def fetch_analytics_sku(client: "OzonSellerClient", date_from: str, date_to: str) -> dict:
    """拉 per-SKU 漏斗数据（dimension=[sku]）。
    返回 {rows: [{sku, exposure, sessions, cart, ordered_units, revenue}], degraded: bool}。
    403 → 降级到 ordered_units/revenue（degraded=True）；429 → 等 62s 重试。
    """
    import time  # noqa: PLC0415

    def _do_request(metrics: list[str]) -> tuple[int, dict]:
        body = {
            "date_from": date_from,
            "date_to": date_to,
            "dimension": ["sku"],
            "metrics": metrics,
            "sort": [{"key": metrics[0], "order": "DESC"}],
            "limit": 1000,
            "offset": 0,
        }
        # 429 重试（分析接口每账号每分钟限 1 次）
        for attempt in range(4):
            try:
                r = client.request("/v1/analytics/data", body)
                return 200, r
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if code == 429 and attempt < 3:
                    time.sleep(62)
                    continue
                if code == 403:
                    return 403, {}
                if code:
                    return code, {}
                raise
        return 429, {}

    status, data = _do_request(_ANALYTICS_METRICS)
    degraded = False
    if status == 403:
        degraded = True
        status, data = _do_request(_ANALYTICS_METRICS_DEGRADED)
        if status != 200:
            return {"rows": [], "degraded": degraded}

    metrics_used = _ANALYTICS_METRICS_DEGRADED if degraded else _ANALYTICS_METRICS
    rows = []
    for r in (data.get("result") or {}).get("data") or []:
        dims = r.get("dimensions") or [{}]
        sku = str(dims[0].get("id") or "")
        if not sku:
            continue
        vals = r.get("metrics") or []
        m = dict(zip(metrics_used, vals))
        rows.append({
            "sku": sku,
            "exposure": int(m.get("hits_view") or 0),
            "sessions": int(m.get("session_view") or 0),
            "cart": int(m.get("hits_tocart") or 0),
            "ordered_units": int(m.get("ordered_units") or 0),
            "revenue": float(m.get("revenue") or 0.0),
        })
    return {"rows": rows, "degraded": degraded}


def fetch_analytics_traffic(client: "OzonSellerClient", date_from: str, date_to: str) -> dict:
    """拉 per-SKU per-day 流量趋势（dimension=[sku, day]）。
    返回 {rows: [{sku, day, hits_view, session_view, hits_tocart, ordered_units}]}。
    """
    import time  # noqa: PLC0415

    body = {
        "date_from": date_from,
        "date_to": date_to,
        "dimension": ["sku", "day"],
        "metrics": _TRAFFIC_METRICS,
        "limit": 1000,
        "offset": 0,
        "sort": [{"key": "hits_view", "order": "DESC"}],
    }
    for attempt in range(4):
        try:
            data = client.request("/v1/analytics/data", body)
            break
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if code == 429 and attempt < 3:
                time.sleep(62)
                continue
            if code == 403:
                return {"rows": []}
            if code:
                return {"rows": []}
            raise
    else:
        return {"rows": []}

    rows = []
    for r in (data.get("result") or {}).get("data") or []:
        dims = r.get("dimensions") or [{}, {}]
        sku = str(dims[0].get("id") or "") if len(dims) > 0 else ""
        day = str(dims[1].get("id") or "") if len(dims) > 1 else ""
        if not sku:
            continue
        vals = r.get("metrics") or []
        m = dict(zip(_TRAFFIC_METRICS, vals))
        rows.append({
            "sku": sku,
            "day": day,
            "hits_view": int(m.get("hits_view") or 0),
            "session_view": int(m.get("session_view") or 0),
            "hits_tocart": int(m.get("hits_tocart") or 0),
            "ordered_units": int(m.get("ordered_units") or 0),
        })
    return {"rows": rows}


def fetch_product_queries(client: "OzonSellerClient", skus: list[str], date_from: str, date_to: str) -> dict:
    """拉 per-SKU 搜索词（/v1/analytics/product-queries/details，page 翻页）。
    返回 {by_sku: {sku: [{query, searches, ctr, position, orders, gmv}]}}。
    """
    import time  # noqa: PLC0415

    by_sku: dict[str, list[dict]] = {}
    page = 0
    while True:
        body = {
            "date_from": f"{date_from}T00:00:00Z",
            "date_to": f"{date_to}T23:59:59Z",
            "skus": skus,
            "page": page,
            "page_size": 100,
            "limit_by_sku": 15,
            "sort_by": "BY_SEARCHES",
            "sort_dir": "DESC",
        }
        for attempt in range(6):
            try:
                r = client.request("/v1/analytics/product-queries/details", body)
                break
            except Exception as exc:  # noqa: BLE001
                code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
                if code == 429 and attempt < 5:
                    time.sleep(2 + attempt * 2)
                    continue
                if code == 403:
                    return {"by_sku": {}}
                return {"by_sku": {}}
        else:
            break

        for q in (r.get("queries") or []):
            sku_key = str(q.get("sku") or "")
            by_sku.setdefault(sku_key, []).append({
                "query": q.get("query") or "",
                "searches": int(q.get("unique_search_users") or 0),
                "ctr": float(q.get("view_conversion") or 0.0),
                "position": float(q.get("position") or 0.0),
                "orders": int(q.get("order_count") or 0),
                "gmv": float(q.get("gmv") or 0.0),
            })
        page_count = int(r.get("page_count") or 1)
        page += 1
        if page >= page_count:
            break

    return {"by_sku": by_sku}


def fetch_prices(client: "OzonSellerClient", offer_ids: list[str]) -> dict[str, dict]:
    """/v5 活动价：{offer_id: {marketing_seller_price, price, old_price}}（cursor 翻页）。"""
    out: dict[str, dict] = {}
    for i in range(0, len(offer_ids), 1000):
        batch = offer_ids[i:i + 1000]
        cursor = ""
        while True:
            try:
                d = client.request(
                    "/v5/product/info/prices",
                    {"filter": {"offer_id": batch, "visibility": "ALL"}, "limit": 1000, "cursor": cursor},
                )
            except Exception:  # noqa: BLE001
                break
            for it in (d.get("items") or []):
                pr = it.get("price") or {}
                out[str(it.get("offer_id") or "")] = {
                    "marketing_seller_price": pr.get("marketing_seller_price"),
                    "price": pr.get("price"),
                    "old_price": pr.get("old_price"),
                }
            cursor = d.get("cursor") or ""
            if not cursor:
                break
    return out


def fetch_stocks(client: "OzonSellerClient", offer_ids: list[str]) -> dict[str, int]:
    """/v4 库存：{offer_id: present 求和}（cursor 翻页，best-effort）。"""
    out: dict[str, int] = {}
    for i in range(0, len(offer_ids), 1000):
        batch = offer_ids[i:i + 1000]
        cursor = ""
        while True:
            try:
                d = client.request(
                    "/v4/product/info/stocks",
                    {"filter": {"offer_id": batch, "visibility": "ALL"}, "limit": 1000, "cursor": cursor},
                )
            except Exception:  # noqa: BLE001
                break
            for it in (d.get("items") or []):
                present = sum(int(s.get("present") or 0) for s in (it.get("stocks") or []))
                out[str(it.get("offer_id") or "")] = present
            cursor = d.get("cursor") or ""
            if not cursor:
                break
    return out


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
        # 内部统一：重量 g、尺寸 mm（列名 length_mm 名实相符）。
        # Ozon 返回按 dimension_unit/weight_unit，换算成 g/mm，避免 round-trip 失真。
        "weight_g": _to_g(attrs.get("weight"), attrs.get("weight_unit")),
        "length_mm": _to_mm(attrs.get("depth"), attrs.get("dimension_unit")),   # Ozon depth=长
        "width_mm": _to_mm(attrs.get("width"), attrs.get("dimension_unit")),
        "height_mm": _to_mm(attrs.get("height"), attrs.get("dimension_unit")),
        "attributes": attrs.get("attributes") or [],
        "video_url": _video_from_complex(attrs.get("complex_attributes")),
        "status": "published",
    }

