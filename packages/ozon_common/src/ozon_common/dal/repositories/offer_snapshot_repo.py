"""OfferSnapshotRepo — offer_snapshots 聚合的 SQLAlchemy Core 访问层。

等价替换 apps/webui/src/webui/store.py 的三个方法:
  - add_offer_snapshot
  - latest_offer_snapshot
  - list_offer_snapshots
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import offer_snapshots as T
from ozon_common.jsonio import utc_now_iso


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, "", " "):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", " "):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class OfferSnapshotRepo(BaseRepo):
    def add_offer_snapshot(self, snap: dict[str, Any]) -> dict[str, Any]:
        """插入一条跟卖快照，返回 {"id": <lastrowid>}。

        字段处理与 Store.add_offer_snapshot 完全一致:
          product_id      → str
          captured_at     → 有则用传入值，否则 utc_now_iso()
          follow_count    → _to_int_or_none
          price_min/max   → _to_float_or_none
          store_client_id → str
        """
        res = self.s.execute(
            insert(T).values(
                product_id=str(snap.get("product_id") or ""),
                sku=snap.get("sku"),
                captured_at=str(snap.get("captured_at") or utc_now_iso()),
                follow_count=_to_int_or_none(snap.get("follow_count")),
                price_min=_to_float_or_none(snap.get("price_min")),
                price_max=_to_float_or_none(snap.get("price_max")),
                sellers_json=snap.get("sellers_json"),
                store_client_id=str(snap.get("store_client_id") or ""),
            )
        )
        return {"id": res.inserted_primary_key[0]}

    def latest_offer_snapshot(self, product_id: str) -> dict[str, Any] | None:
        """返回指定 product_id 的最新一条快照（按 captured_at DESC, id DESC），不含 store_client_id。

        语义与 Store.latest_offer_snapshot 完全一致:
          SELECT id, product_id, sku, captured_at, follow_count, price_min, price_max, sellers_json
          WHERE product_id=? ORDER BY captured_at DESC, id DESC LIMIT 1
        """
        row = self.s.execute(
            select(
                T.c.id,
                T.c.product_id,
                T.c.sku,
                T.c.captured_at,
                T.c.follow_count,
                T.c.price_min,
                T.c.price_max,
                T.c.sellers_json,
            )
            .where(T.c.product_id == str(product_id))
            .order_by(T.c.captured_at.desc(), T.c.id.desc())
            .limit(1)
        ).first()
        if row is None:
            return None
        d = dict(row._mapping)
        d["price_min"] = _to_float_or_none(d.get("price_min"))
        d["price_max"] = _to_float_or_none(d.get("price_max"))
        return d

    def list_offer_snapshots(
        self, product_id: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """返回指定 product_id 的快照列表（按 captured_at ASC, id ASC），不含 store_client_id。

        语义与 Store.list_offer_snapshots 完全一致:
          SELECT id, product_id, sku, captured_at, follow_count, price_min, price_max, sellers_json
          WHERE product_id=? ORDER BY captured_at ASC, id ASC LIMIT ?
        """
        rows = self.s.execute(
            select(
                T.c.id,
                T.c.product_id,
                T.c.sku,
                T.c.captured_at,
                T.c.follow_count,
                T.c.price_min,
                T.c.price_max,
                T.c.sellers_json,
            )
            .where(T.c.product_id == str(product_id))
            .order_by(T.c.captured_at.asc(), T.c.id.asc())
            .limit(int(limit))
        ).all()
        out = []
        for r in rows:
            d = dict(r._mapping)
            d["price_min"] = _to_float_or_none(d.get("price_min"))
            d["price_max"] = _to_float_or_none(d.get("price_max"))
            out.append(d)
        return out
