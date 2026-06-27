"""WarehouseRepo 单测：绑 SQLite 临时库，验证 5 个方法的语义 parity。"""
import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.warehouse_repo import WarehouseRepo
from ozon_common.dal.schema import metadata


def _bind(tmp):
    """构建 SQLite engine 并初始化 schema，返回 engine 供 dispose。"""
    eng = build_engine(f"sqlite:///{Path(tmp) / 'wh.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# ---------- upsert_warehouses / list_warehouses ----------

def test_upsert_and_list_warehouses():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            items = [
                {"warehouse_id": 1, "name": "仓A", "is_rfbs": True, "status": "ACTIVE"},
                {"warehouse_id": 2, "name": "仓B", "is_rfbs": False, "status": "DISABLED"},
            ]
            with S.session_scope():
                WarehouseRepo().upsert_warehouses(items, store_client_id="shop1")

            with S.session_scope():
                rows = WarehouseRepo().list_warehouses()
            assert len(rows) == 2
            r1 = next(r for r in rows if r["warehouse_id"] == 1)
            assert r1["name"] == "仓A"
            assert r1["is_rfbs"] is True
            assert r1["status"] == "ACTIVE"
            assert r1["store_client_id"] == "shop1"
        finally:
            eng.dispose()


def test_list_warehouses_filter_by_store():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                WarehouseRepo().upsert_warehouses(
                    [{"warehouse_id": 10, "name": "S1仓", "is_rfbs": False, "status": "ACTIVE"}],
                    store_client_id="shop1",
                )
                WarehouseRepo().upsert_warehouses(
                    [{"warehouse_id": 20, "name": "S2仓", "is_rfbs": False, "status": "ACTIVE"}],
                    store_client_id="shop2",
                )

            with S.session_scope():
                only_shop1 = WarehouseRepo().list_warehouses(store_client_id="shop1")
            assert len(only_shop1) == 1
            assert only_shop1[0]["warehouse_id"] == 10

            with S.session_scope():
                all_wh = WarehouseRepo().list_warehouses(store_client_id=None)
            assert len(all_wh) == 2
        finally:
            eng.dispose()


def test_upsert_overwrites_existing():
    """二次 upsert 同 warehouse_id 应覆盖旧值。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                WarehouseRepo().upsert_warehouses(
                    [{"warehouse_id": 99, "name": "旧名", "is_rfbs": False, "status": "DISABLED"}],
                    store_client_id="s",
                )
                WarehouseRepo().upsert_warehouses(
                    [{"warehouse_id": 99, "name": "新名", "is_rfbs": True, "status": "ACTIVE"}],
                    store_client_id="s",
                )

            with S.session_scope():
                rows = WarehouseRepo().list_warehouses()
            assert len(rows) == 1
            assert rows[0]["name"] == "新名"
            assert rows[0]["is_rfbs"] is True
        finally:
            eng.dispose()


# ---------- set_default_warehouse ----------

def test_set_default_warehouse_only_one_default():
    """set_default_warehouse 后，该店只有一个 is_default=True，且是指定仓库。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                WarehouseRepo().upsert_warehouses(
                    [
                        {"warehouse_id": 1, "name": "A", "is_rfbs": False, "status": "ACTIVE"},
                        {"warehouse_id": 2, "name": "B", "is_rfbs": False, "status": "ACTIVE"},
                        {"warehouse_id": 3, "name": "C", "is_rfbs": False, "status": "ACTIVE"},
                    ],
                    store_client_id="shop1",
                )
                WarehouseRepo().set_default_warehouse(1, store_client_id="shop1")
                WarehouseRepo().set_default_warehouse(2, store_client_id="shop1")  # 切到 2

            with S.session_scope():
                rows = WarehouseRepo().list_warehouses(store_client_id="shop1")

            defaults = [r for r in rows if r["is_default"]]
            assert len(defaults) == 1
            assert defaults[0]["warehouse_id"] == 2
        finally:
            eng.dispose()


def test_set_default_warehouse_scoped_per_store():
    """不同店铺的 is_default 互不影响。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                WarehouseRepo().upsert_warehouses(
                    [{"warehouse_id": 1, "name": "W1", "is_rfbs": False, "status": "ACTIVE"}],
                    store_client_id="shop1",
                )
                WarehouseRepo().upsert_warehouses(
                    [{"warehouse_id": 2, "name": "W2", "is_rfbs": False, "status": "ACTIVE"}],
                    store_client_id="shop2",
                )
                WarehouseRepo().set_default_warehouse(1, store_client_id="shop1")
                WarehouseRepo().set_default_warehouse(2, store_client_id="shop2")

            with S.session_scope():
                s1 = WarehouseRepo().list_warehouses(store_client_id="shop1")
                s2 = WarehouseRepo().list_warehouses(store_client_id="shop2")

            assert s1[0]["is_default"] is True
            assert s2[0]["is_default"] is True
        finally:
            eng.dispose()


# ---------- replace_delivery_methods / list_delivery_methods ----------

def test_replace_delivery_methods_basic():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            items = [
                {
                    "delivery_method_id": 101,
                    "warehouse_id": 1,
                    "name": "普通",
                    "status": "ACTIVE",
                    "provider_id": 10,
                    "template_id": 20,
                    "tpl_integration_type": "API",
                    "is_express": False,
                    "cutoff": "18:00",
                    "sla_cut_in": 2,
                    "dropoff_name": "自提点A",
                    "dropoff_code": "DP001",
                    "dropoff_address": "莫斯科",
                    "dropoff_lat": 55.7,
                    "dropoff_lng": 37.6,
                    "created_at": "2024-01-01",
                    "updated_at": "2024-01-02",
                    "raw": {"extra": "data"},
                }
            ]
            with S.session_scope():
                WarehouseRepo().replace_delivery_methods(items, store_client_id="shop1")

            with S.session_scope():
                rows = WarehouseRepo().list_delivery_methods(store_client_id="shop1")

            assert len(rows) == 1
            r = rows[0]
            assert r["delivery_method_id"] == 101
            assert r["name"] == "普通"
            assert r["is_express"] is False
            assert r["dropoff_name"] == "自提点A"
            assert r["dropoff_lat"] == 55.7
            assert r["store_client_id"] == "shop1"
        finally:
            eng.dispose()


def test_replace_delivery_methods_full_replace():
    """第二次 replace 应「全删再插」——旧行消失，新行生效。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            first = [
                {"delivery_method_id": 1, "warehouse_id": 10, "name": "旧1", "status": "ACTIVE",
                 "is_express": False, "raw": {}},
                {"delivery_method_id": 2, "warehouse_id": 10, "name": "旧2", "status": "ACTIVE",
                 "is_express": False, "raw": {}},
            ]
            second = [
                {"delivery_method_id": 3, "warehouse_id": 10, "name": "新1", "status": "ACTIVE",
                 "is_express": True, "raw": {"k": "v"}},
            ]
            with S.session_scope():
                WarehouseRepo().replace_delivery_methods(first, store_client_id="shop1")

            with S.session_scope():
                WarehouseRepo().replace_delivery_methods(second, store_client_id="shop1")

            with S.session_scope():
                rows = WarehouseRepo().list_delivery_methods(store_client_id="shop1")

            assert len(rows) == 1
            assert rows[0]["delivery_method_id"] == 3
            assert rows[0]["is_express"] is True
        finally:
            eng.dispose()


def test_replace_scoped_by_store():
    """replace_delivery_methods 只删指定店的行，不影响其他店。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                WarehouseRepo().replace_delivery_methods(
                    [{"delivery_method_id": 1, "warehouse_id": 1, "name": "S1配送",
                      "status": "ACTIVE", "is_express": False, "raw": {}}],
                    store_client_id="shop1",
                )
                WarehouseRepo().replace_delivery_methods(
                    [{"delivery_method_id": 2, "warehouse_id": 2, "name": "S2配送",
                      "status": "ACTIVE", "is_express": False, "raw": {}}],
                    store_client_id="shop2",
                )

            # 只替换 shop1
            with S.session_scope():
                WarehouseRepo().replace_delivery_methods(
                    [{"delivery_method_id": 99, "warehouse_id": 1, "name": "S1新",
                      "status": "ACTIVE", "is_express": False, "raw": {}}],
                    store_client_id="shop1",
                )

            with S.session_scope():
                s1 = WarehouseRepo().list_delivery_methods(store_client_id="shop1")
                s2 = WarehouseRepo().list_delivery_methods(store_client_id="shop2")

            assert len(s1) == 1 and s1[0]["delivery_method_id"] == 99
            assert len(s2) == 1 and s2[0]["delivery_method_id"] == 2
        finally:
            eng.dispose()


def test_list_delivery_methods_no_filter():
    """store_client_id=None 返回所有店的配送方式。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                WarehouseRepo().replace_delivery_methods(
                    [{"delivery_method_id": 1, "warehouse_id": 1, "name": "A",
                      "status": "ACTIVE", "is_express": False, "raw": {}}],
                    store_client_id="shop1",
                )
                WarehouseRepo().replace_delivery_methods(
                    [{"delivery_method_id": 2, "warehouse_id": 2, "name": "B",
                      "status": "ACTIVE", "is_express": False, "raw": {}}],
                    store_client_id="shop2",
                )

            with S.session_scope():
                all_dm = WarehouseRepo().list_delivery_methods(store_client_id=None)

            assert len(all_dm) == 2
        finally:
            eng.dispose()
