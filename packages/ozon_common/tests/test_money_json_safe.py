"""M4b 补漏：仓储读边界钱列 JSON 安全性测试。

验证 DraftRepo._row_to_draft / OrderRepo.list_procurement /
OfferSnapshotRepo.latest_offer_snapshot & list_offer_snapshots
返回的 dict 里钱列（cost_cny / price_min / price_max）是 float（或 None），
而非 Decimal，使 json.dumps() 不会抛 TypeError。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.repositories.offer_snapshot_repo import OfferSnapshotRepo
from ozon_common.dal.repositories.order_repo import OrderRepo
from ozon_common.dal.schema import metadata

# ---------------------------------------------------------------------------
# 公共辅助
# ---------------------------------------------------------------------------

def _bind(tmp: str, name: str = "m.db"):
    eng = build_engine(f"sqlite:///{Path(tmp) / name}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _draft_payload(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_platform": "1688",
        "source_url": "https://detail.1688.com/offer/99.html",
        "source_offer_id": "",
        "source_title": "测试商品",
        "purchase_url": "",
        "purchase_note": "",
        "ozon_title": "Test Product",
        "description": "desc",
        "category_id": "123",
        "type_id": "",
        "brand_id": None,
        "brand_name": "",
        "price": "100",
        "old_price": "120",
        "stock": 5,
        "weight_g": None,
        "length_mm": None,
        "width_mm": None,
        "height_mm": None,
        "cost_cny": None,
        "video_url": "",
        "local_images": [],
        "source": "",
        "ozon_product_id": None,
        "offer_id": "",
        "supplier": "",
        "source_raw": {},
        "attributes": {},
        "status": "ready",
        "publish_response": None,
        "images": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# DraftRepo: cost_cny 是 float，json.dumps 不抛
# ---------------------------------------------------------------------------

def test_draft_cost_cny_is_float_json_safe():
    """get_draft 返回的 cost_cny 是 float，json.dumps 不报 Decimal 错误。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "draft.db")
        try:
            with S.session_scope():
                repo = DraftRepo()
                inserted = repo.insert_draft(
                    _draft_payload(cost_cny=12.5, offer_id=""),
                    user_id=1,
                    store_cid="",
                    errors=[],
                    status="ready",
                    offer_id_base="OFFER-99",
                )
                draft_id = inserted["id"]

            with S.session_scope():
                d = DraftRepo().get_draft(draft_id, 1)

            assert d is not None
            # 不应抛 TypeError: Object of type Decimal is not JSON serializable
            serialized = json.dumps(d)
            assert serialized  # 非空字符串
            assert d["cost_cny"] == 12.5
            assert isinstance(d["cost_cny"], float)
        finally:
            eng.dispose()


def test_draft_cost_cny_none_is_json_safe():
    """cost_cny=None 时 get_draft 返回 None，json.dumps 也安全。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "draft_none.db")
        try:
            with S.session_scope():
                repo = DraftRepo()
                inserted = repo.insert_draft(
                    _draft_payload(cost_cny=None, offer_id=""),
                    user_id=1,
                    store_cid="",
                    errors=[],
                    status="ready",
                    offer_id_base="OFFER-98",
                )
                draft_id = inserted["id"]

            with S.session_scope():
                d = DraftRepo().get_draft(draft_id, 1)

            assert d is not None
            json.dumps(d)  # 不抛
            assert d["cost_cny"] is None
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# OrderRepo: list_procurement 的 cost_cny 是 float，json.dumps 不抛
# ---------------------------------------------------------------------------

def test_procurement_cost_cny_is_float_json_safe():
    """list_procurement 的每行 cost_cny 是 float（或 None），json.dumps 安全。

    rebuild_procurement 从 drafts 表读 cost_cny（Numeric Decimal），
    写入 procurement 表（也是 Numeric），再通过 list_procurement 读出。
    修复后读边界应把 cost_cny 转 float。
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "order.db")
        try:
            scid = "store1"
            # 先插入一条 draft，有 offer_id 和 cost_cny
            with S.session_scope():
                repo = DraftRepo()
                repo.insert_draft(
                    _draft_payload(
                        cost_cny=8.75,
                        offer_id="SKU-COST",
                        source_url="https://detail.1688.com/offer/77.html",
                        store_client_id=scid,
                    ),
                    user_id=1,
                    store_cid=scid,
                    errors=[],
                    status="ready",
                    offer_id_base="SKU-COST",
                )

            # upsert posting + rebuild procurement
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [
                        {
                            "posting_number": "PN-COST-1",
                            "status": "awaiting_deliver",
                            "products": [{"offer_id": "SKU-COST", "quantity": 2}],
                            "raw": {},
                        }
                    ],
                    store_client_id=scid,
                )
                OrderRepo().rebuild_procurement(store_client_id=scid)

            with S.session_scope():
                rows = OrderRepo().list_procurement(store_client_id=scid)

            assert len(rows) == 1
            row = rows[0]
            # json.dumps 不应抛
            json.dumps(row)
            assert row["cost_cny"] == 8.75
            assert isinstance(row["cost_cny"], float)
        finally:
            eng.dispose()


