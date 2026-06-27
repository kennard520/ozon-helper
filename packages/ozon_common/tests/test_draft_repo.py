"""DraftRepo 单测:drafts + draft_images 聚合的关键路径。

临时 SQLite 库,绑定模式同 test_settings_repo.py / test_draft_image_repo.py。
覆盖:insert_draft(含 draft_images 同步) / get_draft 还原 / update_draft 改 images /
list_drafts_page 分页 + status 过滤 + group 模式 / find_by_source_url /
find_by_offer_id / count_by_status / delete_draft / set_media_status /
apply_media_oss / list_drafts_by_variant_group / list_pending_media_drafts /
set_ai_proposal。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.schema import metadata


def _bind(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'd.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _payload(**kw: Any) -> dict[str, Any]:
    """构造一个最小可插入的 draft payload(模拟 Store 传给 repo 的形状)。"""
    base = {
        "source_platform": "1688",
        "source_url": "https://detail.1688.com/offer/1.html",
        "source_offer_id": "",
        "source_title": "测试商品",
        "purchase_url": "",
        "purchase_note": "",
        "ozon_title": "Test Product",
        "description": "desc",
        "category_id": "123",
        "type_id": "",
        "brand_id": None,
        "brand_name": "",
        "price": "100",
        "old_price": "120",
        "stock": 10,
        "weight_g": None,
        "length_mm": None,
        "width_mm": None,
        "height_mm": None,
        "cost_cny": None,
        "video_url": "",
        "local_images": [],
        "source": "",
        "ozon_product_id": None,
        "offer_id": "",
        "supplier": "",
        "source_raw": {},
        "attributes": {},
        "status": "ready",
        "publish_response": None,
        "images": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(kw)
    return base


def _insert(repo: DraftRepo, draft: dict[str, Any], *, user_id: int = 1,
            store_cid: str = "", errors=None, status=None,
            offer_id_base: str = "1688-X") -> dict[str, Any]:
    errors = errors if errors is not None else []
    status = status if status is not None else ("invalid" if errors else draft["status"])
    return repo.insert_draft(
        draft, user_id=user_id, store_cid=store_cid,
        errors=errors, status=status, offer_id_base=offer_id_base,
    )


# ---------------------------------------------------------------------------
# insert_draft + get_draft 往返
# ---------------------------------------------------------------------------

def test_insert_and_get_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                p = _payload(
                    images=["http://x/a.jpg", "http://x/b.jpg"],
                    source_raw={"variant_group": "g1",
                                "image_types": {"http://x/a.jpg": "白底"}},
                )
                out = _insert(repo, p)
                assert out["id"] >= 1
                assert out["offer_id"]  # 已生成
                assert out["images"] == ["http://x/a.jpg", "http://x/b.jpg"]

                d = repo.get_draft(out["id"], 1)
                assert d is not None
                assert d["ozon_title"] == "Test Product"
                assert d["images"] == ["http://x/a.jpg", "http://x/b.jpg"]
                # image_types 注入 source_raw
                assert d["source_raw"]["image_types"]["http://x/a.jpg"] == "白底"
                assert d["source_raw"]["variant_group"] == "g1"
                assert d["status"] == "ready"
                assert d["media_status"] == "done"
        finally:
            eng.dispose()


def test_insert_dedup_by_source_url():
    """同 (user, store, source_url) 第二次 insert 返回旧草稿,不新建。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                a = _insert(repo, _payload())
                b = _insert(repo, _payload(ozon_title="改了标题"))
                assert a["id"] == b["id"]
                # 没新建,标题仍是旧的
                assert b["ozon_title"] == "Test Product"
        finally:
            eng.dispose()


