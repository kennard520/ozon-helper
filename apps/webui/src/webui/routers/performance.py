from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.services import performance_service

router = APIRouter()


def _settings(store_client_id: str | None) -> dict:
    APP = app_instance.APP
    if store_client_id:
        return APP._settings_for_store(store_client_id)
    return APP.store.get_settings()


@router.get("/api/performance/campaigns")
def performance_campaigns(store_client_id: str | None = None) -> dict:
    try:
        return performance_service.campaigns(_settings(store_client_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/performance/campaigns/{campaign_id}/products")
def performance_campaign_products(
    campaign_id: str,
    store_client_id: str | None = None,
    campaign_type: str = "",
) -> dict:
    try:
        return performance_service.campaign_products(_settings(store_client_id), campaign_id, campaign_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/performance/product-promotions")
def performance_product_promotions(store_client_id: str | None = None, limit: int = 1000) -> dict:
    try:
        return performance_service.product_promotions(_settings(store_client_id), limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/api/performance/operations/preview")
def performance_operation_preview(body: dict, store_client_id: str | None = None) -> dict:
    try:
        return performance_service.operation_preview(_settings(store_client_id), body or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/performance/reviews-promo/disable")
def performance_disable_reviews_promo(body: dict, store_client_id: str | None = None) -> dict:
    try:
        return performance_service.disable_reviews_promo(_settings(store_client_id), body or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/api/performance/operations/commit")
def performance_operation_commit(body: dict, store_client_id: str | None = None) -> dict:
    try:
        return performance_service.operation_commit(_settings(store_client_id), body or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))
