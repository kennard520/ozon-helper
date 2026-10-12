from __future__ import annotations

import json as json_lib
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SELLER_API_BASE_URL = "https://api-seller.ozon.ru"


class ResponseLike(Protocol):
    status_code: int
    text: str

    def json(self) -> dict[str, Any]:
        ...


class Transport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> ResponseLike:
        ...


@dataclass
class SimpleResponse:
    status_code: int
    text: str

    def json(self) -> dict[str, Any]:
        if not self.text:
            return {}
        data = json_lib.loads(self.text)
        if not isinstance(data, dict):
            return {"data": data}
        return data


class UrlLibTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> SimpleResponse:
        body = json_lib.dumps(json, ensure_ascii=False).encode("utf-8")
        req = Request(url=url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as res:  # noqa: S310 - caller controls endpoint config.
                text = res.read().decode("utf-8")
                return SimpleResponse(status_code=res.status, text=text)
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return SimpleResponse(status_code=exc.code, text=text)


class OzonApiError(RuntimeError):
    def __init__(self, status_code: int, payload: dict[str, Any], text: str) -> None:
        self.status_code = status_code
        self.payload = payload
        self.text = text
        message = payload.get("message") or payload.get("error") or text[:300] or "Ozon API error"
        super().__init__(f"Ozon API returned HTTP {status_code}: {message}")


class OzonSellerClient:
    def __init__(
        self,
        client_id: str,
        api_key: str,
        *,
        base_url: str = SELLER_API_BASE_URL,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        if not client_id:
            raise ValueError("client_id is required")
        if not api_key:
            raise ValueError("api_key is required")
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport or UrlLibTransport()

    def request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.startswith("/"):
            path = f"/{path}"
        response = self.transport.request(
            method="POST",
            url=f"{self.base_url}{path}",
            headers={
                "Client-Id": self.client_id,
                "Api-Key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload or {},
            timeout=self.timeout,
        )
        data = response.json()
        if response.status_code >= 400:
            raise OzonApiError(response.status_code, data, response.text)
        return data

    def list_warehouses(self, *, cursor: str = "", limit: int = 100) -> dict[str, Any]:
        # /v1/warehouse/list 已被 Ozon 废弃（返回 "obsolete method cannot be used"）→ 用 /v2
        # /v2/warehouse/list 支持 cursor + has_next 游标翻页
        body: dict[str, Any] = {"limit": limit}
        if cursor:
            body["cursor"] = cursor
        return self.request("/v2/warehouse/list", body)

    def list_delivery_methods(
        self, *, warehouse_ids: list[Any] | None = None, provider_ids: list[Any] | None = None,
        delivery_method_ids: list[Any] | None = None, status: list[str] | None = None,
        cursor: str = "", limit: int = 100, sort_dir: str = "ASC",
    ) -> dict[str, Any]:
        # /v1/delivery-method/list 将于 2026-04-07 停用 → 用 /v2。
        # v2：filter 各字段为数组（warehouse_ids 等均为字符串），cursor 游标翻页，响应带 has_next。
        filt: dict[str, Any] = {}
        if warehouse_ids:
            filt["warehouse_ids"] = [str(w) for w in warehouse_ids]
        if provider_ids:
            filt["provider_ids"] = [str(p) for p in provider_ids]
        if delivery_method_ids:
            filt["delivery_method_ids"] = [str(d) for d in delivery_method_ids]
        if status:
            filt["status"] = list(status)
        body: dict[str, Any] = {"filter": filt, "limit": limit, "sort_dir": sort_dir}
        if cursor:
            body["cursor"] = cursor
        return self.request("/v2/delivery-method/list", body)

    def import_products(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("/v3/product/import", {"items": items})

    def get_import_info(self, task_id: int) -> dict[str, Any]:
        return self.request("/v1/product/import/info", {"task_id": int(task_id)})

    def import_by_sku(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        # POST /v1/product/import-by-sku（v1）— 基于已有 Ozon SKU 复制建卡（官方"复制"通道）。
        # item: {sku:int, offer_id:str, name?, price?, old_price?, currency_code?, vat?}
        # 返回 {result:{task_id, unmatched_sku_list[]}}；源卡主开"禁止复制"时该 sku 进 unmatched_sku_list。
        # 轮询结果复用 get_import_info(task_id)。
        return self.request("/v1/product/import-by-sku", {"items": items})

    def import_prices(self, prices: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("/v1/product/import/prices", {"prices": prices})

    def get_category_tree(self, language: str = "ZH_HANS") -> dict[str, Any]:
        return self.request("/v1/description-category/tree", {"language": language})

    def get_category_attributes(
        self, description_category_id: int, type_id: int, language: str = "ZH_HANS"
    ) -> dict[str, Any]:
        return self.request(
            "/v1/description-category/attribute",
            {"description_category_id": description_category_id, "type_id": type_id, "language": language},
        )

    def search_attribute_values(
        self, description_category_id: int, type_id: int, attribute_id: int,
        value: str, *, limit: int = 20, language: str = "ZH_HANS",
    ) -> dict[str, Any]:
        return self.request(
            "/v1/description-category/attribute/values/search",
            {
                "description_category_id": description_category_id,
                "type_id": type_id,
                "attribute_id": attribute_id,
                "value": value,
                "limit": limit,
                "language": language,
            },
        )

    def get_attribute_values(
        self, description_category_id: int, type_id: int, attribute_id: int,
        *, language: str = "ZH_HANS", page_size: int = 100, max_total: int = 2000,
    ) -> dict[str, Any]:
        """分页拉某属性的全部字典值。累计超过 max_total 即停止并标 oversized
        （此时 values 截断到 max_total；调用方应据 oversized 决定是否使用）。
        返回 {"values": [{"id": int, "value": str}, ...], "oversized": bool}。"""
        values: list[dict[str, Any]] = []
        last_value_id = 0
        oversized = False
        while True:
            resp = self.request(
                "/v1/description-category/attribute/values",
                {
                    "description_category_id": description_category_id,
                    "type_id": type_id,
                    "attribute_id": attribute_id,
                    "language": language,
                    "limit": page_size,
                    "last_value_id": last_value_id,
                },
            )
            batch = resp.get("result") or []
            for it in batch:
                vid = it.get("id")
                if vid is None:
                    continue
                values.append({"id": int(vid), "value": str(it.get("value") or "")})
            if len(values) > max_total:
                oversized = True
                del values[max_total:]   # 不返回超额数据：契约保证 values 永不超过 max_total
                break
            if not resp.get("has_next") or not batch:
                break
            last_value_id = int(batch[-1].get("id") or 0)
        return {"values": values, "oversized": oversized}

    def archive_products(self, product_ids: list[int]) -> dict[str, Any]:
        return self.request("/v1/product/archive", {"product_id": product_ids})

    def delete_products(self, offer_ids: list[str]) -> dict[str, Any]:
        """删除商品（按 offer_id）。Ozon 要求商品先归档/无在途单才能删。"""
        return self.request(
            "/v2/products/delete",
            {"products": [{"offer_id": str(o)} for o in offer_ids]},
        )

    def update_stocks(self, stocks: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("/v2/products/stocks", {"stocks": stocks})

    def list_unfulfilled_fbs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str = "awaiting_packaging",
        since: str | None = None,
        to: str | None = None,
        include: dict[str, bool] | None = None,
        direction: str = "ASC",
    ) -> dict[str, Any]:
        filters: dict[str, Any] = {"status": status}
        if since is not None:
            filters["cutoff_from"] = since
        if to is not None:
            filters["cutoff_to"] = to
        return self.request(
            "/v3/posting/fbs/unfulfilled/list",
            {
                "dir": direction,
                "filter": filters,
                "limit": limit,
                "offset": offset,
                "with": include or {
                    "analytics_data": True,
                    "barcodes": True,
                    "financial_data": True,
                    "translit": True,
                },
            },
        )

    def get_fbs_posting(
        self,
        posting_number: str,
        *,
        include: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        return self.request(
            "/v3/posting/fbs/get",
            {
                "posting_number": posting_number,
                "with": include or {
                    "analytics_data": True,
                    "barcodes": True,
                    "financial_data": True,
                    "translit": True,
                },
            },
        )

    def ship_fbs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("/v2/posting/fbs/ship", payload)

    def list_unfulfilled_fbs_v4(self, *, cutoff_from: str, cutoff_to: str,
                                status: str = "awaiting_packaging", limit: int = 100,
                                cursor: str = "") -> dict[str, Any]:
        # v4 的 limit 取值范围是 (0, 100]（与 v3 的 ≤1000 不同），超了会 400。
        body: dict[str, Any] = {
            "dir": "ASC",
            "filter": {"cutoff_from": cutoff_from, "cutoff_to": cutoff_to, "status": status},
            "limit": max(1, min(int(limit), 100)),
            "with": {"analytics_data": True, "barcodes": True},
        }
        if cursor:
            body["cursor"] = cursor
        return self.request("/v4/posting/fbs/unfulfilled/list", body)

    def ship_fbs_v4(self, posting_number: str, packages: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("/v4/posting/fbs/ship",
                            {"posting_number": posting_number, "packages": packages,
                             "with": {"additional_data": True}})

    def _raw_post(self, path: str, payload: dict[str, Any]) -> bytes:
        """直接 POST 返回原始字节（面单 PDF 用）。可被测试 monkeypatch。"""
        import json as _json
        from urllib.request import Request, urlopen  # noqa: PLC0415
        from urllib.error import HTTPError  # noqa: PLC0415
        req = Request(
            url=f"{self.base_url}{path}",
            data=_json.dumps(payload).encode("utf-8"),
            headers={"Client-Id": self.client_id, "Api-Key": self.api_key,
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as res:  # noqa: S310
                return res.read()
        except HTTPError as exc:
            raise OzonApiError(exc.code, {}, exc.read().decode("utf-8", "replace"))

    def get_package_label_pdf(self, posting_numbers: list[str]) -> bytes:
        data = self._raw_post("/v2/posting/fbs/package-label",
                              {"posting_number": [str(p) for p in posting_numbers]})
        if not data.startswith(b"%PDF"):
            try:
                payload = json_lib.loads(data.decode("utf-8", "replace"))
            except Exception:
                payload = {}
            raise OzonApiError(
                200, payload,
                "面单尚未就绪（发货后约 45-60 秒可取），请稍后重试",
            )
        return data

    def get_fbs_package_label(self, posting_numbers: list[str]) -> dict[str, Any]:
        return self.request("/v2/posting/fbs/package-label", {"posting_number": posting_numbers})

    def cancel_fbs_posting(
        self,
        posting_number: str,
        *,
        cancel_reason_id: int,
        cancel_reason_message: str = "",
    ) -> dict[str, Any]:
        return self.request(
            "/v2/posting/fbs/cancel",
            {
                "posting_number": posting_number,
                "cancel_reason_id": cancel_reason_id,
                "cancel_reason_message": cancel_reason_message,
            },
        )

    def list_products(self, *, visibility: str = "ALL", last_id: str = "",
                       limit: int = 1000, offer_ids: list[str] | None = None,
                       product_ids: list[int] | None = None) -> dict[str, Any]:
        filt: dict[str, Any] = {"visibility": visibility}
        if offer_ids:
            filt["offer_id"] = [str(o) for o in offer_ids]
        if product_ids:
            filt["product_id"] = [str(p) for p in product_ids]
        return self.request("/v3/product/list",
                            {"filter": filt, "last_id": last_id, "limit": int(limit)})

    def finance_cash_flow_statement(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("/v1/finance/cash-flow-statement/list", payload)

    def get_products_info(self, *, offer_ids: list[str] | None = None,
                          product_ids: list[int] | None = None,
                          skus: list[int] | None = None) -> dict[str, Any]:
        if sum(bool(ids) for ids in (offer_ids, product_ids, skus)) > 1:
            raise ValueError("offer_ids, product_ids, and skus are mutually exclusive")
        if offer_ids:
            payload: dict[str, Any] = {"offer_id": [str(o) for o in offer_ids]}
        elif product_ids:
            payload = {"product_id": [int(p) for p in product_ids]}
        elif skus:
            payload = {"sku": [int(sku) for sku in skus]}
        else:
            payload = {"offer_id": []}
        return self.request("/v3/product/info/list", payload)

    def get_products_attributes(self, *, offer_ids: list[str] | None = None,
                                product_ids: list[int] | None = None,
                                last_id: str = "", limit: int = 1000) -> dict[str, Any]:
        filt: dict[str, Any] = {"visibility": "ALL"}
        if offer_ids:
            filt["offer_id"] = [str(o) for o in offer_ids]
        if product_ids:
            filt["product_id"] = [str(p) for p in product_ids]
        return self.request("/v4/product/info/attributes",
                            {"filter": filt, "last_id": last_id, "limit": int(limit)})

    def get_product_description(self, *, offer_id: str | None = None,
                                product_id: int | None = None) -> dict[str, Any]:
        """GET /v1/product/info/description — 返回 {result: {description, id, name, offer_id}}。
        offer_id 或 product_id 二选一，优先 offer_id。"""
        if offer_id is not None:
            payload: dict[str, Any] = {"offer_id": str(offer_id)}
        elif product_id is not None:
            payload = {"product_id": int(product_id)}
        else:
            payload = {}
        return self.request("/v1/product/info/description", payload)
