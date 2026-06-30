from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from webui import app_instance
from webui.models import CommissionMapIn

router = APIRouter()


@router.get("/api/commission-map")
def get_commission_map(cat: int, type: int) -> dict:
    try:
        return app_instance.APP.get_commission_map(cat, type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/commission-map")
def save_commission_map(payload: CommissionMapIn) -> dict:
    return app_instance.APP.save_commission_map(payload.model_dump())


# realFBS 运费路线表（智能定价用）：可导出 CSV → Excel 维护 → 导入覆盖
@router.get("/api/realfbs-routes")
def get_realfbs_routes() -> dict:
    return app_instance.APP.realfbs_routes()


@router.get("/api/realfbs-routes/export")
def export_realfbs_routes() -> Response:
    csv_text = app_instance.APP.export_realfbs_routes_csv()
    return Response(
        content=csv_text, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=realfbs_routes.csv"},
    )


@router.post("/api/realfbs-routes/import")
async def import_realfbs_routes(request: Request) -> dict:
    body = await request.json()
    try:
        return app_instance.APP.import_realfbs_routes(str((body or {}).get("csv") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# realFBS 佣金类目表（智能定价用，只 FBS=RFBS）：导出 xlsx → Excel 维护 → 导入覆盖；
# 也可直接丢 Ozon 官方 Tarifs xlsx 导入（自动认 'MP Tree Tarifs CN' sheet 的 RFBS 三档）
@router.get("/api/commission-categories")
def get_commission_categories() -> dict:
    return app_instance.APP.commission_categories()


@router.get("/api/commission-categories/export")
def export_commission_categories() -> Response:
    data = app_instance.APP.export_commission_categories_xlsx()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=commission_categories.xlsx"},
    )


@router.post("/api/commission-categories/import")
async def import_commission_categories(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    try:
        return app_instance.APP.import_commission_categories_xlsx(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