def test_offer_id_collision_resolution():
    """offer_id 撞库自动加 -2。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                a = _insert(repo, _payload(source_url="u1"), offer_id_base="1688-RED")
                b = _insert(repo, _payload(source_url="u2"), offer_id_base="1688-RED")
                assert a["offer_id"] == "1688-RED"
                assert b["offer_id"] == "1688-RED-2"
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# update_draft 改 images(增删换序)
# ---------------------------------------------------------------------------

def test_update_draft_images_sync():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                out = _insert(repo, _payload(images=["a", "b", "c"]))
                did = out["id"]

                # 换序 + 删 c + 增 d
                cur = repo.get_draft(did, 1)
                updated = {**cur, "images": ["b", "a", "d"],
                           "updated_at": "2026-02-02T00:00:00+00:00"}
                res = repo.update_draft(
                    did, updated, user_id=1, errors=[], status="ready",
                    sync_images=True)
                assert res["images"] == ["b", "a", "d"]

                d = repo.get_draft(did, 1)
                assert d["images"] == ["b", "a", "d"]
                assert d["updated_at"] == "2026-02-02T00:00:00+00:00"
        finally:
            eng.dispose()


def test_update_draft_preserves_image_type_source():
    """换序保留旧行 type/source(按 url 匹配)。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                out = _insert(repo, _payload(
                    images=["a", "b"],
                    source_raw={"image_types": {"a": "白底", "b": "场景"}}))
                did = out["id"]
                # 只读 draft_images 行确认 type 保留
                rows = repo._load_draft_images(did)
                tmap = {r["url"]: r["type"] for r in rows}
                assert tmap["a"] == "白底"
                assert tmap["b"] == "场景"

                cur = repo.get_draft(did, 1)
                # source_raw 不再带 image_types(只换序),换序后旧 type 应保留
                updated = {**cur, "images": ["b", "a"]}
                updated["source_raw"] = {k: v for k, v in cur["source_raw"].items()
                                         if k != "image_types"}
                repo.update_draft(did, updated, user_id=1, errors=[],
                                  status="ready", sync_images=True)
                rows2 = repo._load_draft_images(did)
                tmap2 = {r["url"]: r["type"] for r in rows2}
                assert tmap2["a"] == "白底"
                assert tmap2["b"] == "场景"
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# list_drafts_page:分页 + status 过滤 + group 模式
# ---------------------------------------------------------------------------

def test_list_drafts_page_basic_pagination():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                for i in range(5):
                    _insert(repo, _payload(source_url=f"u{i}"),
                            offer_id_base=f"1688-{i}")
                rows, total = repo.list_drafts_page(
                    page=1, page_size=2, user_id=1)
                assert total == 5
                assert len(rows) == 2
                # id DESC
                assert rows[0]["id"] > rows[1]["id"]
                rows3, total3 = repo.list_drafts_page(
                    page=3, page_size=2, user_id=1)
                assert total3 == 5
                assert len(rows3) == 1
        finally:
            eng.dispose()


def test_list_drafts_page_status_filter():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                _insert(repo, _payload(source_url="u1", status="ready"),
                        status="ready", offer_id_base="1688-1")
                _insert(repo, _payload(source_url="u2", status="invalid"),
                        status="invalid", offer_id_base="1688-2")
                _insert(repo, _payload(source_url="u3", status="ready"),
                        status="ready", offer_id_base="1688-3")
                rows, total = repo.list_drafts_page(
                    status="ready", page=1, page_size=20, user_id=1)
                assert total == 2
                assert all(r["status"] == "ready" for r in rows)
        finally:
            eng.dispose()


def test_list_drafts_page_group_mode():
    """group=True:同 variant_group 只出代表行 + group_count,组级 status 过滤。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                # 组 g1 两个成员(代表=最新 id),组 g2 一个,无组一个
                _insert(repo, _payload(source_url="u1",
                        source_raw={"variant_group": "g1"}), offer_id_base="1688-1")
                _insert(repo, _payload(source_url="u2",
                        source_raw={"variant_group": "g1"}), offer_id_base="1688-2")
                _insert(repo, _payload(source_url="u3",
                        source_raw={"variant_group": "g2"}), offer_id_base="1688-3")
                _insert(repo, _payload(source_url="u4", source_raw={}),
                        offer_id_base="1688-4")
                rows, total = repo.list_drafts_page(
                    page=1, page_size=20, user_id=1, group=True)
                # 3 组:g1, g2, 无组单行
                assert total == 3
                # g1 组代表带 group_count=2
                g1 = next(r for r in rows if r["source_raw"].get("variant_group") == "g1")
                assert g1["group_count"] == 2
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# count_by_status
# ---------------------------------------------------------------------------

def test_count_by_status():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                _insert(repo, _payload(source_url="u1"), status="ready",
                        offer_id_base="1688-1")
                _insert(repo, _payload(source_url="u2"), status="ready",
                        offer_id_base="1688-2")
                _insert(repo, _payload(source_url="u3"), status="invalid",
                        offer_id_base="1688-3")
                c = repo.count_by_status(1)
                assert c["all"] == 3
                assert c["ready"] == 2
                assert c["invalid"] == 1
        finally:
            eng.dispose()


def test_count_by_status_group():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                _insert(repo, _payload(source_url="u1",
                        source_raw={"variant_group": "g1"}), status="ready",
                        offer_id_base="1688-1")
                _insert(repo, _payload(source_url="u2",
                        source_raw={"variant_group": "g1"}), status="ready",
                        offer_id_base="1688-2")
                c = repo.count_by_status(1, group=True)
                # 一组算一条
                assert c["all"] == 1
                assert c["ready"] == 1
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# find_by_source_url / find_by_offer_id
# ---------------------------------------------------------------------------

def test_find_by_source_url_and_offer_id():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                out = _insert(repo, _payload(source_url="uX"),
                              offer_id_base="1688-OID")
                by_url = repo.find_by_source_url("uX", 1)
                assert by_url is not None
                assert by_url["id"] == out["id"]
                by_oid = repo.find_by_offer_id(out["offer_id"], 1)
                assert by_oid is not None
                assert by_oid["id"] == out["id"]
                # 不存在
                assert repo.find_by_source_url("nope", 1) is None
                assert repo.find_by_offer_id("nope", 1) is None
        finally:
            eng.dispose()


def test_find_by_source_url_store_scoped():
    """store_client_id 非 None 时按店过滤。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                _insert(repo, _payload(source_url="u"), store_cid="A",
                        offer_id_base="1688-A")
                _insert(repo, _payload(source_url="u"), store_cid="B",
                        offer_id_base="1688-B")
                a = repo.find_by_source_url("u", 1, "A")
                b = repo.find_by_source_url("u", 1, "B")
                assert a is not None and a["store_client_id"] == "A"
                assert b is not None and b["store_client_id"] == "B"
                # store_client_id=None 不过滤,返回最新
                any_ = repo.find_by_source_url("u", 1)
                assert any_ is not None
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# delete_draft 级联删 draft_images
# ---------------------------------------------------------------------------

