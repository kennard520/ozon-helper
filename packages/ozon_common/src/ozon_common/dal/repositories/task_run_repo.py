from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import task_runs as TR
from ozon_common.jsonio import dumps_json, loads_json, utc_now_iso

_DEFAULT_USER_ID = 1
_FINISHED_STATUSES = {"done", "failed", "skipped", "cancelled"}
_ACTIVE_STATUSES = {"queued", "running", "cancel_requested"}


def _uid(user_id: int | None) -> int:
    return int(user_id) if user_id is not None else _DEFAULT_USER_ID


def _serialize_result(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return dumps_json(value)


def _row_dict(row: Any) -> dict[str, Any]:
    data = dict(row._mapping)
    data["result"] = loads_json(data.pop("result_json", None), None)
    return data


def _time_patch(values: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_iso()
    out = dict(values)
    out["updated_at"] = now
    status = str(out.get("status") or "")
    if status in {"running"} and not out.get("started_at"):
        out["started_at"] = now
    if status in _FINISHED_STATUSES and not out.get("finished_at"):
        out["finished_at"] = now
    return out


class TaskRunRepo(BaseRepo):
    def create(
        self,
        draft_id: int | None,
        task_type: str,
        user_id: int | None = None,
        status: str = "queued",
        progress_current: int = 0,
        progress_total: int = 0,
        error: str | None = None,
        result: Any = None,
        source: str = "",
        external_id: str | int | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        values = {
            "draft_id": None if draft_id is None else int(draft_id),
            "user_id": _uid(user_id),
            "task_type": str(task_type),
            "status": str(status),
            "progress_current": int(progress_current or 0),
            "progress_total": int(progress_total or 0),
            "error": error,
            "result_json": _serialize_result(result),
            "source": str(source or ""),
            "external_id": None if external_id is None else str(external_id),
            "created_at": now,
            "updated_at": now,
        }
        if values["status"] == "running":
            values["started_at"] = now
        if values["status"] in _FINISHED_STATUSES:
            values["finished_at"] = now
        res = self.s.execute(insert(TR).values(**values))
        return self.get(int(res.inserted_primary_key[0]))  # type: ignore[return-value]

    def get(self, run_id: int) -> dict[str, Any] | None:
        row = self.s.execute(select(TR).where(TR.c.id == int(run_id))).first()
        return _row_dict(row) if row is not None else None

    def get_by_external(
        self,
        task_type: str,
        source: str,
        external_id: str | int,
    ) -> dict[str, Any] | None:
        row = self.s.execute(
            select(TR)
            .where(
                TR.c.task_type == str(task_type),
                TR.c.source == str(source or ""),
                TR.c.external_id == str(external_id),
            )
            .order_by(TR.c.id.desc())
            .limit(1)
        ).first()
        return _row_dict(row) if row is not None else None

    def update(self, run_id: int, patch: dict[str, Any]) -> dict[str, Any] | None:
        values: dict[str, Any] = {}
        for key, value in patch.items():
            if key == "id":
                continue
            if key == "result":
                values["result_json"] = _serialize_result(value)
            elif key in TR.c:
                values[key] = value
        if not values:
            return self.get(run_id)
        self.s.execute(update(TR).where(TR.c.id == int(run_id)).values(**_time_patch(values)))
        return self.get(run_id)

    def upsert_external(
        self,
        draft_id: int | None,
        task_type: str,
        source: str,
        external_id: str | int,
        user_id: int | None = None,
        **patch: Any,
    ) -> dict[str, Any]:
        existing = self.get_by_external(task_type, source, external_id)
        if existing is not None:
            return self.update(existing["id"], patch)  # type: ignore[return-value]
        return self.create(
            draft_id=draft_id,
            task_type=task_type,
            user_id=user_id,
            source=source,
            external_id=external_id,
            **patch,
        )

    def latest_for_draft(
        self, draft_id: int, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        rows = self.s.execute(
            select(TR)
            .where(TR.c.draft_id == int(draft_id), TR.c.user_id == _uid(user_id))
            .order_by(TR.c.id.desc())
        ).all()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = _row_dict(row)
            out.setdefault(str(item["task_type"]), item)
        return list(out.values())

    def latest_by_type(
        self, draft_id: int, task_type: str, user_id: int | None = None
    ) -> dict[str, Any] | None:
        row = self.s.execute(
            select(TR)
            .where(
                TR.c.draft_id == int(draft_id),
                TR.c.user_id == _uid(user_id),
                TR.c.task_type == str(task_type),
            )
            .order_by(TR.c.id.desc())
            .limit(1)
        ).first()
        return _row_dict(row) if row is not None else None

    def fail_stale_active(self, timeout_seconds: int = 1800) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(timeout_seconds or 1800))
        rows = self.s.execute(select(TR).where(TR.c.status.in_(_ACTIVE_STATUSES))).all()
        count = 0
        for row in rows:
            item = _row_dict(row)
            raw = str(item.get("updated_at") or item.get("created_at") or "")
            try:
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts > cutoff:
                continue
            self.update(item["id"], {
                "status": "failed",
                "error": f"task timeout after {int(timeout_seconds or 1800)}s",
                "result": {**(item.get("result") or {}), "phase": "timeout"},
            })
            count += 1
        return count
