"""in_gallery 列:create_all 含该列,默认 1。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, insert, select

from ozon_common.dal.schema import draft_images as DI
from ozon_common.dal.schema import drafts as DR
from ozon_common.dal.schema import metadata


def test_in_gallery_column_default_1():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = create_engine(f"sqlite:///{Path(tmp) / 'g.db'}")
        try:
            metadata.create_all(eng)
            assert "in_gallery" in DI.c, "draft_images 缺 in_gallery 列"
            with eng.begin() as c:
                c.execute(
                    insert(DR).values(
                        id=1,
                        user_id=1,
                        source_platform="1688",
                        source_url="u",
                        source_title="title",
                        purchase_url="",
                        ozon_title="",
                        description="",
                        category_id="",
                        price="0",
                        old_price="0",
                        stock=0,
                        images_json="[]",
                        attributes_json="[]",
                        status="draft",
                        validation_errors_json="[]",
                        created_at="2026-01-01T00:00:00+00:00",
                        updated_at="2026-01-01T00:00:00+00:00",
                    )
                )
                c.execute(
                    insert(DI).values(
                        draft_id=1,
                        position=0,
                        url="x",
                        created_at="2026-01-01T00:00:00+00:00",
                    )
                )
                v = c.execute(
                    select(DI.c.in_gallery).where(DI.c.url == "x")
                ).scalar()
            assert v == 1, f"in_gallery 默认应为 1,实际 {v}"
        finally:
            eng.dispose()
