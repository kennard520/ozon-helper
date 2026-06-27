from __future__ import annotations

from fastapi import APIRouter, HTTPException

from webui import app_instance

router = APIRouter()


@router.get("/api/category/search")
def category_search(q: str = "", limit: int = 500) -> dict:
    try:
        return app_instance.APP.search_category(q, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/category/tree")
def category_tree() -> dict:
    try:
        return app_instance.APP.category_tree()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/category/resolve")
def category_resolve(cat: int, type: int) -> dict:
    try:
        return app_instance.APP.resolve_category(cat, type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/category/attributes")
def category_attributes(cat: int, type: int, language: str = "ZH_HANS") -> dict:
    try:
        return app_instance.APP.category_attributes(cat, type, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/attribute/values/search")
def attribute_values_search(cat: int, type: int, attr: int, q: str = "", language: str = "ZH_HANS") -> dict:
    try:
        return app_instance.APP.brand_search(cat, type, attr, q, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/attribute/values")
def attribute_values(cat: int, type: int, attr: int, language: str = "ZH_HANS") -> dict:
    """某属性全量字典选项(下拉用)：先查 DB 缓存，缺了拉 Ozon 回写。oversized 时 values 空、前端回退实时搜。"""
    try:
        return app_instance.APP.attribute_value_options(cat, type, attr, language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
