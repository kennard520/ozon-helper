"""OrderRepo 单测：SQLite 临时库，覆盖 6 个方法的核心语义。"""
import tempfile
from pathlib import Path

import pytest

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.order_repo import OrderRepo
from ozon_common.dal.schema import metadata


def _bind(tmp: str):
    """构建 SQLite engine 并初始化 schema，返回 engine 供 dispose。"""
    eng = build_engine(f"sqlite:///{Path(tmp) / 'o.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# ---------------------------------------------------------------------------
# upsert_postings / list_postings / get_posting
# ---------------------------------------------------------------------------

def test_upsert_and_list_postings():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            items = [
                {
                    "posting_number": "PN-001",
                    "ozon_order_id": "O-1",
                    "status": "awaiting_deliver",
                    "ship_by": "2026-07-01",
                    "products": [{"offer_id": "SKU-A", "quantity": 2}],
                    "warehouse_id": 100,
                    "raw": {"k": "v"},
                },
                {
                    "posting_number": "PN-002",
                    "status": "cancelled",
                    "products": [],
                    "raw": {},
                },
            ]
            with S.session_scope():
                OrderRepo().upsert_postings(items, store_client_id="store1")

            with S.session_scope():
                rows = OrderRepo().list_postings(store_client_id="store1")

            assert len(rows) == 2
            pn1 = next(r for r in rows if r["posting_number"] == "PN-001")
            assert pn1["status"] == "awaiting_deliver"
            assert pn1["ship_by"] == "2026-07-01"
            # JSON 列已还原
            assert isinstance(pn1["products"], list)
            assert pn1["products"][0]["offer_id"] == "SKU-A"
            assert isinstance(pn1["raw"], dict)
            assert pn1["raw"]["k"] == "v"
            # products_json/raw_json 不暴露在外层
            assert "products_json" not in pn1
            assert "raw_json" not in pn1
        finally:
            eng.dispose()


def test_list_postings_store_filter():
    """list_postings(store_client_id=...) 只返回对应店的行。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            items_s1 = [{"posting_number": "PN-S1", "status": "x", "products": [], "raw": {}}]
            items_s2 = [{"posting_number": "PN-S2", "status": "y", "products": [], "raw": {}}]
            with S.session_scope():
                OrderRepo().upsert_postings(items_s1, store_client_id="storeA")
                OrderRepo().upsert_postings(items_s2, store_client_id="storeB")

            with S.session_scope():
                rows_a = OrderRepo().list_postings(store_client_id="storeA")
                rows_none = OrderRepo().list_postings()  # None = 不过滤

            assert len(rows_a) == 1
            assert rows_a[0]["posting_number"] == "PN-S1"
            assert len(rows_none) == 2
        finally:
            eng.dispose()


def test_get_posting_found_and_not_found():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [{"posting_number": "PN-X", "status": "ok", "products": [{"offer_id": "AA"}], "raw": {}}]
                )

            with S.session_scope():
                found = OrderRepo().get_posting("PN-X")
                missing = OrderRepo().get_posting("NO-SUCH")

            assert found is not None
            assert found["posting_number"] == "PN-X"
            assert isinstance(found["products"], list)
            assert missing is None
        finally:
            eng.dispose()


def test_upsert_postings_overwrites():
    """相同 posting_number 再次 upsert 应覆盖旧数据。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [{"posting_number": "PN-DUP", "status": "old", "products": [], "raw": {}}]
                )
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [{"posting_number": "PN-DUP", "status": "new", "products": [], "raw": {}}]
                )

            with S.session_scope():
                rows = OrderRepo().list_postings()

            assert len(rows) == 1
            assert rows[0]["status"] == "new"
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# rebuild_procurement / list_procurement
# ---------------------------------------------------------------------------

def test_rebuild_procurement_generates_rows():
    """rebuild_procurement 应从 postings 的 products 生成采购行。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            scid = "storeX"
            postings_data = [
                {
                    "posting_number": "PN-R1",
                    "status": "awaiting_deliver",
                    "products": [
                        {"offer_id": "SKU-1", "quantity": 3},
                        {"offer_id": "SKU-2", "quantity": 1},
                    ],
                    "raw": {},
                },
            ]
            with S.session_scope():
                OrderRepo().upsert_postings(postings_data, store_client_id=scid)
                OrderRepo().rebuild_procurement(store_client_id=scid)

            with S.session_scope():
                rows = OrderRepo().list_procurement(store_client_id=scid)

            assert len(rows) == 2
            by_offer = {r["offer_id"]: r for r in rows}
            assert by_offer["SKU-1"]["qty"] == 3
            assert by_offer["SKU-2"]["qty"] == 1
            # 默认状态
            assert by_offer["SKU-1"]["purchase_state"] == "待采购"
            assert by_offer["SKU-1"]["store_client_id"] == scid
        finally:
            eng.dispose()


def test_rebuild_procurement_preserves_state():
    """rebuild_procurement 重建时保留已有行的 purchase_state 和 note。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            scid = "storeY"
            posting = [
                {
                    "posting_number": "PN-PRES",
                    "status": "x",
                    "products": [{"offer_id": "SKU-Z", "quantity": 2}],
                    "raw": {},
                }
            ]
            with S.session_scope():
                OrderRepo().upsert_postings(posting, store_client_id=scid)
                OrderRepo().rebuild_procurement(store_client_id=scid)

            # 先查到 id
            with S.session_scope():
                rows = OrderRepo().list_procurement(store_client_id=scid)
            pid = rows[0]["id"]

            # 改状态
            with S.session_scope():
                OrderRepo().set_procurement_state(pid, "已采购", note="供应商备货中")

            # 再次 rebuild，状态应保留
            with S.session_scope():
                OrderRepo().rebuild_procurement(store_client_id=scid)

            with S.session_scope():
                rows2 = OrderRepo().list_procurement(store_client_id=scid)

            assert len(rows2) == 1
            assert rows2[0]["purchase_state"] == "已采购"
            assert rows2[0]["note"] == "供应商备货中"
        finally:
            eng.dispose()


