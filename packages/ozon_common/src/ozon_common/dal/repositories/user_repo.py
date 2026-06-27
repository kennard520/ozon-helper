"""UserRepo — users 聚合的 SQLAlchemy Core 仓储。

方法签名与返回形状与 Store 完全对齐：
  - get_user_by_*   → dict[str, Any] | None（整行 mapping）
  - list_users      → list[dict]（不含 password_hash，字段顺序同 Store）
  - create_user     → dict[str, Any]（整行，委托 get_user_by_id 返回）
  - count_users     → int
  - set_*/delete_*  → None

delete_user 为硬删：同步删关联表（草稿/钱包/流水/设置 + store_client_id 关联），
保持与 Store 原有行为一致（仅 SQLAlchemy Core 改写，语义不变）。
password_hash 原样存取，不碰任何认证/哈希逻辑。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, func, insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import (
    delivery_methods,
    drafts,
    offer_snapshots,
    postings,
    procurement,
    settings,
    warehouses,
)
from ozon_common.dal.schema import (
    users as T,
)
from ozon_common.jsonio import utc_now_iso


def _row(row) -> dict[str, Any] | None:
    """将 SQLAlchemy Row 转成 dict；None 输入原样返回 None。"""
    return dict(row._mapping) if row is not None else None


class UserRepo(BaseRepo):
    # ------------------------------------------------------------------ #
    # 读取                                                                 #
    # ------------------------------------------------------------------ #

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        row = self.s.execute(
            select(T).where(T.c.username == username)
        ).first()
        return _row(row)

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        row = self.s.execute(
            select(T).where(T.c.id == int(user_id))
        ).first()
        return _row(row)

    def count_users(self) -> int:
        return int(self.s.execute(select(func.count()).select_from(T)).scalar())

    def list_users(self) -> list[dict[str, Any]]:
        """返回 id/username/role/status/max_stores/created_at（不含 password_hash）。"""
        rows = self.s.execute(
            select(
                T.c.id,
                T.c.username,
                T.c.role,
                T.c.status,
                T.c.max_stores,
                T.c.created_at,
            ).order_by(T.c.id)
        ).all()
        return [dict(r._mapping) for r in rows]

    # ------------------------------------------------------------------ #
    # 写入                                                                 #
    # ------------------------------------------------------------------ #

    def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = "user",
        max_stores: int = 1,
    ) -> dict[str, Any]:
        result = self.s.execute(
            insert(T).values(
                username=username,
                password_hash=password_hash,
                role=role,
                status="active",
                created_at=utc_now_iso(),
                max_stores=int(max_stores),
            )
        )
        uid = result.inserted_primary_key[0]
        return self.get_user_by_id(uid)  # type: ignore[return-value]

    def set_max_stores(self, user_id: int, max_stores: int) -> None:
        self.s.execute(
            update(T)
            .where(T.c.id == int(user_id))
            .values(max_stores=int(max_stores))
        )

    def set_status(self, user_id: int, status: str) -> None:
        self.s.execute(
            update(T)
            .where(T.c.id == int(user_id))
            .values(status=str(status))
        )

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        self.s.execute(
            update(T)
            .where(T.c.id == int(user_id))
            .values(password_hash=str(password_hash))
        )

    def delete_user(self, user_id: int) -> None:
        """硬删用户：连同 user_id 关联数据（草稿/钱包/流水/设置）+
        其店铺的 store_client_id 关联数据（仓库/订单/采购/快照）一起删。不可逆。"""
        uid = int(user_id)

        # 1. 收集该用户的 store_client_id 集合（同 Store 逻辑）
        cids: set[str] = set()

        row = self.s.execute(
            select(settings.c.value).where(
                settings.c.user_id == uid,
                settings.c.key == "ozon_stores",
            )
        ).first()
        if row:
            for st in (self._loads_json(row[0], []) or []):
                c = str((st or {}).get("client_id") or "").strip()
                if c:
                    cids.add(c)

        row2 = self.s.execute(
            select(settings.c.value).where(
                settings.c.user_id == uid,
                settings.c.key == "ozon_client_id",
            )
        ).first()
        if row2:
            c = str(self._loads_json(row2[0], "") or "").strip()
            if c:
                cids.add(c)

        # 2. 删 store_client_id 关联数据
        for tbl in (warehouses, delivery_methods, postings, procurement, offer_snapshots):
            for c in cids:
                self.s.execute(
                    delete(tbl).where(tbl.c.store_client_id == c)
                )

        # 3. 删 user_id 关联数据
        #    accounts / account_txns 由 FK ON DELETE CASCADE(M4d,user_id 维度)
        #    随用户行级联删除,无需手写;此处只处理无 FK 的 settings,
        #    以及随 drafts 级联清空 draft_images/gen_jobs/gen_job_images 的 drafts。
        for tbl in (drafts, settings):
            self.s.execute(delete(tbl).where(tbl.c.user_id == uid))

        # 4. 删用户行本身(accounts/account_txns 经 FK CASCADE 一并删除)
        self.s.execute(delete(T).where(T.c.id == uid))

    # ------------------------------------------------------------------ #
    # 内部工具                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _loads_json(value: Any, default: Any) -> Any:
        """等价于 Store 里的 loads_json(value, default)。"""
        try:
            return json.loads(value)
        except Exception:
            return default
