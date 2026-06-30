"""TextJobRepo — text_jobs 的 SQLAlchemy Core 访问层。

「文本生成 MQ 异步任务」的状态表访问层(仿 GenJobRepo 写法)。
生命周期:queued → running → done/failed;
current_step 记跑到哪步(understand/category/copy/attrs),
steps_done 为逗号分隔的已完成步骤串(如 "understand,category")。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import text_jobs as TJ
from ozon_common.jsonio import utc_now_iso

# 与 store.py 一致:user_id 为 None 时回落到 1。
_DEFAULT_USER_ID = 1

# has_active: 仍在排队/执行中的状态。
_ACTIVE_STATUSES = ("queued", "running")


def _uid(user_id: int | None) -> int:
    return int(user_id) if user_id is not None else _DEFAULT_USER_ID


class TextJobRepo(BaseRepo):
    def create(self, draft_id: int, user_id: int | None = None) -> dict[str, Any]:
        """INSERT 一条 text_job,status=queued,返回完整行 dict。"""
        now = utc_now_iso()
        res = self.s.execute(
            insert(TJ).values(
                draft_id=int(draft_id),
                user_id=_uid(user_id),
                status="queued",
                created_at=now,
                updated_at=now,
            )
        )
        return self.get(int(res.inserted_primary_key[0]))  # type: ignore[return-value]

    def get(self, job_id: int) -> dict[str, Any] | None:
        """按 id 返回 text_jobs 行 dict,不存在返回 None。"""
        row = self.s.execute(
            select(TJ).where(TJ.c.id == int(job_id))
        ).first()
        return dict(row._mapping) if row is not None else None

    def get_latest(self, draft_id: int) -> dict[str, Any] | None:
        """按 draft_id 返回最新(created_at 降序)一行,不存在返回 None。"""
        row = self.s.execute(
            select(TJ)
            .where(TJ.c.draft_id == int(draft_id))
            .order_by(TJ.c.created_at.desc(), TJ.c.id.desc())
            .limit(1)
        ).first()
        return dict(row._mapping) if row is not None else None

    def update_status(
        self, job_id: int, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        """动态 SET patch 中的列(跳过 'id')+ updated_at,返回更新后行。

        可更新 status/current_step/steps_done/error。
        若 patch 为空(除 id 外无键),直接返回当前行(与 GenJobRepo 一致)。
        """
        keys = [k for k in patch if k != "id"]
        if not keys:
            return self.get(job_id)
        values = {k: patch[k] for k in keys}
        values["updated_at"] = utc_now_iso()
        self.s.execute(
            update(TJ).where(TJ.c.id == int(job_id)).values(**values)
        )
        return self.get(job_id)

    def has_active(self, draft_id: int) -> bool:
        """返回 True 若存在 status IN (queued,running) 的 text_job。"""
        cnt = self.s.execute(
            select(func.count()).where(
                TJ.c.draft_id == int(draft_id),
                TJ.c.status.in_(_ACTIVE_STATUSES),
            )
        ).scalar()
        return int(cnt or 0) > 0
