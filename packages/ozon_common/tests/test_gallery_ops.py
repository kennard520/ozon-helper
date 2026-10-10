"""细粒度图集操作:add/remove/delete/reorder 按 id,id 稳定,素材不误删。"""
import tempfile
from pathlib import Path

from sqlalchemy import insert, select

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo
from ozon_common.dal.schema import draft_images as DI
from ozon_common.dal.schema import drafts as DR
from ozon_common.dal.schema import metadata
from ozon_common.jsonio import utc_now_iso


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'o.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _seed(did):
    s = S.current_session()
    now = utc_now_iso()
    s.execute(insert(DR).values(
        id=did,
        user_id=1,
        store_client_id="",
        source_platform="1688",
        source_url=f"u{did}",
        source_offer_id="",
        source_title="测试商品",
        purchase_url="",
        ozon_title="Test Product",
        description="desc",
        category_id="123",
        type_id="",
        brand_name="",
        price="100",
        old_price="120",
        stock=10,
        images_json="[]",
        attributes_json="{}",
        status="draft",
        validation_errors_json="[]",
        created_at=now,
        updated_at=now,
    ))
    ids = []
    for i, ig in enumerate([0, 0, 1]):  # 2素材 + 1图集
        r = s.execute(insert(DI).values(draft_id=did, position=i, url=f"http://x/{i}.jpg",
                      type="", source="collected", in_gallery=ig,
                      created_at=now))
        ids.append(int(r.inserted_primary_key[0]))
    return ids  # [mat0, mat1, gal2]


def test_add_remove_delete_reorder():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope():
                ids = _seed(1)
            with S.session_scope():
                DraftImageRepo().add_to_gallery(1, [ids[0]])
            with S.session_scope():
                g = S.current_session().execute(
                    select(DI.c.in_gallery).where(DI.c.id == ids[0])).scalar()
            assert g == 1
            with S.session_scope():
                DraftImageRepo().remove_from_gallery(1, [ids[2]])
            with S.session_scope():
                g = S.current_session().execute(
                    select(DI.c.in_gallery).where(DI.c.id == ids[2])).scalar()
            assert g == 0
            with S.session_scope():
                DraftImageRepo().delete_image(1, ids[1])
            with S.session_scope():
                left = {int(r.id) for r in S.current_session().execute(
                    select(DI.c.id).where(DI.c.draft_id == 1)).all()}
            assert ids[1] not in left and ids[0] in left
            with S.session_scope():
                DraftImageRepo().reorder_gallery(1, [ids[0]])
                p = S.current_session().execute(
                    select(DI.c.position).where(DI.c.id == ids[0])).scalar()
            assert p == 0
        finally:
            eng.dispose()
