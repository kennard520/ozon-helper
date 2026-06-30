"""钱列 Numeric(18,4) + WalletRepo Decimal 往返精确性单测（M4b）。

float 累加会有误差（0.1*3 == 0.30000000000000004），Decimal 精确（== 0.30）。
绑临时 SQLite，session_scope 内验证 recharge/deduct 的 Decimal 精确累加 + balance_after。
"""
import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import insert

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.wallet_repo import WalletRepo
from ozon_common.dal.schema import metadata, users


def _bind(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'm.db'}")
    metadata.create_all(eng)
    # accounts.user_id FK -> users.id(M4d):备好 user_id=1。
    with eng.begin() as conn:
        conn.execute(
            insert(users).values(
                id=1, username="u1", password_hash="x",
                created_at="2026-01-01 00:00:00.000000",
            )
        )
    S.bind_engine(eng)
    return eng


def test_recharge_decimal_exact_accumulation():
    """recharge 0.10 三次 → 精确 0.30（float 会 0.30000000000000004）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(0.10, user_id=1)
                repo.recharge(0.10, user_id=1)
                repo.recharge(0.10, user_id=1)
                acc = repo.get_account(1)
                assert isinstance(acc["balance"], Decimal)
                assert acc["balance"] == Decimal("0.30")
                assert acc["total_recharge"] == Decimal("0.30")
        finally:
            eng.dispose()


def test_deduct_decimal_exact():
    """0.30 - 0.10 → 精确 0.20。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(0.10, user_id=1)
                repo.recharge(0.10, user_id=1)
                repo.recharge(0.10, user_id=1)
                assert repo.deduct(0.10, user_id=1) is True
                acc = repo.get_account(1)
                assert acc["balance"] == Decimal("0.20")
                assert acc["total_consume"] == Decimal("0.10")
        finally:
            eng.dispose()


def test_deduct_insufficient_keeps_decimal():
    """余额不足拒绝，账户不变（仍为精确 Decimal）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(0.10, user_id=1)
                assert repo.deduct(0.50, user_id=1) is False
                acc = repo.get_account(1)
                assert acc["balance"] == Decimal("0.10")
                assert acc["total_consume"] == Decimal("0")
        finally:
            eng.dispose()


def test_balance_after_decimal_exact():
    """流水 balance_after 精确：连续小额 recharge 的 balance_after 序列。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(0.10, user_id=1)
                repo.recharge(0.10, user_id=1)
                repo.recharge(0.10, user_id=1)
                txns = repo.list_txns(1)  # id DESC
                # 最新一条 balance_after == 0.30（精确）
                assert txns[0]["balance_after"] == Decimal("0.30")
                assert txns[0]["amount"] == Decimal("0.10")
                # 验证三条 balance_after 序列精确
                bas = sorted(t["balance_after"] for t in txns)
                assert bas == [Decimal("0.10"), Decimal("0.20"), Decimal("0.30")]
        finally:
            eng.dispose()
