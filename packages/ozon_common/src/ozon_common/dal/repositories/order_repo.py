"""OrderRepo — postings + procurement 聚合的 SQLAlchemy Core 访问层。

等价替换 apps/webui/src/webui/store.py 的六个方法:
  - upsert_postings
  - list_postings
  - get_posting
  - rebuild_procurement
  - list_procurement
  - set_procurement_state
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import case, delete, func, insert, literal, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import drafts as DR
from ozon_common.dal.schema import postings as P
from ozon_common.dal.schema import procurement as PR
from ozon_common.jsonio import dumps_json, loads_json, utc_now_iso


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


class OrderRepo(BaseRepo):
    # ---------- 订单(postings) ----------

    def upsert_postings(
        self, items: list[dict[str, Any]], store_client_id: str = ""
    ) -> None:
        """批量 upsert postings（按 posting_number 冲突覆盖）。

        products 列表 → products_json；raw dict → raw_json；synced_at 自动填当前 UTC。
        实现：delete(PK) + insert，等价于旧 INSERT … ON CONFLICT DO UPDATE。
        """
        now = utc_now_iso()
        scid = str(store_client_id or "")
        for p in items or []:
            num = str(p.get("posting_number") or "").strip()
            if not num:
                continue
            self.s.execute(delete(P).where(P.c.posting_number == num))
            self.s.execute(
                insert(P).values(
                    posting_number=num,
                    ozon_order_id=str(p.get("ozon_order_id") or ""),
                    status=str(p.get("status") or ""),
                    ship_by=p.get("ship_by"),
                    products_json=dumps_json(p.get("products") or []),
                    warehouse_id=_to_int_or_none(p.get("warehouse_id")),
                    raw_json=dumps_json(p.get("raw") or {}),
                    synced_at=now,
                    store_client_id=scid,
                )
            )

    def list_postings(
        self, store_client_id: str | None = None
    ) -> list[dict[str, Any]]:
        """按店过滤（None = 不过滤），返回 list[dict]；products_json/raw_json 还原为 products/raw。"""
        q = select(P).order_by(P.c.synced_at.desc())
        if store_client_id is not None:
            q = q.where(P.c.store_client_id == str(store_client_id or ""))
        rows = self.s.execute(q).all()
        out = []
        for r in rows:
            d = dict(r._mapping)
            d["products"] = loads_json(d.pop("products_json"), [])
            d["raw"] = loads_json(d.pop("raw_json"), {})
            out.append(d)
        return out

    def get_posting(self, posting_number: str) -> dict[str, Any] | None:
        """按 posting_number 精确查询，找不到返回 None；products_json/raw_json 还原。"""
        row = self.s.execute(
            select(P).where(P.c.posting_number == str(posting_number)).limit(1)
        ).first()
        if not row:
            return None
        d = dict(row._mapping)
        d["products"] = loads_json(d.pop("products_json"), [])
        d["raw"] = loads_json(d.pop("raw_json"), {})
        return d

    # ---------- 备货(procurement) ----------

    def rebuild_procurement(self, store_client_id: str = "") -> None:
        """按 postings × drafts(offer_id) JOIN 重建待采购行；已存在的保留 purchase_state/note。

        按店重建：只用该店 postings，offer_id 在该店草稿里找 supplier/purchase_url/cost_cny，
        采购行带 store_client_id。

        实现语义与旧 Store 完全一致：
        1. 先读取本店现有 procurement 行（保留 purchase_state/note）。
        2. 遍历本店所有 postings，展开 products_json 里的每个 product。
        3. 按 offer_id 查草稿取 supplier/purchase_url/cost_cny（查不到则用空值）。
        4. 按 (posting_number, offer_id) UNIQUE 冲突：delete+insert 等价 upsert，
           只覆盖 qty/supplier/purchase_url/cost_cny/updated_at/store_client_id，
           保留旧的 purchase_state/note（即步骤1查到的）。
        """
        scid = str(store_client_id or "")
        # 1. 读当前本店采购行（保留状态/备注）
        existing = {
            (r.posting_number, r.offer_id): r
            for r in self.s.execute(
                select(
                    PR.c.posting_number,
                    PR.c.offer_id,
                    PR.c.purchase_state,
                    PR.c.note,
                ).where(PR.c.store_client_id == scid)
            ).all()
        }
        now = utc_now_iso()
        # 2. 遍历本店所有 postings
        posting_rows = self.s.execute(
            select(P.c.posting_number, P.c.products_json).where(
                P.c.store_client_id == scid
            )
        ).all()
        for p_row in posting_rows:
            for prod in loads_json(p_row.products_json, []):
                offer_id = str(prod.get("offer_id") or "").strip()
                if not offer_id:
                    continue
                qty = _to_int_or_none(prod.get("quantity")) or 1
                # 3. 查草稿取供应商信息
                src = self.s.execute(
                    select(
                        DR.c.supplier,
                        DR.c.purchase_url,
                        DR.c.cost_cny,
                    )
                    .where(DR.c.offer_id == offer_id, DR.c.store_client_id == scid)
                    .limit(1)
                ).first()
                supplier = src.supplier if src else ""
                purchase_url = src.purchase_url if src else ""
                cost_cny = src.cost_cny if src else None
                prev = existing.get((p_row.posting_number, offer_id))
                state = prev.purchase_state if prev else "待采购"
                note = prev.note if prev else ""
                # 4. delete+insert upsert
                self.s.execute(
                    delete(PR).where(
                        PR.c.posting_number == p_row.posting_number,
                        PR.c.offer_id == offer_id,
                    )
                )
                self.s.execute(
                    insert(PR).values(
                        posting_number=p_row.posting_number,
                        offer_id=offer_id,
                        qty=qty,
                        purchase_state=state,
                        supplier=str(supplier or ""),
                        purchase_url=str(purchase_url or ""),
                        cost_cny=cost_cny,
                        note=note,
                        updated_at=now,
                        store_client_id=scid,
                    )
                )

    def list_procurement(
        self, store_client_id: str | None = None
    ) -> list[dict[str, Any]]:
        """按店过滤（None = 不过滤），LEFT JOIN postings 取 ship_by/status，
        再 LEFT JOIN drafts(同 offer_id + 同店) 批量补商品标题，按截止时间升序。

        - NULL/空 ship_by 放最后；相同 ship_by 按 posting_number 稳定排序。
        - title 取 drafts.ozon_title，空则回退 source_title；查不到草稿则为空串。
          drafts.offer_id 是 Ozon 商品唯一标识，与采购行基本一对一，单次 JOIN
          不放大行数，无 N+1。
        - status 透传 postings.status（前端分阶段 tab 用：awaiting_packaging
          待发货 / 已发货态等）。
        """
        ship_by_col = func.coalesce(P.c.ship_by, literal("")).label("ship_by")
        status_col = func.coalesce(P.c.status, literal("")).label("posting_status")
        # ozon_title 优先，空回退 source_title，再回退空串
        title_col = func.coalesce(
            func.nullif(DR.c.ozon_title, literal("")),
            DR.c.source_title,
            literal(""),
        ).label("title")
        sort_key = case(
            (func.coalesce(P.c.ship_by, literal("")) == "", "9999-99-99"),
            else_=P.c.ship_by,
        )
        # drafts JOIN：同 offer_id 且同店（与 rebuild_procurement 的取数口径一致）
        draft_join_on = (DR.c.offer_id == PR.c.offer_id) & (
            DR.c.store_client_id == PR.c.store_client_id
        )
        q = (
            select(PR, ship_by_col, status_col, title_col)
            .select_from(
                PR.outerjoin(P, P.c.posting_number == PR.c.posting_number).outerjoin(
                    DR, draft_join_on
                )
            )
            .order_by(sort_key.asc(), PR.c.posting_number.asc())
        )
        if store_client_id is not None:
            q = q.where(PR.c.store_client_id == str(store_client_id or ""))
        rows = self.s.execute(q).all()
        # 同 offer_id 偶有多条草稿时 JOIN 会放大行数：按采购行主键去重，保第一条。
        out: list[dict[str, Any]] = []
        seen: set[int] = set()
        for r in rows:
            d = dict(r._mapping)
            pid = d.get("id")
            if pid in seen:
                continue
            seen.add(pid)
            d["cost_cny"] = _to_float_or_none(d.get("cost_cny"))
            out.append(d)
        return out

    def set_procurement_state(
        self, proc_id: int, state: str, *, note: str | None = None
    ) -> None:
        """更新采购行状态；note=None 时只改状态，否则同时覆盖 note。"""
        if note is None:
            self.s.execute(
                update(PR)
                .where(PR.c.id == int(proc_id))
                .values(purchase_state=str(state), updated_at=utc_now_iso())
            )
        else:
            self.s.execute(
                update(PR)
                .where(PR.c.id == int(proc_id))
                .values(
                    purchase_state=str(state),
                    note=str(note),
                    updated_at=utc_now_iso(),
                )
            )
