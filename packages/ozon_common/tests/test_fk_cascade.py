"""FK ON DELETE CASCADE 单测(M4d)。

绑临时 SQLite(必须用 build_engine —— 它已开 PRAGMA foreign_keys=ON,
裸 create_engine 不强制 FK,级联不会触发)。create_all 后在 session_scope 内
插父子行,删父行,断言子表随级联清空。

覆盖 3 条级联链:
  drafts -> draft_images / gen_jobs -> gen_job_images
  users  -> accounts / account_txns
  postings -> procurement
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import delete, func, insert, select

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.schema import (
    account_txns,
    accounts,
    draft_images,
    drafts,
    gen_job_images,
    gen_jobs,
    metadata,
    postings,
    procurement,
    users,
)
from ozon_common.jsonio import utc_now_iso


def _bind(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'fk.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _count(sess, tbl, **conds) -> int:
    stmt = select(func.count()).select_from(tbl)
    for col, val in conds.items():
        stmt = stmt.where(tbl.c[col] == val)
    return int(sess.execute(stmt).scalar() or 0)


def _new_draft(sess, now: str) -> int:
    res = sess.execute(
        insert(drafts).values(
            user_id=1,
            source_platform="1688",
            source_url="https://detail.1688.com/offer/fk.html",
            source_title="t",
            ozon_title="t",
            description="d",
            category_id="1",
            price="1",
            old_price="1",
            stock=1,
            images_json="[]",
            attributes_json="{}",
            status="ready",
            validation_errors_json="[]",
            created_at=now,
            updated_at=now,
        )
    )
    return int(res.inserted_primary_key[0])


def test_drafts_cascade_to_images_and_gen_jobs():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope() as sess:
                now = utc_now_iso()
                did = _new_draft(sess, now)
                # 2 行 draft_images
                for i in range(2):
                    sess.execute(
                        insert(draft_images).values(
                            draft_id=did, position=i, url=f"u{i}", created_at=now
                        )
                    )
                # gen_job + gen_job_images
                gj = sess.execute(
                    insert(gen_jobs).values(
                        draft_id=did, user_id=1, status="queued",
                        created_at=now, updated_at=now,
                    )
                )
                job_id = int(gj.inserted_primary_key[0])
                sess.execute(
                    insert(gen_job_images).values(
                        job_id=job_id, status="pending", updated_at=now
                    )
                )

                assert _count(sess, draft_images, draft_id=did) == 2
                assert _count(sess, gen_jobs, id=job_id) == 1
                assert _count(sess, gen_job_images, job_id=job_id) == 1

                # 删父草稿 -> 子表随级联清空
                sess.execute(delete(drafts).where(drafts.c.id == did))

                assert _count(sess, draft_images, draft_id=did) == 0
                assert _count(sess, gen_jobs, id=job_id) == 0
                # gen_job_images 经 gen_jobs 二级级联也应清空
                assert _count(sess, gen_job_images, job_id=job_id) == 0
        finally:
            eng.dispose()


def test_users_cascade_to_accounts_and_txns():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope() as sess:
                now = utc_now_iso()
                res = sess.execute(
                    insert(users).values(
                        username="fkuser", password_hash="x", created_at=now
                    )
                )
                uid = int(res.inserted_primary_key[0])
                sess.execute(insert(accounts).values(user_id=uid, balance=0))
                sess.execute(
                    insert(account_txns).values(
                        user_id=uid, txn_type="recharge", amount=1, created_at=now
                    )
                )

                assert _count(sess, accounts, user_id=uid) == 1
                assert _count(sess, account_txns, user_id=uid) == 1

                sess.execute(delete(users).where(users.c.id == uid))

                assert _count(sess, accounts, user_id=uid) == 0
                assert _count(sess, account_txns, user_id=uid) == 0
        finally:
            eng.dispose()


def test_postings_cascade_to_procurement():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope() as sess:
                pn = "FK-POST-1"
                sess.execute(insert(postings).values(posting_number=pn, status="x"))
                sess.execute(
                    insert(procurement).values(posting_number=pn, offer_id="o1")
                )

                assert _count(sess, procurement, posting_number=pn) == 1

                sess.execute(
                    delete(postings).where(postings.c.posting_number == pn)
                )

                assert _count(sess, procurement, posting_number=pn) == 0
        finally:
            eng.dispose()
