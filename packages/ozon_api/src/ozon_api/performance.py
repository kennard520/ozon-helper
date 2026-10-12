from __future__ import annotations

import json as json_lib
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .client import OzonApiError


PERFORMANCE_API_BASE_URL = "https://api-performance.ozon.ru"


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
        json: dict[str, Any] | None,
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


class UrlLibPerformanceTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None,
        timeout: float,
    ) -> SimpleResponse:
        body = None
        if json is not None:
            body = json_lib.dumps(json, ensure_ascii=False).encode("utf-8")
        req = Request(url=url, data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as res:  # noqa: S310 - fixed Ozon API endpoint.
                text = res.read().decode("utf-8")
                return SimpleResponse(status_code=res.status, text=text)
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return SimpleResponse(status_code=exc.code, text=text)


class OzonPerformanceClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = PERFORMANCE_API_BASE_URL,
        timeout: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        if not client_id:
            raise ValueError("performance_client_id is required")
        if not client_secret:
            raise ValueError("performance_client_secret is required")
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport or UrlLibPerformanceTransport()
        self._access_token = ""
        self._token_expires_at = 0.0

    def _token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token
        data = self._request_no_auth(
            "POST",
            "/api/client/token",
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
        )
        token = str(data.get("access_token") or "")
        if not token:
            raise OzonApiError(200, data, "Performance API token response has no access_token")
        expires_in = int(data.get("expires_in") or 3600)
        self._access_token = token
        self._token_expires_at = now + max(60, expires_in - 60)
        return token

    def _request_no_auth(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.transport.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        data = response.json()
        if response.status_code >= 400:
            raise OzonApiError(response.status_code, data, response.text)
        return data

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{self.base_url}{path}"
        if query:
            pairs: list[tuple[str, str]] = []
            for key, value in query.items():
                if value in (None, ""):
                    continue
                if isinstance(value, list):
                    pairs.extend((key, str(v)) for v in value)
                else:
                    pairs.append((key, str(value)))
            if pairs:
                url = f"{url}?{urlencode(pairs)}"
        response = self.transport.request(
            method=method.upper(),
            url=url,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        data = response.json()
        if response.status_code >= 400:
            raise OzonApiError(response.status_code, data, response.text)
        return data

    def list_campaigns(self, **query: Any) -> dict[str, Any]:
        return self.request("GET", "/api/client/campaign", query=query)

    def campaign_products(self, campaign_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/client/campaign/{campaign_id}/v2/products")

    def add_campaign_products(self, campaign_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", f"/api/client/campaign/{campaign_id}/products", {"products": items})

    def delete_campaign_products(self, campaign_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", f"/api/client/campaign/{campaign_id}/products/delete", {"products": items})

    def search_promo_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/client/campaign/search_promo/v2/products", payload)

    def enable_search_promo(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", "/api/client/search_promo/product/enable", {"products": items})

    def disable_search_promo(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", "/api/client/search_promo/product/disable", {"products": items})
