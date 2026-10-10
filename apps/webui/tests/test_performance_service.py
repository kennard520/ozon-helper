from __future__ import annotations

import pytest

from webui.services import performance_service


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    def list_campaigns(self):
        self.calls.append(("list_campaigns", None, None))
        return {"list": [{"id": "11", "title": "A", "state": "RUNNING", "advObjectType": "SKU"}]}

    def campaign_products(self, campaign_id: str):
        self.calls.append(("campaign_products", campaign_id, None))
        return {"products": [{"sku": "1", "offerId": "O1", "title": "T1"}]}

    def delete_campaign_products(self, campaign_id: str, items: list[dict]):
        self.calls.append(("delete_campaign_products", campaign_id, items))
        return {"ok": True}

    def disable_search_promo(self, items: list[dict]):
        self.calls.append(("disable_search_promo", None, items))
        if items[0].get("sku") == "bad":
            raise RuntimeError("bad sku")
        return {"ok": True}


def test_operation_preview_rejects_unknown_operation() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        performance_service.operation_preview(
            {"performance_client_id": "cid", "performance_client_secret": "sec"},
            {"operation": "stop_campaign", "campaign_id": "11", "items": [{"sku": "1"}]},
        )


def test_operation_preview_normalizes_items_and_counts() -> None:
    preview = performance_service.operation_preview(
        {"performance_client_id": "cid", "performance_client_secret": "sec"},
        {
            "operation": "remove_products",
            "campaign_id": "11",
            "campaign_title": "Campaign A",
            "items": [{"sku": 1}, {"offer_id": "O2"}, {"sku": ""}],
        },
    )

    assert preview == {
        "operation": "remove_products",
        "campaign_id": "11",
        "campaign_title": "Campaign A",
        "count": 2,
        "items": [{"sku": "1", "offer_id": ""}, {"sku": "", "offer_id": "O2"}],
        "warnings": [],
    }


def test_remove_products_calls_campaign_delete_per_item(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(performance_service, "_client", lambda _settings: fake)

    result = performance_service.operation_commit(
        {"performance_client_id": "cid", "performance_client_secret": "sec"},
        {"operation": "remove_products", "campaign_id": "11", "items": [{"sku": "1"}, {"offer_id": "O2"}]},
    )

    assert fake.calls == [
        ("delete_campaign_products", "11", [{"sku": "1", "offer_id": ""}]),
        ("delete_campaign_products", "11", [{"sku": "", "offer_id": "O2"}]),
    ]
    assert result["results"] == [
        {"sku": "1", "offer_id": "", "ok": True, "message": ""},
        {"sku": "", "offer_id": "O2", "ok": True, "message": ""},
    ]


def test_disable_search_promo_returns_partial_item_failures(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(performance_service, "_client", lambda _settings: fake)

    result = performance_service.operation_commit(
        {"performance_client_id": "cid", "performance_client_secret": "sec"},
        {"operation": "disable_search_promo", "campaign_id": "11", "items": [{"sku": "1"}, {"sku": "bad"}]},
    )

    assert fake.calls == [
        ("disable_search_promo", None, [{"sku": "1", "offer_id": ""}]),
        ("disable_search_promo", None, [{"sku": "bad", "offer_id": ""}]),
    ]
    assert result["results"] == [
        {"sku": "1", "offer_id": "", "ok": True, "message": ""},
        {"sku": "bad", "offer_id": "", "ok": False, "message": "bad sku"},
    ]
