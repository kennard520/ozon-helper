from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance
from webui.models import OzonProductImportIn, OzonProductSyncIn

router = APIRouter()

_CONFIG_ERROR_DETAIL = "Ozon 店铺配置无效"
_NOT_FOUND_DETAIL = "未找到指定的 Ozon 商品"


@router.post("/api/ozon-products/import-by-sku")
def import_by_sku(body: OzonProductImportIn) -> dict:
    try:
        return app_instance.APP.import_ozon_product_by_sku(
            body.sku,
            body.store_client_id,
            body.selected_fields,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_CONFIG_ERROR_DETAIL) from exc


@router.post("/api/ozon-products/sync")
def sync_products(body: OzonProductSyncIn) -> dict:
    try:
        return app_instance.APP.sync_ozon_products(
            body.store_client_id,
            body.visibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_CONFIG_ERROR_DETAIL) from exc
