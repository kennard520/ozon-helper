import tempfile
from pathlib import Path

from sqlalchemy import insert

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.wallet_repo import WalletRepo
from ozon_common.dal.schema import account_txns, metadata, users


def _bind(tmp):
    """构建 SQLite engine 并初始化 schema,返回 engine 供 dispose。"""
    eng = build_engine(f"sqlite:///{Path(tmp) / 'w.db'}")
    metadata.create_all(eng)
    # accounts.user_id / account_txns.user_id 现有 FK -> users.id(M4d),
    # 先备好被测试引用的用户行。
    now = "2026-01-01 00:00:00.000000"
    with eng.begin() as conn:
        for uid in (1, 2, 5, 7, 9):
            conn.execute(
                insert(users).values(
                    id=uid, username=f"u{uid}", password_hash="x", created_at=now
                )
            )
    S.bind_engine(eng)
    return eng


def test_get_account_lazy_open():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                acc = WalletRepo().get_account(7)
                assert acc["user_id"] == 7
                assert acc["balance"] == 0
                assert acc["total_recharge"] == 0
                assert acc["total_consume"] == 0
        finally:
            eng.dispose()


def test_recharge_balance_and_txn():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                acc = WalletRepo().recharge(100, remark="test", user_id=1)
                assert acc["balance"] == 100
                assert acc["total_recharge"] == 100
                txns = WalletRepo().list_txns(1)
                assert len(txns) == 1
                assert txns[0]["txn_type"] == "recharge"
                assert txns[0]["balance_after"] == 100
                assert txns[0]["remark"] == "test"
        finally:
            eng.dispose()


def test_deduct_success_and_insufficient():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(50, user_id=1)
                assert repo.deduct(30, biz_no="x", user_id=1) is True
                assert repo.get_account(1)["balance"] == 20
                assert repo.get_account(1)["total_consume"] == 30
                # 余额不足：拒绝，账户不变，不写流水
                assert repo.deduct(30, user_id=1) is False
                assert repo.get_account(1)["balance"] == 20
                assert repo.get_account(1)["total_consume"] == 30
                # 一条 recharge + 一条 consume（失败那次不落流水）
                txns = repo.list_txns(1)
                assert [t["txn_type"] for t in txns] == ["consume", "recharge"]
        finally:
            eng.dispose()


def test_refund():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(50, user_id=1)
                repo.deduct(20, user_id=1)
                acc = repo.refund(20, biz_no="r", user_id=1)
                assert acc["balance"] == 50
                # refund 不动 total_recharge / total_consume
                assert acc["total_recharge"] == 50
                assert acc["total_consume"] == 20
                txns = repo.list_txns(1)
                assert txns[0]["txn_type"] == "refund"
                assert txns[0]["balance_after"] == 50
                assert txns[0]["biz_no"] == "r"
        finally:
            eng.dispose()


def test_list_txns_order_and_limit():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                for i in range(5):
                    repo.recharge(i + 1, remark=f"r{i}", user_id=1)
                # 默认顺序 id DESC（最新在前）
                txns = repo.list_txns(1)
                assert len(txns) == 5
                assert [t["amount"] for t in txns] == [5, 4, 3, 2, 1]
                # limit 截断
                limited = repo.list_txns(1, limit=2)
                assert len(limited) == 2
                assert [t["amount"] for t in limited] == [5, 4]
        finally:
            eng.dispose()


def test_wallet_isolated_by_user():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(100, user_id=1)
                repo.recharge(7, user_id=2)
                assert repo.get_account(1)["balance"] == 100
                assert repo.get_account(2)["balance"] == 7
                assert len(repo.list_txns(1)) == 1
                assert len(repo.list_txns(2)) == 1
        finally:
            eng.dispose()


def test_atomicity_balance_and_txn_same_session():
    """在同一 session_scope 内 recharge 后，用同一 session 读：
    accounts 余额与 account_txns 流水都已生效（同事务可见）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = WalletRepo()
                repo.recharge(42, biz_no="b1", remark="atomic", user_id=9)
                # 账户余额生效
                assert repo.get_account(9)["balance"] == 42
                # 流水同步生效（同一 session 内可见）
                rows = S.current_session().execute(
                    account_txns.select().where(account_txns.c.user_id == 9)
                ).all()
                assert len(rows) == 1
                m = dict(rows[0]._mapping)
                assert m["amount"] == 42
                assert m["balance_after"] == 42
                assert m["biz_no"] == "b1"
        finally:
            eng.dispose()
