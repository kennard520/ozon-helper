from __future__ import annotations

from typing import Any

from sqlalchemy import delete, insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import commission_map as CM
from ozon_common.dal.schema import settings as ST
from ozon_common.jsonio import dumps_json, loads_json, utc_now_iso

_KEY_REALFBS = "realfbs_routes_json"
_KEY_COMMISSION_CATS = "commission_categories_json"


class CommissionRepo(BaseRepo):
    # ------------------------------------------------------------------
    # commission_map 表
    # ------------------------------------------------------------------

    def save_commission_map(
        self, cat: int, type_id: int, parent_en: str, sub_en: str, rfbs: list[float]
    ) -> None:
        """写入/更新一条 commission_map 记录（复合主键 upsert = delete+insert）。"""
        self.s.execute(
            delete(CM).where(
                CM.c.description_category_id == int(cat),
                CM.c.type_id == int(type_id),
            )
        )
        self.s.execute(
            insert(CM).values(
                description_category_id=int(cat),
                type_id=int(type_id),
                parent_en=str(parent_en or ""),
                sub_en=str(sub_en or ""),
                rfbs_json=dumps_json(rfbs or []),
                updated_at=utc_now_iso(),
            )
        )

    def load_commission_map(self, cat: int, type_id: int) -> dict[str, Any] | None:
        """按复合主键读取一条 commission_map 记录，无记录返回 None。"""
        row = self.s.execute(
            select(CM.c.parent_en, CM.c.sub_en, CM.c.rfbs_json).where(
                CM.c.description_category_id == int(cat),
                CM.c.type_id == int(type_id),
            )
        ).first()
        if row is None:
            return None
        return {
            "parent_en": row.parent_en,
            "sub_en": row.sub_en,
            "rfbs": loads_json(row.rfbs_json, []),
        }

    # ------------------------------------------------------------------
    # settings 表 — realfbs_routes (user_id=0, key='realfbs_routes_json')
    # ------------------------------------------------------------------

    def get_realfbs_routes(self) -> list[dict[str, Any]] | None:
        """读 realFBS 运费路线；无记录返回 None。"""
        row = self.s.execute(
            select(ST.c.value).where(
                ST.c.user_id == 0,
                ST.c.key == _KEY_REALFBS,
            )
        ).first()
        if row is None:
            return None
        return loads_json(row.value, None)

    def set_realfbs_routes(self, routes: list[dict[str, Any]]) -> None:
        """整表覆盖 realFBS 运费路线。"""
        self.s.execute(
            delete(ST).where(ST.c.user_id == 0, ST.c.key == _KEY_REALFBS)
        )
        self.s.execute(
            insert(ST).values(
                user_id=0,
                key=_KEY_REALFBS,
                value=dumps_json(routes or []),
            )
        )

    # ------------------------------------------------------------------
    # settings 表 — commission_categories (user_id=0, key='commission_categories_json')
    # ------------------------------------------------------------------

    def get_commission_categories(self) -> list[dict[str, Any]] | None:
        """读 realFBS 佣金类目表；无记录返回 None。"""
        row = self.s.execute(
            select(ST.c.value).where(
                ST.c.user_id == 0,
                ST.c.key == _KEY_COMMISSION_CATS,
            )
        ).first()
        if row is None:
            return None
        return loads_json(row.value, None)

    def set_commission_categories(self, cats: list[dict[str, Any]]) -> None:
        """整表覆盖佣金类目。"""
        self.s.execute(
            delete(ST).where(ST.c.user_id == 0, ST.c.key == _KEY_COMMISSION_CATS)
        )
        self.s.execute(
            insert(ST).values(
                user_id=0,
                key=_KEY_COMMISSION_CATS,
                value=dumps_json(cats or []),
            )
        )
