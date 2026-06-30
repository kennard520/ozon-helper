"""GenJobRepo — gen_jobs / gen_job_images 的 SQLAlchemy Core 访问层。

等价替换 webui store.py 中 12 个 gen_job 方法:
  create_gen_job / get_gen_job / get_latest_gen_job / list_gen_jobs /
  has_active_gen_job / update_gen_job / set_gen_job_status /
  create_gen_job_images / get_gen_job_images / update_gen_job_image /
  set_gen_job_image_status / count_gen_job_images_by_status

SQL 语义与 store.py 完全对齐;差异见下方注释。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import gen_job_images as GJI
from ozon_common.dal.schema import gen_jobs as GJ
from ozon_common.jsonio import utc_now_iso

# store.py 中 _uid(user_id) 对 None 返回 1
_DEFAULT_USER_ID = 1

# has_active_gen_job: store.py 用 IN ('queued','designing','running')
#   worker draft_images.py 没有 has_active_gen_job 方法,故以 store 为准
_ACTIVE_STATUSES = ("queued", "designing", "running")


def _uid(user_id: int | None) -> int:
    return int(user_id) if user_id is not None else _DEFAULT_USER_ID


class GenJobRepo(BaseRepo):
    # ------------------------------------------------------------------
    # gen_jobs 操作
    # ------------------------------------------------------------------

    def create_gen_job(
        self, draft_id: int, target: int, user_id: int | None = None
    ) -> dict[str, Any]:
        """INSERT 一条 gen_job,status=queued,返回完整行 dict。"""
        now = utc_now_iso()
        res = self.s.execute(
            insert(GJ).values(
                draft_id=int(draft_id),
                user_id=_uid(user_id),
                status="queued",
                target=int(target),
                total=0,
                succeeded=0,
                failed=0,
                created_at=now,
                updated_at=now,
            )
        )
        return self.get_gen_job(int(res.inserted_primary_key[0]))  # type: ignore[return-value]

    def get_gen_job(self, job_id: int) -> dict[str, Any] | None:
        """按 id 返回 gen_jobs 行 dict,不存在返回 None。"""
        row = self.s.execute(
            select(GJ).where(GJ.c.id == int(job_id))
        ).first()
        return dict(row._mapping) if row is not None else None

    def get_latest_gen_job(
        self, draft_id: int, user_id: int | None = None
    ) -> dict[str, Any] | None:
        """按 draft_id+user_id 返回最新(id 最大)一行,不存在返回 None。"""
        row = self.s.execute(
            select(GJ)
            .where(GJ.c.draft_id == int(draft_id), GJ.c.user_id == _uid(user_id))
            .order_by(GJ.c.id.desc())
            .limit(1)
        ).first()
        return dict(row._mapping) if row is not None else None

    def list_gen_jobs(
        self, draft_id: int, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        """按 draft_id+user_id 返回所有 gen_jobs 行,id 降序。"""
        rows = self.s.execute(
            select(GJ)
            .where(GJ.c.draft_id == int(draft_id), GJ.c.user_id == _uid(user_id))
            .order_by(GJ.c.id.desc())
        ).all()
        return [dict(r._mapping) for r in rows]

    def has_active_gen_job(
        self, draft_id: int, user_id: int | None = None
    ) -> bool:
        """返回 True 若存在 status IN (queued,designing,running) 的 gen_job。

        store.py 用 IN ('queued','designing','running');
        worker draft_images.py 无此方法,故以 store 为准。
        """
        cnt = self.s.execute(
            select(func.count()).where(
                GJ.c.draft_id == int(draft_id),
                GJ.c.user_id == _uid(user_id),
                GJ.c.status.in_(_ACTIVE_STATUSES),
            )
        ).scalar()
        return int(cnt or 0) > 0

    def update_gen_job(
        self, job_id: int, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        """动态 SET patch 中的列(跳过 'id')+ updated_at,返回更新后行。

        若 patch 为空(除 id 外无键),直接返回当前行(与 store 一致)。
        """
        keys = [k for k in patch if k != "id"]
        if not keys:
            return self.get_gen_job(job_id)
        values = {k: patch[k] for k in keys}
        values["updated_at"] = utc_now_iso()
        self.s.execute(
            update(GJ).where(GJ.c.id == int(job_id)).values(**values)
        )
        return self.get_gen_job(job_id)

    def set_gen_job_status(self, job_id: int, status: str) -> None:
        """仅更新 status + updated_at,无返回值。"""
        self.s.execute(
            update(GJ)
            .where(GJ.c.id == int(job_id))
            .values(status=str(status), updated_at=utc_now_iso())
        )

    # ------------------------------------------------------------------
    # gen_job_images 操作
    # ------------------------------------------------------------------

    def create_gen_job_images(
        self, job_id: int, slots: list[dict[str, Any]]
    ) -> None:
        """批量 INSERT gen_job_images 行,status 初始为 pending。"""
        now = utc_now_iso()
        for s in slots:
            self.s.execute(
                insert(GJI).values(
                    job_id=int(job_id),
                    slot_id=str(s.get("slot_id") or ""),
                    label=str(s.get("label") or ""),
                    status="pending",
                    updated_at=now,
                )
            )

    def get_gen_job_images(self, job_id: int) -> list[dict[str, Any]]:
        """按 id 升序返回 job 的所有图片行。"""
        rows = self.s.execute(
            select(GJI).where(GJI.c.job_id == int(job_id)).order_by(GJI.c.id)
        ).all()
        return [dict(r._mapping) for r in rows]

    def update_gen_job_image(self, image_id: int, patch: dict[str, Any]) -> None:
        """动态 SET patch 中的列(跳过 'id')+ updated_at。

        与 store.py 一致:无返回值。
        """
        keys = [k for k in patch if k != "id"]
        if not keys:
            return
        values = {k: patch[k] for k in keys}
        values["updated_at"] = utc_now_iso()
        self.s.execute(
            update(GJI).where(GJI.c.id == int(image_id)).values(**values)
        )

    def set_gen_job_image_status(
        self,
        image_id: int,
        status: str,
        url: str | None = None,
        error: str | None = None,
    ) -> None:
        """更新图片 status/url/error/updated_at。url/error 为 None 时写 NULL(同 store)。"""
        self.s.execute(
            update(GJI)
            .where(GJI.c.id == int(image_id))
            .values(
                status=str(status),
                url=url or None,
                error=error or None,
                updated_at=utc_now_iso(),
            )
        )

    def count_gen_job_images_by_status(self, job_id: int) -> dict[str, int]:
        """返回 {status: count} 字典。"""
        rows = self.s.execute(
            select(GJI.c.status, func.count().label("c"))
            .where(GJI.c.job_id == int(job_id))
            .group_by(GJI.c.status)
        ).all()
        return {str(r.status): int(r.c) for r in rows}