def test_procurement_cost_cny_none_json_safe():
    """procurement cost_cny=None 时也 JSON 安全（offer_id 无对应 draft）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "order_none.db")
        try:
            scid = "storeN"
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [
                        {
                            "posting_number": "PN-NC-1",
                            "status": "awaiting_deliver",
                            "products": [{"offer_id": "SKU-NOCOST", "quantity": 1}],
                            "raw": {},
                        }
                    ],
                    store_client_id=scid,
                )
                OrderRepo().rebuild_procurement(store_client_id=scid)

            with S.session_scope():
                rows = OrderRepo().list_procurement(store_client_id=scid)

            assert len(rows) == 1
            row = rows[0]
            json.dumps(row)  # 不抛
            assert row["cost_cny"] is None
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# OfferSnapshotRepo: price_min / price_max 是 float，json.dumps 不抛
# ---------------------------------------------------------------------------

def test_latest_offer_snapshot_prices_are_float_json_safe():
    """latest_offer_snapshot 返回的 price_min/price_max 是 float，json.dumps 安全。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "snap.db")
        try:
            with S.session_scope():
                OfferSnapshotRepo().add_offer_snapshot(
                    {
                        "product_id": "P-SNAP",
                        "sku": "SKU-S",
                        "captured_at": "2026-01-01T00:00:00Z",
                        "follow_count": 3,
                        "price_min": 15.5,
                        "price_max": 30.0,
                        "sellers_json": "[]",
                        "store_client_id": "s1",
                    }
                )

            with S.session_scope():
                snap = OfferSnapshotRepo().latest_offer_snapshot("P-SNAP")

            assert snap is not None
            json.dumps(snap)  # 不抛
            assert snap["price_min"] == 15.5
            assert isinstance(snap["price_min"], float)
            assert snap["price_max"] == 30.0
            assert isinstance(snap["price_max"], float)
        finally:
            eng.dispose()


def test_list_offer_snapshots_prices_are_float_json_safe():
    """list_offer_snapshots 列表中每行 price_min/price_max 是 float，json.dumps 安全。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "snap2.db")
        try:
            with S.session_scope():
                for i, (pmin, pmax) in enumerate([(10.0, 20.0), (11.5, 21.5)]):
                    OfferSnapshotRepo().add_offer_snapshot(
                        {
                            "product_id": "P-LIST",
                            "sku": f"SKU-{i}",
                            "captured_at": f"2026-01-0{i+1}T00:00:00Z",
                            "follow_count": i,
                            "price_min": pmin,
                            "price_max": pmax,
                            "sellers_json": "[]",
                            "store_client_id": "s1",
                        }
                    )

            with S.session_scope():
                snaps = OfferSnapshotRepo().list_offer_snapshots("P-LIST")

            assert len(snaps) == 2
            for s in snaps:
                json.dumps(s)  # 不抛
                assert isinstance(s["price_min"], float)
                assert isinstance(s["price_max"], float)
        finally:
            eng.dispose()


def test_offer_snapshot_prices_none_json_safe():
    """price_min/price_max 为 None 时也 JSON 安全。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp, "snap_none.db")
        try:
            with S.session_scope():
                OfferSnapshotRepo().add_offer_snapshot(
                    {
                        "product_id": "P-NONE",
                        "sku": None,
                        "follow_count": None,
                        "price_min": None,
                        "price_max": None,
                        "sellers_json": None,
                        "store_client_id": "",
                    }
                )

            with S.session_scope():
                snap = OfferSnapshotRepo().latest_offer_snapshot("P-NONE")

            assert snap is not None
            json.dumps(snap)  # 不抛
            assert snap["price_min"] is None
            assert snap["price_max"] is None
        finally:
            eng.dispose()
