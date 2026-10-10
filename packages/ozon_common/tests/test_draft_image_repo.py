"""DraftImageRepo 单测:add_draft_image / load_draft_images / get_draft。

使用临时 SQLite 库,绑定模式与 test_settings_repo.py 相同。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import insert

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo
from ozon_common.dal.schema import drafts as DR
from ozon_common.dal.schema import metadata
from ozon_common.jsonio import utc_now_iso


def _bind(tmp: str):
    """构建 SQLite engine 并初始化 schema,返回 engine 供 dispose。"""
    eng = build_engine(f"sqlite:///{Path(tmp) / 'd.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _insert_draft(*, source_url: str = "https://detail.1688.com/offer/1.html",
                  source_raw_json: str | None = None) -> int:
    """在 session_scope 内插入一条最小 drafts 行,返回新 id。"""
    now = utc_now_iso()
    res = S.current_session().execute(
        insert(DR).values(
            user_id=1,
            store_client_id="",
            source_platform="1688",
            source_url=source_url,
            source_offer_id="",
            source_title="测试商品",
            purchase_url="",
            purchase_note="",
            ozon_title="Test Product",
            description="desc",
            category_id="123",
            type_id="",
            brand_id=None,
            brand_name="",
            price="100",
            old_price="120",
            stock=10,
            images_json="[]",
            attributes_json="{}",
            source_raw_json=source_raw_json,
            status="draft",
            validation_errors_json="[]",
            created_at=now,
            updated_at=now,
        )
    )
    return int(res.inserted_primary_key[0])


# ---------------------------------------------------------------------------
# 用例 1: add_draft_image + load_draft_images
# ---------------------------------------------------------------------------

def test_add_and_load_draft_images():
    """add_draft_image 按插入序追加,load_draft_images 按 position 升序返回,type/source 正确。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftImageRepo()

            with S.session_scope():
                draft_id = _insert_draft()

                id1 = repo.add_draft_image(draft_id, "http://x.com/a.jpg",
                                           type="白底", source="collected")
                id2 = repo.add_draft_image(draft_id, "http://x.com/b.jpg",
                                           type="场景", source="generated")
                id3 = repo.add_draft_image(draft_id, "http://x.com/c.jpg",
                                           type="", source="generated")

                # id 递增(返回值为整数)
                assert isinstance(id1, int)
                assert id2 > id1
                assert id3 > id2

                imgs = repo.load_draft_images(draft_id)
                assert len(imgs) == 3
                assert imgs[0] == {"url": "http://x.com/a.jpg", "type": "白底",  "source": "collected"}
                assert imgs[1] == {"url": "http://x.com/b.jpg", "type": "场景",  "source": "generated"}
                assert imgs[2] == {"url": "http://x.com/c.jpg", "type": "",      "source": "generated"}
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# 用例 2: get_draft — images 列表 + source_raw.image_types
# ---------------------------------------------------------------------------

def test_get_draft_images_and_source_raw():
    """get_draft 返回 images=[url, ...] 且 source_raw['image_types'] 映射正确。"""
    import json

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            repo = DraftImageRepo()

            with S.session_scope():
                draft_id = _insert_draft(
                    source_url="https://detail.1688.com/offer/2.html",
                    source_raw_json=json.dumps({"foo": "bar"}),
                )
                repo.add_draft_image(draft_id, "http://x.com/1.jpg", type="白底",  source="collected")
                repo.add_draft_image(draft_id, "http://x.com/2.jpg", type="卖点",  source="generated")
                repo.add_draft_image(draft_id, "http://x.com/3.jpg", type="",      source="generated")

                d = repo.get_draft(draft_id)

            assert d is not None
            # 基础字段
            assert d["id"] == draft_id
            assert d["source_platform"] == "1688"
            assert d["category_id"] == "123"
            assert d["type_id"] == ""
            # 语义变更:DraftImageRepo._row_to_draft 只取图集(in_gallery=1)
            # source="collected"(图1) → in_gallery=0 → 不在 images
            # source="generated"(图2/3)  → in_gallery=1 → 在 images
            assert d["images"] == [
                "http://x.com/2.jpg",
                "http://x.com/3.jpg",
            ]
            # source_raw 保留原有字段 + 注入 image_types(只图集图)
            assert d["source_raw"]["foo"] == "bar"
            it = d["source_raw"]["image_types"]
            assert it["http://x.com/2.jpg"] == "卖点"
            # type="" 和 source="collected" 的条目不进 image_types
            assert "http://x.com/1.jpg" not in it
            assert "http://x.com/3.jpg" not in it
            # images_json 空数组
            assert d["images_json"] == []
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# 用例 3: get_draft 不存在时返回 None
# ---------------------------------------------------------------------------

def test_get_draft_not_found():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                result = DraftImageRepo().get_draft(99999)
            assert result is None
        finally:
            eng.dispose()
