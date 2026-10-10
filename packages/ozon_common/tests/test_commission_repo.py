"""CommissionRepo 单测 — SQLite 临时库冒烟。"""
import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.commission_repo import CommissionRepo
from ozon_common.dal.schema import metadata


def _bind(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'c.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# ---------- commission_map 表 ----------

def test_commission_map_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CommissionRepo().save_commission_map(
                    cat=101, type_id=20, parent_en="Electronics", sub_en="Laptops",
                    rfbs=[0.07, 0.09]
                )
            with S.session_scope():
                row = CommissionRepo().load_commission_map(101, 20)
                assert row is not None
                assert row["parent_en"] == "Electronics"
                assert row["sub_en"] == "Laptops"
                assert row["rfbs"] == [0.07, 0.09]
        finally:
            eng.dispose()


def test_commission_map_not_found():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                row = CommissionRepo().load_commission_map(999, 999)
                assert row is None
        finally:
            eng.dispose()


def test_commission_map_resave_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CommissionRepo().save_commission_map(
                    cat=101, type_id=20, parent_en="OldParent", sub_en="OldSub",
                    rfbs=[0.05]
                )
            with S.session_scope():
                CommissionRepo().save_commission_map(
                    cat=101, type_id=20, parent_en="NewParent", sub_en="NewSub",
                    rfbs=[0.10, 0.12]
                )
            with S.session_scope():
                row = CommissionRepo().load_commission_map(101, 20)
                assert row is not None
                assert row["parent_en"] == "NewParent"
                assert row["rfbs"] == [0.10, 0.12]
        finally:
            eng.dispose()


# ---------- realfbs_routes ----------

def test_realfbs_routes_none_before_set():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                result = CommissionRepo().get_realfbs_routes()
                assert result is None
        finally:
            eng.dispose()


def test_realfbs_routes_set_and_get():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            routes = [{"from": "MSK", "to": "SPB", "cost": 150.0}]
            with S.session_scope():
                CommissionRepo().set_realfbs_routes(routes)
            with S.session_scope():
                got = CommissionRepo().get_realfbs_routes()
                assert got == routes
        finally:
            eng.dispose()


def test_realfbs_routes_reset_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            routes1 = [{"from": "MSK", "to": "SPB", "cost": 150.0}]
            routes2 = [{"from": "MSK", "to": "EKB", "cost": 200.0}]
            with S.session_scope():
                CommissionRepo().set_realfbs_routes(routes1)
            with S.session_scope():
                CommissionRepo().set_realfbs_routes(routes2)
            with S.session_scope():
                got = CommissionRepo().get_realfbs_routes()
                assert got == routes2
        finally:
            eng.dispose()


# ---------- commission_categories ----------

def test_commission_categories_none_before_set():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                result = CommissionRepo().get_commission_categories()
                assert result is None
        finally:
            eng.dispose()


def test_commission_categories_set_and_get():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            cats = [{"id": 1, "name": "Electronics", "rate": 0.08}]
            with S.session_scope():
                CommissionRepo().set_commission_categories(cats)
            with S.session_scope():
                got = CommissionRepo().get_commission_categories()
                assert got == cats
        finally:
            eng.dispose()


def test_commission_categories_reset_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            cats1 = [{"id": 1, "name": "Electronics"}]
            cats2 = [{"id": 2, "name": "Clothing"}, {"id": 3, "name": "Books"}]
            with S.session_scope():
                CommissionRepo().set_commission_categories(cats1)
            with S.session_scope():
                CommissionRepo().set_commission_categories(cats2)
            with S.session_scope():
                got = CommissionRepo().get_commission_categories()
                assert got == cats2
                assert len(got) == 2
        finally:
            eng.dispose()
