"""写入落池:采集图→素材(in_gallery=0),AI出图→图集(in_gallery=1);
_sync 图集感知:编辑图集不删素材、不删表全行。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, func, select

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.schema import draft_images as DI
from ozon_common.dal.schema import metadata
from webui.drafts import create_draft_from_url


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'w.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def test_collected_to_material_ai_to_gallery_and_sync_keeps_material():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope():
                d = create_draft_from_url("https://detail.1688.com/offer/100000000002.html")
                d["images"] = ["http://c/0.jpg", "http://c/1.jpg"]
                result = DraftRepo().insert_draft(d, user_id=1, store_cid="", errors=[], status="draft",
                                                  offer_id_base="1688-100000000002")
                did = result["id"]
            with S.session_scope():
                got = DraftRepo().get_draft(did, user_id=1)
            assert got["images"] == []
            assert {m["url"] for m in got["materials"]} == {"http://c/0.jpg", "http://c/1.jpg"}
            assert all(m["in_gallery"] == 0 for m in got["materials"])
            with S.session_scope():
                DraftImageRepo().add_draft_image(did, "http://ai/main.jpg", type="白底主图", source="generated")
            with S.session_scope():
                got = DraftRepo().get_draft(did, user_id=1)
            assert got["images"] == ["http://ai/main.jpg"]
            with S.session_scope():
                DraftRepo()._sync_draft_images(did, ["http://ai/main.jpg"])
                n = S.current_session().execute(
                    select(func.count()).select_from(DI).where(DI.c.draft_id == did)).scalar()
            assert n == 3, f"总行数应为 3(2素材+1图集),实际 {n}——_sync 删了素材"
        finally:
            eng.dispose()
