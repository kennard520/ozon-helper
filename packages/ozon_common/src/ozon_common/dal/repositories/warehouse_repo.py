"""WarehouseRepo — warehouses + delivery_methods 聚合的 SQLAlchemy Core 访问层。

等价替换 apps/webui/src/webui/store.py 的五个方法:
  - upsert_warehouses
  - list_warehouses
  - set_default_warehouse
  - replace_delivery_methods
  - list_delivery_methods
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import delivery_methods as DM
from ozon_common.dal.schema import warehouses as WH
from ozon_common.jsonio import dumps_json, utc_now_iso


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, "", " "):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class WarehouseRepo(BaseRepo):
    # ---------- 仓库 ----------

    def upsert_warehouses(
        self, items: list[dict[str, Any]], store_client_id: str = ""
    ) -> None:
        """批量 upsert 仓库（按 warehouse_id 冲突覆盖），照搬 Store 语义。

        实现：delete(pk) + insert，等价于旧 INSERT … ON CONFLICT DO UPDATE。
        """
        now = utc_now_iso()
        scid = str(store_client_id or "")
        for w in items or []:
            wid = _to_int_or_none(w.get("warehouse_id"))
            if wid is None:
                continue
            self.s.execute(delete(WH).where(WH.c.warehouse_id == wid))
            self.s.execute(
                insert(WH).values(
                    warehouse_id=wid,
                    name=str(w.get("name") or ""),
                    is_rfbs=1 if w.get("is_rfbs") else 0,
                    status=str(w.get("status") or ""),
                    fetched_at=now,
                    store_client_id=scid,
                )
            )

    def list_warehouses(
        self, store_client_id: str | None = None
    ) -> list[dict[str, Any]]:
        """按店过滤（None = 不过滤），返回 list[dict]，is_rfbs/is_default 转 bool。"""
        q = select(
            WH.c.warehouse_id,
            WH.c.name,
            WH.c.is_rfbs,
            WH.c.status,
            WH.c.is_default,
            WH.c.fetched_at,
            WH.c.store_client_id,
        ).order_by(WH.c.warehouse_id)
        if store_client_id is not None:
            q = q.where(WH.c.store_client_id == str(store_client_id or ""))
        rows = self.s.execute(q).all()
        out = []
        for r in rows:
            d = dict(r._mapping)
            d["is_rfbs"] = bool(d["is_rfbs"])
            d["is_default"] = bool(d["is_default"])
            out.append(d)
        return out

    def set_default_warehouse(
        self, warehouse_id: int, store_client_id: str = ""
    ) -> None:
        """每店一个默认仓：先在该店范围内清旧默认，再设新默认。"""
        scid = str(store_client_id or "")
        self.s.execute(
            update(WH).where(WH.c.store_client_id == scid).values(is_default=0)
        )
        self.s.execute(
            update(WH)
            .where(
                WH.c.warehouse_id == int(warehouse_id),
                WH.c.store_client_id == scid,
            )
            .values(is_default=1)
        )

    # ---------- 配送方式 ----------

    def replace_delivery_methods(
        self, items: list[dict[str, Any]], store_client_id: str = ""
    ) -> None:
        """按店全量替换：先删本店所有行，再批量插新行。

        删除范围：WHERE store_client_id = scid（与旧 Store 完全一致）。
        raw_json 列：取 d.get("raw") 序列化存储（与旧 Store 完全一致）。
        """
        now = utc_now_iso()
        scid = str(store_client_id or "")
        self.s.execute(delete(DM).where(DM.c.store_client_id == scid))
        for d in items or []:
            did = _to_int_or_none(d.get("delivery_method_id"))
            if did is None:
                continue
            self.s.execute(
                insert(DM).values(
                    delivery_method_id=did,
                    warehouse_id=_to_int_or_none(d.get("warehouse_id")),
                    name=str(d.get("name") or ""),
                    status=str(d.get("status") or ""),
                    provider_id=_to_int_or_none(d.get("provider_id")),
                    template_id=_to_int_or_none(d.get("template_id")),
                    tpl_integration_type=str(d.get("tpl_integration_type") or ""),
                    is_express=1 if d.get("is_express") else 0,
                    cutoff=str(d.get("cutoff") or ""),
                    sla_cut_in=_to_int_or_none(d.get("sla_cut_in")),
                    dropoff_name=str(d.get("dropoff_name") or ""),
                    dropoff_code=str(d.get("dropoff_code") or ""),
                    dropoff_address=str(d.get("dropoff_address") or ""),
                    dropoff_lat=d.get("dropoff_lat"),
                    dropoff_lng=d.get("dropoff_lng"),
                    created_at=str(d.get("created_at") or ""),
                    updated_at=str(d.get("updated_at") or ""),
                    fetched_at=now,
                    store_client_id=scid,
                    raw_json=dumps_json(d.get("raw") or {}),
                )
            )

    def list_delivery_methods(
        self, store_client_id: str | None = None
    ) -> list[dict[str, Any]]:
        """按店过滤（None = 不过滤），返回 list[dict]，is_express 转 bool。

        不含 raw_json（与旧 Store 完全一致：SELECT 无该列）。
        """
        q = select(
            DM.c.delivery_method_id,
            DM.c.warehouse_id,
            DM.c.name,
            DM.c.status,
            DM.c.provider_id,
            DM.c.template_id,
            DM.c.tpl_integration_type,
            DM.c.is_express,
            DM.c.cutoff,
            DM.c.sla_cut_in,
            DM.c.dropoff_name,
            DM.c.dropoff_code,
            DM.c.dropoff_address,
            DM.c.dropoff_lat,
            DM.c.dropoff_lng,
            DM.c.created_at,
            DM.c.updated_at,
            DM.c.fetched_at,
            DM.c.store_client_id,
        ).order_by(DM.c.warehouse_id, DM.c.delivery_method_id)
        if store_client_id is not None:
            q = q.where(DM.c.store_client_id == str(store_client_id or ""))
        rows = self.s.execute(q).all()
        out = []
        for r in rows:
            d = dict(r._mapping)
            d["is_express"] = bool(d.get("is_express"))
            out.append(d)
        return out