def test_delete_draft_cascades_images():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                out = _insert(repo, _payload(images=["a", "b"]))
                did = out["id"]
                assert len(repo._load_draft_images(did)) == 2
                repo.delete_draft(did, 1)
                assert repo.get_draft(did, 1) is None
                assert repo._load_draft_images(did) == []
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# set_media_status / apply_media_oss / list_pending_media_drafts
# ---------------------------------------------------------------------------

def test_media_status_flow():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                out = _insert(repo, _payload(
                    images=["http://old/a.jpg", "http://old/b.jpg"],
                    video_url="http://old/v.mp4"))
                did = out["id"]
                repo.set_media_status(did, "pending")
                d = repo.get_draft(did, 1)
                assert d["media_status"] == "pending"

                pending = repo.list_pending_media_drafts(1)
                assert len(pending) == 1
                assert pending[0]["id"] == did
                assert pending[0]["images"] == ["http://old/a.jpg", "http://old/b.jpg"]
                assert pending[0]["video_url"] == "http://old/v.mp4"

                # apply_media_oss 换 URL + done
                repo.apply_media_oss(did, {
                    "http://old/a.jpg": "http://oss/a.jpg",
                    "http://old/v.mp4": "http://oss/v.mp4",
                })
                d2 = repo.get_draft(did, 1)
                assert d2["images"] == ["http://oss/a.jpg", "http://old/b.jpg"]
                assert d2["video_url"] == "http://oss/v.mp4"
                assert d2["media_status"] == "done"
                # 已 done,不再出现在 pending
                assert repo.list_pending_media_drafts(1) == []
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# list_drafts_by_variant_group
# ---------------------------------------------------------------------------

def test_list_drafts_by_variant_group():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                _insert(repo, _payload(source_url="u1",
                        source_raw={"variant_group": "grp"}), offer_id_base="1688-1")
                _insert(repo, _payload(source_url="u2",
                        source_raw={"variant_group": "grp"}), offer_id_base="1688-2")
                _insert(repo, _payload(source_url="u3",
                        source_raw={"variant_group": "other"}), offer_id_base="1688-3")
                rows = repo.list_drafts_by_variant_group("grp")
                assert len(rows) == 2
                # id 升序
                assert rows[0]["id"] < rows[1]["id"]
                assert repo.list_drafts_by_variant_group("") == []
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# set_ai_proposal
# ---------------------------------------------------------------------------

def test_set_ai_proposal():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                out = _insert(repo, _payload())
                did = out["id"]
                repo.set_ai_proposal(did, {"title": "AI 标题"})
                d = repo.get_draft(did, 1)
                assert d["ai_proposal"] == {"title": "AI 标题"}
                repo.set_ai_proposal(did, None)
                d2 = repo.get_draft(did, 1)
                assert d2["ai_proposal"] is None
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# list_drafts:user 隔离
# ---------------------------------------------------------------------------

def test_list_drafts_user_isolation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftRepo()
            with S.session_scope():
                _insert(repo, _payload(source_url="u1"), user_id=1,
                        offer_id_base="1688-1")
                _insert(repo, _payload(source_url="u2"), user_id=2,
                        offer_id_base="1688-2")
                assert len(repo.list_drafts(1)) == 1
                assert len(repo.list_drafts(2)) == 1
        finally:
            eng.dispose()
