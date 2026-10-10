"""Analytics service — per-SKU 漏斗 / 流量趋势 / 搜索词分析。

纯函数（build_dashboard_rows、grand_total）+ 编排函数（dashboard、traffic、keywords）。
不进 App 类；进程内 TTL 缓存（dashboard/traffic 600s，keywords 21600s）。
多店通过传入 settings（由 router 调 _settings_for_store 得到）。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------- 进程内 TTL 缓存 ----------
_cache: dict[tuple, tuple[float, Any]] = {}
_DASHBOARD_TTL = 600      # 10 分钟
_KEYWORDS_TTL = 21600     # 6 小时


def _cache_get(key: tuple) -> Any | None:
    """返回缓存值，或 None（已过期/不存在）。"""
    entry = _cache.get(key)
    if entry is None:
        return None
    expire_at, value = entry
    if time.time() > expire_at:
        del _cache[key]
        return None
    return value


def _cache_set(key: tuple, value: Any, ttl: float) -> None:
    _cache[key] = (time.time() + ttl, value)


# ---------- 纯函数 ----------

def _ozon_product_url(sku: object) -> str:
    sku_str = str(sku or "").strip()
    if not sku_str.isdigit() or sku_str == "0":
        return ""
    return f"https://www.ozon.ru/product/{sku_str}/"


def build_dashboard_rows(
    infos: dict[str, dict],
    funnel: dict[Any, dict],
) -> list[dict]:
    """合并商品信息（offer_id→dict）+ 漏斗数据（sku→dict），计算 conv_cart_pct，打诊断标签。

    Args:
        infos:  {offer_id: {sku, title, price, stock, ...}}
        funnel: {sku(str 或 int): {exposure, sessions, cart, ordered_units, revenue}}

    Returns:
        按曝光量降序排列的行列表，每行含 diagnostics 列表。
    """
    # 统一 funnel key 为 str
    funnel_by_str: dict[str, dict] = {str(k): v for k, v in funnel.items()}

    rows: list[dict] = []
    for offer_id, meta in infos.items():
        sku = str(meta.get("sku") or "")
        f = funnel_by_str.get(sku, {})

        exposure = int(f.get("exposure") or 0)
        sessions = int(f.get("sessions") or 0)
        cart = int(f.get("cart") or 0)
        ordered_units = int(f.get("ordered_units") or 0)
        revenue = float(f.get("revenue") or 0.0)
        stock = meta.get("stock")
        stock_int = int(stock) if stock is not None else 0

        conv_cart_pct = round(cart / sessions * 100, 2) if sessions > 0 else 0.0

        diagnostics: list[str] = []
        if stock_int <= 0:
            diagnostics.append("缺货")
        if exposure <= 0:
            diagnostics.append("0曝光")
        elif exposure > 200 and ordered_units == 0:
            diagnostics.append("高曝光0转化")
        if cart > 0 and ordered_units == 0:
            diagnostics.append("加购未转化")

        rows.append({
            "offer_id": offer_id,
            "sku": int(sku) if sku.isdigit() else sku,
            "product_url": meta.get("product_url") or _ozon_product_url(sku),
            "title": meta.get("title") or meta.get("name") or "",
            "price": meta.get("price"),
            "stock": stock_int,
            "exposure": exposure,
            "sessions": sessions,
            "cart": cart,
            "conv_cart_pct": conv_cart_pct,
            "ordered_units": ordered_units,
            "revenue": revenue,
            "diagnostics": diagnostics,
        })

    rows.sort(key=lambda r: r["exposure"], reverse=True)
    return rows


def grand_total(rows: list[dict]) -> dict:
    """聚合所有行，返回全局漏斗汇总。"""
    n = len(rows)
    exposure = sum(r["exposure"] for r in rows)
    sessions = sum(r["sessions"] for r in rows)
    cart = sum(r["cart"] for r in rows)
    ordered_units = sum(r["ordered_units"] for r in rows)
    revenue = round(sum(r["revenue"] for r in rows), 2)
    conv_cart_pct = round(cart / sessions * 100, 2) if sessions > 0 else 0.0

    return {
        "sku_count": n,
        "sku_with_traffic": sum(1 for r in rows if r["exposure"] > 0),
        "exposure": exposure,
        "sessions": sessions,
        "cart": cart,
        "conv_cart_pct": conv_cart_pct,
        "ordered_units": ordered_units,
        "revenue": revenue,
    }


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_keyword_period(date_from: str, date_to: str) -> tuple[str, str, bool]:
    """Clamp search-query analytics to Ozon's latest available day.

    Product query details lag behind regular analytics. If the UI asks for a
    period ending today, preserve the selected window length but move the whole
    keyword window back so it ends at today - 3 days.
    """
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    if d_from > d_to:
        d_from = d_to

    latest = datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=3)
    if d_to <= latest:
        return d_from.isoformat(), d_to.isoformat(), False

    span = d_to - d_from
    adjusted_to = latest
    adjusted_from = adjusted_to - span
    return adjusted_from.isoformat(), adjusted_to.isoformat(), True


# ---------- 编排函数 ----------

def dashboard(settings: dict, date_from: str, date_to: str) -> dict:
    """拉取并汇总 per-SKU 漏斗数据（含 TTL 缓存）。

    Returns:
        {store, date_from, date_to, grand_total, rows, degraded}
    """
    from webui.ozon_client_adapter import (  # noqa: PLC0415
        build_client,
        fetch_analytics_sku,
        fetch_prices,
        fetch_stocks,
        list_ozon_products,
        get_ozon_info,
    )

    cid = str(settings.get("ozon_client_id") or "").strip()
    if not cid or not str(settings.get("ozon_api_key") or "").strip():
        raise ValueError("未配置 Ozon 店铺凭证")

    cache_key = (cid, "dashboard", date_from, date_to)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    client = build_client(settings)

    # 1. 拉所有 offer_id
    product_items = list_ozon_products(settings)
    offer_ids = [str(it.get("offer_id") or "") for it in product_items if it.get("offer_id")]

    if not offer_ids:
        result = {
            "store": cid,
            "date_from": date_from,
            "date_to": date_to,
            "grand_total": grand_total([]),
            "rows": [],
            "degraded": False,
        }
        _cache_set(cache_key, result, _DASHBOARD_TTL)
        return result

    # 2. 拉商品详情
    info_by_oid = get_ozon_info(settings, offer_ids)

    # 3. 拉活动价 & 库存（best-effort，失败不阻断）
    prices_by_oid: dict[str, dict] = {}
    stocks_by_oid: dict[str, int] = {}
    try:
        prices_by_oid = fetch_prices(client, offer_ids)
    except Exception:  # noqa: BLE001
        pass
    try:
        stocks_by_oid = fetch_stocks(client, offer_ids)
    except Exception:  # noqa: BLE001
        pass

    # 4. 拉 analytics 漏斗
    analytics_result = fetch_analytics_sku(client, date_from, date_to)
    degraded = analytics_result.get("degraded", False)
    # 转成 {sku: {...}} 供 build_dashboard_rows 使用
    funnel: dict[str, dict] = {row["sku"]: row for row in analytics_result.get("rows", [])}

    # 5. 组装 infos（附价格 & 库存）
    infos: dict[str, dict] = {}
    for oid, info in info_by_oid.items():
        sku = str(info.get("sku") or "")
        if not sku or sku == "0":
            continue
        pr = prices_by_oid.get(oid, {})
        stock_val = stocks_by_oid.get(oid)
        infos[oid] = {
            "sku": sku,
            "product_url": _ozon_product_url(sku),
            "title": info.get("name") or "",
            "price": pr.get("price") or info.get("price"),
            "price_action": pr.get("marketing_seller_price"),
            "stock": stock_val if stock_val is not None else (
                # fallback: 从 info.stocks 里取
                sum(int(s.get("present") or 0)
                    for s in ((info.get("stocks") or {}).get("stocks") or []))
            ),
        }

    rows = build_dashboard_rows(infos, funnel)
    result = {
        "store": cid,
        "date_from": date_from,
        "date_to": date_to,
        "grand_total": grand_total(rows),
        "rows": rows,
        "degraded": degraded,
    }
    _cache_set(cache_key, result, _DASHBOARD_TTL)
    return result


def traffic(settings: dict, date_from: str, date_to: str) -> dict:
    """拉取 per-SKU per-day 流量趋势（含 TTL 缓存）。

    Returns:
        {store, date_from, date_to, rows:[{sku, day, hits_view, session_view, hits_tocart, ordered_units}]}
    """
    from webui.ozon_client_adapter import build_client, fetch_analytics_traffic  # noqa: PLC0415

    cid = str(settings.get("ozon_client_id") or "").strip()
    if not cid or not str(settings.get("ozon_api_key") or "").strip():
        raise ValueError("未配置 Ozon 店铺凭证")

    cache_key = (cid, "traffic", date_from, date_to)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    client = build_client(settings)
    result_data = fetch_analytics_traffic(client, date_from, date_to)

    result = {
        "store": cid,
        "date_from": date_from,
        "date_to": date_to,
        "rows": result_data.get("rows", []),
    }
    _cache_set(cache_key, result, _DASHBOARD_TTL)
    return result


def keywords(settings: dict, date_from: str, date_to: str) -> dict:
    """拉取 per-SKU 搜索词（含 TTL 缓存，6h）。

    Returns:
        {store, date_from, date_to, by_sku:{sku:[{query, searches, ctr, position, orders, gmv}]}}
    """
    from webui.ozon_client_adapter import (  # noqa: PLC0415
        build_client,
        fetch_product_queries,
        list_ozon_products,
        get_ozon_info,
    )

    cid = str(settings.get("ozon_client_id") or "").strip()
    if not cid or not str(settings.get("ozon_api_key") or "").strip():
        raise ValueError("未配置 Ozon 店铺凭证")

    query_from, query_to, adjusted = normalize_keyword_period(date_from, date_to)

    cache_key = (cid, "keywords", query_from, query_to)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    client = build_client(settings)

    # 拉全部 SKU 列表
    product_items = list_ozon_products(settings)
    offer_ids = [str(it.get("offer_id") or "") for it in product_items if it.get("offer_id")]

    skus: list[str] = []
    if offer_ids:
        info_by_oid = get_ozon_info(settings, offer_ids)
        for info in info_by_oid.values():
            sku = str(info.get("sku") or "")
            if sku and sku != "0":
                skus.append(sku)

    if not skus:
        result = {
            "store": cid,
            "date_from": query_from,
            "date_to": query_to,
            "requested_date_from": date_from,
            "requested_date_to": date_to,
            "date_adjusted": adjusted,
            "by_sku": {},
        }
        _cache_set(cache_key, result, _KEYWORDS_TTL)
        return result

    queries_result = fetch_product_queries(client, skus, query_from, query_to)
    result = {
        "store": cid,
        "date_from": query_from,
        "date_to": query_to,
        "requested_date_from": date_from,
        "requested_date_to": date_to,
        "date_adjusted": adjusted,
        "by_sku": queries_result.get("by_sku", {}),
    }
    _cache_set(cache_key, result, _KEYWORDS_TTL)
    return result


# ---------- 多店并发聚合 ----------

def _run_per_store(fn, settings_list: list[dict], date_from: str, date_to: str) -> list[tuple[dict, Any]]:
    """并发对每个店 settings 跑 fn(settings, date_from, date_to)。

    缺凭证（ValueError）的店被跳过；其它异常也跳过该店（best-effort，不阻断全局）。
    全部店都失败 → raise ValueError。

    Returns:
        [(settings, result), ...]，仅含成功的店，保持输入顺序。
    """
    if not settings_list:
        raise ValueError("未配置 Ozon 店铺凭证")

    workers = min(8, len(settings_list))

    def _one(st: dict):
        return fn(st, date_from, date_to)

    results: list[Any] = [None] * len(settings_list)
    errors: list[Exception | None] = [None] * len(settings_list)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_one, st): i for i, st in enumerate(settings_list)}
        for fut, i in futures.items():
            try:
                results[i] = fut.result()
            except Exception as e:  # noqa: BLE001
                errors[i] = e

    ok: list[tuple[dict, Any]] = [
        (settings_list[i], results[i]) for i in range(len(settings_list)) if errors[i] is None
    ]
    if not ok:
        # 全失败：若有 ValueError（缺凭证）优先报它，否则报第一个错
        for e in errors:
            if isinstance(e, ValueError):
                raise e
        for e in errors:
            if e is not None:
                raise ValueError(str(e))
        raise ValueError("未配置 Ozon 店铺凭证")
    return ok


def dashboard_all(settings_list: list[dict], date_from: str, date_to: str) -> dict:
    """并发跑各店 dashboard 并合并。

    - rows 拼接，每行附 `store`=来源店 cid；
    - grand_total 用合并后 rows 重算；
    - store='all'，degraded=任一店 degraded；
    - 缺凭证店跳过，全部缺则 raise ValueError。
    """
    ok = _run_per_store(dashboard, settings_list, date_from, date_to)

    merged_rows: list[dict] = []
    degraded = False
    for _st, res in ok:
        store_cid = res.get("store")
        for r in res.get("rows", []):
            merged_rows.append({**r, "store": store_cid})
        if res.get("degraded"):
            degraded = True

    merged_rows.sort(key=lambda r: r["exposure"], reverse=True)
    return {
        "store": "all",
        "date_from": date_from,
        "date_to": date_to,
        "grand_total": grand_total(merged_rows),
        "rows": merged_rows,
        "degraded": degraded,
    }


def traffic_all(settings_list: list[dict], date_from: str, date_to: str) -> dict:
    """并发跑各店 traffic 并合并 rows（每行附 `store`）。"""
    ok = _run_per_store(traffic, settings_list, date_from, date_to)

    merged_rows: list[dict] = []
    for _st, res in ok:
        store_cid = res.get("store")
        for r in res.get("rows", []):
            merged_rows.append({**r, "store": store_cid})

    return {
        "store": "all",
        "date_from": date_from,
        "date_to": date_to,
        "rows": merged_rows,
    }


def keywords_all(settings_list: list[dict], date_from: str, date_to: str) -> dict:
    """并发跑各店 keywords 并合并 by_sku。

    同一 sku 跨店：用 `<store_cid>:<sku>` 作为 key 避免覆盖，保留每店搜索词列表。
    """
    ok = _run_per_store(keywords, settings_list, date_from, date_to)

    merged_by_sku: dict[str, list] = {}
    result_from = date_from
    result_to = date_to
    adjusted = False
    for _st, res in ok:
        store_cid = res.get("store")
        result_from = res.get("date_from") or result_from
        result_to = res.get("date_to") or result_to
        adjusted = adjusted or bool(res.get("date_adjusted"))
        for sku, lst in (res.get("by_sku") or {}).items():
            merged_by_sku[f"{store_cid}:{sku}"] = lst

    return {
        "store": "all",
        "date_from": result_from,
        "date_to": result_to,
        "requested_date_from": date_from,
        "requested_date_to": date_to,
        "date_adjusted": adjusted,
        "by_sku": merged_by_sku,
    }
