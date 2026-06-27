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


@router.post("/api/analytics/dashboard")
def analytics_dashboard(body: dict) -> dict:
    b = body or {}
    try:
        return analytics_service.dashboard(
            _settings(b.get("store_client_id")),
            b.get("date_from") or "",
            b.get("date_to") or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/analytics/traffic")
def analytics_traffic(body: dict) -> dict:
    b = body or {}
    try:
        return analytics_service.traffic(
            _settings(b.get("store_client_id")),
            b.get("date_from") or "",
            b.get("date_to") or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/analytics/keywords")
def analytics_keywords(body: dict) -> dict:
    b = body or {}
    try:
        return analytics_service.keywords(
            _settings(b.get("store_client_id")),
            b.get("date_from") or "",
            b.get("date_to") or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
