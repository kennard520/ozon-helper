from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from webui import app_instance
from webui.models import DefaultWarehouseIn, FbsPullIn, OzonPullIn, ProcStateIn, ShipIn

router = APIRouter()


@router.post("/api/ozon/pull")
def ozon_pull(body: OzonPullIn) -> dict:
    try:
        return app_instance.APP.pull_ozon_products(body.visibility)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/warehouses")
def warehouses(store_client_id: str | None = None) -> dict:
    return app_instance.APP.list_warehouses(store_client_id)


@router.post("/api/warehouses/sync")
def warehouses_sync(store_client_id: str | None = None) -> dict:
    try:
        return app_instance.APP.sync_warehouses(store_client_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/warehouses/default")
def warehouses_default(body: DefaultWarehouseIn, store_client_id: str | None = None) -> dict:
    return app_instance.APP.set_default_warehouse(body.warehouse_id, store_client_id)


# ---------- 功能⑤：FBS 备货发货 ----------
@router.post("/api/fbs/pull")
def fbs_pull(body: FbsPullIn, store_client_id: str | None = None) -> dict:
    try:
        return app_instance.APP.pull_fbs(body.status, body.days, store_client_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/fbs/procurement")
def fbs_procurement(store_client_id: str | None = None) -> dict:
    return app_instance.APP.list_procurement(store_client_id)


@router.post("/api/fbs/procurement/{pid}/state")
def fbs_proc_state(pid: int, body: ProcStateIn, store_client_id: str | None = None) -> dict:
    return app_instance.APP.set_procurement_state(pid, body.purchase_state, body.note, store_client_id)


@router.post("/api/fbs/ship")
def fbs_ship(body: ShipIn, store_client_id: str | None = None) -> dict:
    try:
        return app_instance.APP.ship_posting(body.posting_number, store_client_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/fbs/label")
def fbs_label(posting: str, store_client_id: str | None = None) -> Response:
    try:
        pdf = app_instance.APP.fbs_label(posting, store_client_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{posting}.pdf"'})
