"""WalletRepo — 钱包聚合（accounts + account_txns）的 SQLAlchemy Core 仓储。

方法签名/返回形状与 Store 完全对齐：
  - get_account → dict[str, Any]（整行 mapping；不存在则 lazy 开户 0 余额）
  - recharge / refund → dict[str, Any]（操作后整账户行，委托 get_account）
  - deduct → bool（成功 True；余额不足 False，账户不变）
  - list_txns → list[dict]（按 id DESC，limit 截断）

⚠️ 原子性：recharge/deduct/refund 各自「改 accounts 余额 + 写一条 account_txns 流水」
是复合操作。这些方法整体跑在 _in_scope 提供的单个 session 内（结束统一 commit），
余额改与流水写都在同一方法体（都用 self.s）→ 天然同一事务，原子。

金额用 Numeric(18,4)（M4b）；Python 层统一收发 Decimal 做精确算术，入参用
Decimal(str(amount)) 中转避免 float 直转 Decimal 引误差。
deduct 用条件 UPDATE（balance>=amount）防并发超扣，行为照搬。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import account_txns as TX
from ozon_common.dal.schema import accounts as AC
from ozon_common.jsonio import utc_now_iso


class WalletRepo(BaseRepo):
    # ------------------------------------------------------------------ #
    # 内部：写流水（与 Store._add_txn 等价，金额用 Decimal 精确入库）        #
    # ------------------------------------------------------------------ #
    def _add_txn(
        self,
        user_id: int,
        txn_type: str,
        amount: Decimal,
        balance_after: Decimal | None,
        biz_no: str | None,
        remark: str | None,
    ) -> None:
        self.s.execute(
            insert(TX).values(
                user_id=user_id,
                txn_type=txn_type,
                amount=Decimal(str(amount)),
                balance_after=(
                    None if balance_after is None else Decimal(str(balance_after))
                ),
                biz_no=biz_no,
                remark=remark,
                created_at=utc_now_iso(),
            )
        )

    # ------------------------------------------------------------------ #
    # 账户                                                                 #
    # ------------------------------------------------------------------ #
    def get_account(self, user_id: int) -> dict[str, Any]:
        """取账户，没有则开户（余额0）。"""
        uid = int(user_id)
        row = self.s.execute(select(AC).where(AC.c.user_id == uid)).first()
        if row is None:
            self.s.execute(
                insert(AC).values(
                    user_id=uid,
                    balance=Decimal("0"),
                    total_recharge=Decimal("0"),
                    total_consume=Decimal("0"),
                    updated_at=utc_now_iso(),
                )
            )
            row = self.s.execute(select(AC).where(AC.c.user_id == uid)).first()
        return dict(row._mapping)

    def _balance(self, user_id: int) -> Decimal:
        return self.s.execute(
            select(AC.c.balance).where(AC.c.user_id == int(user_id))
        ).scalar()

    def recharge(
        self,
        amount: float,
        *,
        remark: str = "",
        biz_no: str | None = None,
        user_id: int,
    ) -> dict[str, Any]:
        uid = int(user_id)
        amt = Decimal(str(amount))
        self.get_account(uid)
        self.s.execute(
            update(AC)
            .where(AC.c.user_id == uid)
            .values(
                balance=AC.c.balance + amt,
                total_recharge=AC.c.total_recharge + amt,
                updated_at=utc_now_iso(),
            )
        )
        bal = self._balance(uid)
        self._add_txn(uid, "recharge", amt, bal, biz_no, remark)
        return self.get_account(uid)

    def deduct(
        self,
        amount: float,
        *,
        biz_no: str | None = None,
        remark: str = "",
        user_id: int,
    ) -> bool:
        """原子扣款：仅 balance>=amount 才扣（条件 UPDATE 防并发超扣）。
        成功 True，余额不足 False。"""
        uid = int(user_id)
        amt = Decimal(str(amount))
        self.get_account(uid)
        cur = self.s.execute(
            update(AC)
            .where(AC.c.user_id == uid, AC.c.balance >= amt)
            .values(
                balance=AC.c.balance - amt,
                total_consume=AC.c.total_consume + amt,
                updated_at=utc_now_iso(),
            )
        )
        if cur.rowcount != 1:
            return False
        bal = self._balance(uid)
        self._add_txn(uid, "consume", amt, bal, biz_no, remark)
        return True

    def refund(
        self,
        amount: float,
        *,
        biz_no: str | None = None,
        remark: str = "",
        user_id: int,
    ) -> dict[str, Any]:
        uid = int(user_id)
        amt = Decimal(str(amount))
        self.get_account(uid)
        self.s.execute(
            update(AC)
            .where(AC.c.user_id == uid)
            .values(
                balance=AC.c.balance + amt,
                updated_at=utc_now_iso(),
            )
        )
        bal = self._balance(uid)
        self._add_txn(uid, "refund", amt, bal, biz_no, remark)
        return self.get_account(uid)

    def list_txns(self, user_id: int, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.s.execute(
            select(TX)
            .where(TX.c.user_id == int(user_id))
            .order_by(TX.c.id.desc())
            .limit(int(limit))
        ).all()
        return [dict(r._mapping) for r in rows]
