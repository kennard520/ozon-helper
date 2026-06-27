"""OfferSnapshotRepo 单测 — 绑 SQLite 临时库验证三个方法。"""
import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.offer_snapshot_repo import OfferSnapshotRepo
from ozon_common.dal.schema import metadata


def _bind(tmp: str):
    """构建 SQLite engine 并初始化 schema，返回 engine 供 dispose。"""
    eng = build_engine(f"sqlite:///{Path(tmp) / 'snap.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# ---------------------------------------------------------------------------
# add + latest
# ---------------------------------------------------------------------------

def test_add_and_latest():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            # 写两条快照，同 product_id，captured_at 不同
            with S.session_scope():
                r1 = OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P001",
                    "sku": "SKU-A",
                    "captured_at": "2024-01-01T00:00:00Z",
                    "follow_count": 3,
                    "price_min": 10.5,
                    "price_max": 20.0,
                    "sellers_json": '["s1"]',
                    "store_client_id": "store1",
                })
                r2 = OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P001",
                    "sku": "SKU-B",
                    "captured_at": "2024-06-01T00:00:00Z",
                    "follow_count": 5,
                    "price_min": 11.0,
                    "price_max": 22.0,
                    "sellers_json": '["s2","s3"]',
                    "store_client_id": "store1",
                })

            # 验证 add 返回 id
            assert "id" in r1
            assert "id" in r2
            assert r2["id"] > r1["id"]

            # latest 应返回 captured_at 最大的那条(r2)
            with S.session_scope():
                latest = OfferSnapshotRepo().latest_offer_snapshot("P001")

            assert latest is not None
            assert latest["sku"] == "SKU-B"
            assert latest["follow_count"] == 5
            assert latest["price_min"] == 11.0
            assert latest["sellers_json"] == '["s2","s3"]'
            # latest 不含 store_client_id（与 Store 保持一致）
            assert "store_client_id" not in latest
        finally:
            eng.dispose()


def test_latest_returns_none_for_missing():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                assert OfferSnapshotRepo().latest_offer_snapshot("NO_SUCH") is None
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_order_and_fields():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P002",
                    "captured_at": "2024-03-01T00:00:00Z",
                    "follow_count": 1,
                })
                OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P002",
                    "captured_at": "2024-01-01T00:00:00Z",
                    "follow_count": 2,
                })
                OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P002",
                    "captured_at": "2024-06-01T00:00:00Z",
                    "follow_count": 3,
                })

            with S.session_scope():
                rows = OfferSnapshotRepo().list_offer_snapshots("P002")

            assert len(rows) == 3
            # ASC by captured_at
            assert rows[0]["follow_count"] == 2  # 2024-01
            assert rows[1]["follow_count"] == 1  # 2024-03
            assert rows[2]["follow_count"] == 3  # 2024-06

            # 字段完整性
            for r in rows:
                assert "id" in r
                assert "product_id" in r
                assert r["product_id"] == "P002"
                assert "sku" in r
                assert "captured_at" in r
                assert "follow_count" in r
                assert "price_min" in r
                assert "price_max" in r
                assert "sellers_json" in r
                assert "store_client_id" not in r
        finally:
            eng.dispose()


def test_list_limit():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                for i in range(5):
                    OfferSnapshotRepo().add_offer_snapshot({
                        "product_id": "P003",
                        "captured_at": f"2024-0{i+1}-01T00:00:00Z",
                    })

            with S.session_scope():
                rows = OfferSnapshotRepo().list_offer_snapshots("P003", limit=3)

            assert len(rows) == 3
        finally:
            eng.dispose()


def test_list_empty():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                rows = OfferSnapshotRepo().list_offer_snapshots("NOPE")
            assert rows == []
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# store_client_id 写入存储（add 时写，只是 SELECT 不返回）
# ---------------------------------------------------------------------------

def test_store_client_id_stored():
    """add 时 store_client_id 确实写入数据库。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            from sqlalchemy import select as sa_select

            from ozon_common.dal.schema import offer_snapshots as T_

            with S.session_scope():
                OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P004",
                    "store_client_id": "my_store",
                })

            with S.session_scope():
                row = S._current_session.get().execute(
                    sa_select(T_.c.store_client_id).where(T_.c.product_id == "P004")
                ).scalar()
            assert row == "my_store"
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# 类型强转（int/float 兼容性）
# ---------------------------------------------------------------------------

def test_type_coercion():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                OfferSnapshotRepo().add_offer_snapshot({
                    "product_id": "P005",
                    "follow_count": "7",   # 字符串 → int
                    "price_min": "9.99",  # 字符串 → float
                    "price_max": None,    # None → None
                })

            with S.session_scope():
                latest = OfferSnapshotRepo().latest_offer_snapshot("P005")

            assert latest["follow_count"] == 7
            assert latest["price_min"] == 9.99
            assert latest["price_max"] is None
        finally:
            eng.dispose()
