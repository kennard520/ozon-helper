from __future__ import annotations

from typing import Any

from ozon_api import OzonPerformanceClient, OzonSellerClient


ALLOWED_OPERATIONS = {
    "add_products",
    "remove_products",
    "enable_search_promo",
    "disable_search_promo",
}


def _client(settings: dict[str, Any]) -> OzonPerformanceClient:
    client_id = str(settings.get("performance_client_id") or "").strip()
    client_secret = str(settings.get("performance_client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ValueError("请先在系统设置配置 Ozon Performance API 凭证")
    return OzonPerformanceClient(client_id=client_id, client_secret=client_secret, timeout=60.0)


def _seller_client(settings: dict[str, Any]) -> OzonSellerClient:
    client_id = str(settings.get("ozon_client_id") or "").strip()
    api_key = str(settings.get("ozon_api_key") or "").strip()
    if not client_id or not api_key:
        raise ValueError("请先在系统设置配置 Ozon Seller API 店铺凭证")
    return OzonSellerClient(client_id=client_id, api_key=api_key, timeout=60.0)


def _first_value(src: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in src and src[key] not in (None, ""):
            return src[key]
    return ""


def _normalize_campaign(item: dict[str, Any]) -> dict[str, Any]:
    campaign_id = str(_first_value(item, "id", "campaignId", "campaign_id"))
    title = str(_first_value(item, "title", "name", "campaignName", "campaign_name"))
    payment_type = str(_first_value(item, "paymentType", "payment_type", "paymentMethod"))
    adv_type = str(_first_value(item, "advObjectType", "adv_object_type", "objectType"))
    placement = str(_first_value(item, "placement", "campaignPlacement"))
    is_search_promo = (
        "SEARCH_PROMO" in f"{payment_type} {adv_type} {placement}".upper()
        or "CPO" in payment_type.upper()
    )
    return {
        "id": campaign_id,
        "title": title or campaign_id,
        "state": str(_first_value(item, "state", "status")),
        "adv_object_type": adv_type,
        "payment_type": payment_type,
        "is_search_promo": is_search_promo,
        "products_count": int(_first_value(item, "productsCount", "products_count", "skuCount") or 0),
        "raw": item,
    }


def _normalize_product(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": str(_first_value(item, "sku", "productId", "product_id")),
        "offer_id": str(_first_value(item, "offerId", "offer_id")),
        "title": str(_first_value(item, "title", "name")),
        "status": str(_first_value(item, "status", "state")),
        "bid": str(_first_value(item, "bid", "selectedBid", "currentBid")),
        "raw": item,
    }


def _items(payload: dict[str, Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip()
        offer_id = str(item.get("offer_id") or item.get("offerId") or "").strip()
        if not sku and not offer_id:
            continue
        key = (sku, offer_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"sku": sku, "offer_id": offer_id})
    return normalized


def _validate_operation(payload: dict[str, Any]) -> str:
    operation = str(payload.get("operation") or "").strip()
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported operation: {operation}")
    return operation


def campaigns(settings: dict[str, Any]) -> dict[str, Any]:
    client = _client(settings)
    campaigns_by_id: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    queries = [
        {"advObjectType": "SKU"},
        {"advObjectType": "SEARCH_PROMO"},
    ]
    for query in queries:
        try:
            data = client.list_campaigns(**query)
            source = data.get("list") or data.get("campaigns") or data.get("items") or []
            normalized = [_normalize_campaign(it) for it in source if isinstance(it, dict)]
            for item in normalized:
                campaigns_by_id[item["id"]] = item
            diagnostics.append({"query": query, "count": len(normalized)})
        except Exception as exc:  # noqa: BLE001
            diagnostics.append({"query": query, "error": str(exc)})
    return {"campaigns": list(campaigns_by_id.values()), "diagnostics": diagnostics}


def _promotion_enabled(item: dict[str, Any], promo_type: str) -> bool:
    for promo in item.get("promotions") or []:
        if str(promo.get("type") or "") == promo_type:
            return bool(promo.get("is_enabled"))
    return False


def _normalize_seller_product(item: dict[str, Any]) -> dict[str, Any]:
    promotions = [
        {
            "type": str(p.get("type") or ""),
            "is_enabled": bool(p.get("is_enabled")),
        }
        for p in item.get("promotions") or []
        if isinstance(p, dict)
    ]
    return {
        "sku": str(_first_value(item, "sku")),
        "offer_id": str(_first_value(item, "offer_id", "offerId")),
        "product_id": str(_first_value(item, "id", "product_id", "productId")),
        "title": str(_first_value(item, "name", "title")),
        "promotions": promotions,
        "reviews_promo_enabled": _promotion_enabled(item, "REVIEWS_PROMO"),
    }


def product_promotions(settings: dict[str, Any], *, limit: int = 1000) -> dict[str, Any]:
    client = _seller_client(settings)
    max_items = max(1, min(int(limit or 1000), 1000))
    listed: list[dict[str, Any]] = []
    last_id = ""
    while len(listed) < max_items:
        data = client.list_products(last_id=last_id, limit=min(1000, max_items - len(listed)))
        result = data.get("result") or {}
        batch = result.get("items") or []
        listed.extend([it for it in batch if isinstance(it, dict)])
        next_last_id = str(result.get("last_id") or "")
        if not batch or not next_last_id or next_last_id == last_id:
            break
        last_id = next_last_id

    products: list[dict[str, Any]] = []
    product_ids = [it.get("product_id") for it in listed if it.get("product_id")]
    for start in range(0, len(product_ids), 100):
        data = client.get_products_info(product_ids=product_ids[start:start + 100])
        source = data.get("items") or (data.get("result") or {}).get("items") or []
        products.extend(_normalize_seller_product(it) for it in source if isinstance(it, dict))

    reviews_enabled = sum(1 for p in products if p["reviews_promo_enabled"])
    return {
        "products": products,
        "summary": {
            "total": len(products),
            "reviews_promo_enabled": reviews_enabled,
        },
    }


def _primary_image(info: dict[str, Any], attrs: dict[str, Any]) -> str:
    value = attrs.get("primary_image")
    if value:
        return str(value)
    raw = info.get("primary_image")
    if isinstance(raw, list):
        return str(raw[0]) if raw else ""
    return str(raw or "")


def _reviews_promo_import_item(info: dict[str, Any], attrs: dict[str, Any], action: str) -> dict[str, Any]:
    item = {
        "offer_id": str(info.get("offer_id") or attrs.get("offer_id") or ""),
        "name": info.get("name") or attrs.get("name"),
        "description_category_id": info.get("description_category_id") or attrs.get("description_category_id"),
        "type_id": info.get("type_id") or attrs.get("type_id"),
        "price": info.get("price"),
        "old_price": info.get("old_price") or "0",
        "currency_code": info.get("currency_code") or "CNY",
        "vat": info.get("vat") or "0",
        "height": attrs.get("height"),
        "depth": attrs.get("depth"),
        "width": attrs.get("width"),
        "dimension_unit": attrs.get("dimension_unit") or "mm",
        "weight": attrs.get("weight"),
        "weight_unit": attrs.get("weight_unit") or "g",
        "images": attrs.get("images") or info.get("images") or [],
        "primary_image": _primary_image(info, attrs),
        "attributes": attrs.get("attributes") or [],
        "complex_attributes": attrs.get("complex_attributes") or [],
        "barcode": attrs.get("barcode") or "",
        "barcodes": attrs.get("barcodes") or [],
        "color_image": attrs.get("color_image") or "",
        "reviews_promo": action,
    }
    return {k: v for k, v in item.items() if v not in (None, "")}


def disable_reviews_promo(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    client = _seller_client(settings)
    items = _items(payload)
    if not items:
        raise ValueError("请选择至少一个商品")
    results: list[dict[str, Any]] = []
    for item in items:
        offer_id = str(item.get("offer_id") or "").strip()
        if not offer_id:
            results.append({**item, "ok": False, "message": "缺少 offer_id"})
            continue
        try:
            info_items = client.get_products_info(offer_ids=[offer_id]).get("items") or []
            attr_items = client.get_products_attributes(offer_ids=[offer_id], limit=1).get("result") or []
            if not info_items or not attr_items:
                results.append({**item, "ok": False, "message": "未找到商品详情"})
                continue
            import_item = _reviews_promo_import_item(info_items[0], attr_items[0], "disable")
            data = client.import_products([import_item])
            task_id = (data.get("result") or {}).get("task_id")
            results.append({**item, "ok": True, "message": f"已提交关闭任务 {task_id or ''}".strip(), "task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            results.append({**item, "ok": False, "message": str(exc)})
    return {"operation": "disable_reviews_promo", "results": results}


def campaign_products(settings: dict[str, Any], campaign_id: str, campaign_type: str = "") -> dict[str, Any]:
    client = _client(settings)
    if "search" in str(campaign_type or "").lower():
        data = client.search_promo_products({"campaign_id": str(campaign_id)})
    else:
        data = client.campaign_products(str(campaign_id))
    source = data.get("products") or data.get("items") or data.get("list") or []
    return {
        "campaign_id": str(campaign_id),
        "products": [_normalize_product(it) for it in source if isinstance(it, dict)],
    }


def operation_preview(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    _validate_operation(payload)
    if not str(settings.get("performance_client_id") or "").strip() or not str(settings.get("performance_client_secret") or "").strip():
        raise ValueError("请先在系统设置配置 Ozon Performance API 凭证")
    items = _items(payload)
    if not items:
        raise ValueError("请选择或输入至少一个商品")
    return {
        "operation": str(payload.get("operation")),
        "campaign_id": str(payload.get("campaign_id") or ""),
        "campaign_title": str(payload.get("campaign_title") or ""),
        "count": len(items),
        "items": items,
        "warnings": [],
    }


def _commit_one(client: Any, operation: str, campaign_id: str, item: dict[str, str]) -> None:
    if operation == "add_products":
        client.add_campaign_products(campaign_id, [item])
    elif operation == "remove_products":
        client.delete_campaign_products(campaign_id, [item])
    elif operation == "enable_search_promo":
        client.enable_search_promo([item])
    elif operation == "disable_search_promo":
        client.disable_search_promo([item])
    else:
        raise ValueError(f"unsupported operation: {operation}")


def operation_commit(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    operation = _validate_operation(payload)
    campaign_id = str(payload.get("campaign_id") or "")
    items = _items(payload)
    if not items:
        raise ValueError("请选择或输入至少一个商品")
    client = _client(settings)
    results: list[dict[str, Any]] = []
    for item in items:
        try:
            _commit_one(client, operation, campaign_id, item)
            results.append({**item, "ok": True, "message": ""})
        except Exception as exc:  # noqa: BLE001
            results.append({**item, "ok": False, "message": str(exc)})
    return {"operation": operation, "campaign_id": campaign_id, "results": results}