def test_list_procurement_joins_draft_title():
    """list_procurement 按 offer_id+店 JOIN drafts 补 title/posting_status；
    ozon_title 优先，空回退 source_title，查不到草稿则空串。"""
    from sqlalchemy import insert as _insert

    from ozon_common.dal.schema import drafts as _DR

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            scid = "storeT"
            # 草稿1：ozon_title 有值；草稿2：ozon_title 空 → 回退 source_title
            with S.session_scope():
                base = dict(
                    user_id=1, source_platform="1688", source_url="u",
                    source_title="源标题", ozon_title="", description="d",
                    category_id="1", price="10", old_price="10", stock=1,
                    images_json="[]", attributes_json="{}", status="draft",
                    validation_errors_json="[]", purchase_url="",
                    type_id="", brand_name="", supplier="", source="",
                    media_status="done", variant_group="",
                    created_at="2026-06-28T00:00:00",
                    updated_at="2026-06-28T00:00:00", store_client_id=scid,
                )
                S.current_session().execute(
                    _insert(_DR).values({**base, "source_url": "u1", "offer_id": "SKU-1",
                                         "ozon_title": "俄语标题1", "source_title": "源1"})
                )
                S.current_session().execute(
                    _insert(_DR).values({**base, "source_url": "u2", "offer_id": "SKU-2",
                                         "ozon_title": "", "source_title": "源2"})
                )
            postings_data = [{
                "posting_number": "PN-T1", "status": "awaiting_packaging",
                "products": [{"offer_id": "SKU-1", "quantity": 2},
                             {"offer_id": "SKU-2", "quantity": 1},
                             {"offer_id": "NO-DRAFT", "quantity": 1}],
                "raw": {},
            }]
            with S.session_scope():
                OrderRepo().upsert_postings(postings_data, store_client_id=scid)
                OrderRepo().rebuild_procurement(store_client_id=scid)

            with S.session_scope():
                rows = OrderRepo().list_procurement(store_client_id=scid)

            by_offer = {r["offer_id"]: r for r in rows}
            assert by_offer["SKU-1"]["title"] == "俄语标题1"
            assert by_offer["SKU-2"]["title"] == "源2"  # ozon_title 空 → source_title
            assert by_offer["NO-DRAFT"]["title"] == ""   # 无草稿 → 空串
            assert by_offer["SKU-1"]["posting_status"] == "awaiting_packaging"
            # 行数不被 JOIN 放大（每个采购行恰好一行）
            assert len(rows) == 3
        finally:
            eng.dispose()


def test_list_procurement_store_filter():
    """list_procurement 按店过滤。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            for scid, pn, offer in [("sA", "PN-A", "OA"), ("sB", "PN-B", "OB")]:
                with S.session_scope():
                    OrderRepo().upsert_postings(
                        [{"posting_number": pn, "status": "x",
                          "products": [{"offer_id": offer, "quantity": 1}], "raw": {}}],
                        store_client_id=scid,
                    )
                    OrderRepo().rebuild_procurement(store_client_id=scid)

            with S.session_scope():
                rows_a = OrderRepo().list_procurement(store_client_id="sA")
                rows_all = OrderRepo().list_procurement()

            assert len(rows_a) == 1
            assert rows_a[0]["offer_id"] == "OA"
            assert len(rows_all) == 2
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# set_procurement_state
# ---------------------------------------------------------------------------

def test_set_procurement_state_without_note():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [{"posting_number": "PN-ST", "status": "x",
                      "products": [{"offer_id": "SK1", "quantity": 1}], "raw": {}}]
                )
                OrderRepo().rebuild_procurement()

            with S.session_scope():
                rows = OrderRepo().list_procurement()
            pid = rows[0]["id"]

            with S.session_scope():
                OrderRepo().set_procurement_state(pid, "已采购")

            with S.session_scope():
                rows2 = OrderRepo().list_procurement()
            assert rows2[0]["purchase_state"] == "已采购"
            # note 保持旧值（空字符串）
            assert rows2[0]["note"] == ""
        finally:
            eng.dispose()


def test_set_procurement_state_with_note():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                OrderRepo().upsert_postings(
                    [{"posting_number": "PN-NT", "status": "x",
                      "products": [{"offer_id": "SK2", "quantity": 1}], "raw": {}}]
                )
                OrderRepo().rebuild_procurement()

            with S.session_scope():
                rows = OrderRepo().list_procurement()
            pid = rows[0]["id"]

            with S.session_scope():
                OrderRepo().set_procurement_state(pid, "已到货", note="快递到了")

            with S.session_scope():
                rows2 = OrderRepo().list_procurement()
            assert rows2[0]["purchase_state"] == "已到货"
            assert rows2[0]["note"] == "快递到了"
        finally:
            eng.dispose()
