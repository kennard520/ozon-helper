"""Analytics router — SKU 漏斗 / 流量趋势 / 搜索词三端点。

端点全部 POST（body 传参），缺凭证返回 400，其他异常返回 500。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.services import analytics_service

router = APIRouter()


def _settings(store_client_id: str | None) -> dict:
    APP = app_instance.APP
    if store_client_id:
        return APP._settings_for_store(store_client_id)
    return APP.store.get_settings()


def _all_store_settings() -> list[dict] | None:
    """当未指定店且配置了 ≥2 个店时，返回各店 settings 列表（供 _all 并发聚合）；
    否则返回 None（维持单店路径）。"""
    APP = app_instance.APP
    stores = APP.store.get_settings().get("ozon_stores") or []
    if len(stores) < 2:
        return None
    out: list[dict] = []
    for st in stores:
        cid = str(st.get("client_id") or "").strip()
        if not cid:
            continue
        try:
            out.append(APP._settings_for_store(cid))
        except ValueError:
            continue
    return out or None


@router.post("/api/analytics/dashboard")
def analytics_dashboard(body: dict) -> dict:
    b = body or {}
    date_from = b.get("date_from") or ""
    date_to = b.get("date_to") or ""
    cid = b.get("store_client_id")
    try:
        if not cid and (settings_list := _all_store_settings()):
            return analytics_service.dashboard_all(settings_list, date_from, date_to)
        return analytics_service.dashboard(_settings(cid), date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/analytics/traffic")
def analytics_traffic(body: dict) -> dict:
    b = body or {}
    date_from = b.get("date_from") or ""
    date_to = b.get("date_to") or ""
    cid = b.get("store_client_id")
    try:
        if not cid and (settings_list := _all_store_settings()):
            return analytics_service.traffic_all(settings_list, date_from, date_to)
        return analytics_service.traffic(_settings(cid), date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/analytics/keywords")
def analytics_keywords(body: dict) -> dict:
    b = body or {}
    date_from = b.get("date_from") or ""
    date_to = b.get("date_to") or ""
    cid = b.get("store_client_id")
    try:
        if not cid and (settings_list := _all_store_settings()):
            return analytics_service.keywords_all(settings_list, date_from, date_to)
        return analytics_service.keywords(_settings(cid), date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
