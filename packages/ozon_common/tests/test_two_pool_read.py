"""get_draft:images=图集(in_gallery=1),materials=全部(带 id/in_gallery)。"""
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import insert

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.schema import draft_images as DI
from ozon_common.dal.schema import metadata
from webui.drafts import create_draft_from_url


def _setup(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 't.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _payload(url: str) -> dict[str, Any]:
    d = create_draft_from_url(url)
    d["images"] = []  # 不带任何图,测试自己插
    return d


def test_images_is_gallery_materials_is_all():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            did: int
            with S.session_scope():
                d = _payload("https://detail.1688.com/offer/100000000001.html")
                result = DraftRepo().insert_draft(
                    d,
                    user_id=1,
                    store_cid="",
                    errors=[],
                    status="draft",
                    offer_id_base="1688-100000000001",
                )
                did = result["id"]
                # 插入一张素材图(in_gallery=0)
                S.current_session().execute(insert(DI).values(
                    draft_id=did, position=0, url="http://m/material.jpg",
                    type="细节图", source="collected", in_gallery=0,
                    created_at="2026-01-01T00:00:00+00:00"))
                # 插入一张图集图(in_gallery=1)
                S.current_session().execute(insert(DI).values(
                    draft_id=did, position=1, url="http://m/gallery.jpg",
                    type="白底主图", source="generated", in_gallery=1,
                    created_at="2026-01-01T00:00:00+00:00"))
            with S.session_scope():
                got = DraftRepo().get_draft(did, user_id=1)
            assert got is not None
            # images 只含图集
            assert got["images"] == ["http://m/gallery.jpg"], f"images 应只含图集: {got['images']}"
            # materials 含全部两张
            assert "materials" in got, "get_draft 结果缺 materials 字段"
            urls = {m["url"]: m for m in got["materials"]}
            assert set(urls) == {"http://m/material.jpg", "http://m/gallery.jpg"}, \
                f"materials url 集合不符: {set(urls)}"
            assert urls["http://m/material.jpg"]["in_gallery"] == 0
            assert urls["http://m/gallery.jpg"]["in_gallery"] == 1
            assert isinstance(urls["http://m/material.jpg"]["id"], int)
            assert urls["http://m/gallery.jpg"]["type"] == "白底主图"
        finally:
            eng.dispose()
