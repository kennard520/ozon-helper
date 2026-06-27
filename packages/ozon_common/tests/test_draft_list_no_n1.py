"""M5:list_drafts_page 对 draft_images 只发 1 次 SELECT(N+1 消除)。"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import event

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.schema import metadata


def _setup(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'n1.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _payload(i: int) -> dict[str, Any]:
    return {
        "source_platform": "1688",
        "source_url": f"https://detail.1688.com/offer/10000000000{i}.html",
        "source_offer_id": "",
        "source_title": f"测试商品{i}",
        "purchase_url": "",
        "purchase_note": "",
        "ozon_title": f"Test Product {i}",
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
        "images": [f"http://x/{i}-0.jpg", f"http://x/{i}-1.jpg"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def test_list_drafts_page_batches_images():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            # 造 3 个草稿,各带 2 张图
            with S.session_scope():
                repo = DraftRepo()
                for i in range(3):
                    d = _payload(i)
                    repo.insert_draft(
                        d,
                        user_id=1,
                        store_cid="",
                        errors=[],
                        status="ready",
                        offer_id_base=f"1688-{i}",
                    )
            # 计数 draft_images 的 SELECT 次数
            counter = {"n": 0}

            @event.listens_for(eng, "before_cursor_execute")
            def _count(conn, cursor, statement, params, context, executemany):
                s = statement.lower()
                if "from draft_images" in s and s.strip().startswith("select"):
                    counter["n"] += 1

            with S.session_scope():
                drafts, total = DraftRepo().list_drafts_page(user_id=1, page=1, page_size=20)
            assert total == 3
            assert len(drafts) == 3
            # 每个草稿都带 2 张图(装配正确)
            assert all(len(d["images"]) == 2 for d in drafts)
            # 关键:draft_images 只查 1 次(批量),不是 3 次(N+1)
            assert counter["n"] == 1, f"draft_images 查询了 {counter['n']} 次(应为 1,N+1 未消除)"
        finally:
            eng.dispose()
