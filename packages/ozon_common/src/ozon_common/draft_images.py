"""gen_jobs / draft_images 数据访问(worker 出图链路用)。"""

from __future__ import annotations

import json
from typing import Any

from ozon_common.db import make_conn
from ozon_common.jsonio import loads_json, utc_now_iso

USER_ID = 1  # worker 固定读取 admin 用户 settings


class DataStore:
    def __init__(self) -> None:
        self.conn = make_conn()

    def close(self) -> None:
        self.conn.close()

    # -- settings --

    def get_settings(self) -> dict:
        # 先读全局(user_id=0)，再读用户(user_id=1)覆盖
        out = {}
        for uid in (0, USER_ID):
            rows = self.conn.execute(
                "SELECT `key`, `value` FROM settings WHERE user_id=?", (uid,)
            ).fetchall()
            for r in rows:
                v = r["value"]
                if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
                    try:
                        out[r["key"]] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        out[r["key"]] = v
                else:
                    out[r["key"]] = v
        return out

    # -- drafts --

    def get_draft(self, draft_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_draft(row)

    def _row_to_draft(self, row) -> dict:
        dimg_rows = self.conn.execute(
            "SELECT url, type FROM draft_images WHERE draft_id=? ORDER BY position",
            (row["id"],),
        ).fetchall()
        images = [r["url"] for r in dimg_rows]
        image_types = {r["url"]: r["type"] for r in dimg_rows if r["type"]}
        source_raw = loads_json(row["source_raw_json"], {}) if "source_raw_json" in row.keys() else {}
        if image_types:
            source_raw["image_types"] = image_types
        elif "image_types" not in source_raw:
            source_raw["image_types"] = {}
        return {
            "id": row["id"],
            "source_platform": row["source_platform"],
            "source_url": row["source_url"],
            "source_title": row["source_title"],
            "ozon_title": row["ozon_title"],
            "description": row["description"],
            "category_id": row["category_id"],
            "type_id": row["type_id"] if "type_id" in row.keys() else "",
            "images": images,
            "source_raw": source_raw,
            "images_json": loads_json(row["images_json"], []) if "images_json" in row.keys() else [],
        }

    # -- draft_images --

    def add_draft_image(self, draft_id: int, url: str, *, type: str = "",
                        source: str = "generated") -> int:
        now = utc_now_iso()
        row = self.conn.execute(
            "SELECT GREATEST(IFNULL(MAX(position), -1), -1) + 1 AS next_pos"
            " FROM draft_images WHERE draft_id=?",
            (draft_id,),
        ).fetchone()
        pos = int(row["next_pos"]) if row else 0
        cur = self.conn.execute(
            "INSERT INTO draft_images (draft_id, position, url, type, source, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (draft_id, pos, str(url), str(type or ""), str(source), now),
        )
        self.conn.commit()
        return cur.lastrowid

    # -- gen_jobs --

    def get_gen_job(self, job_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM gen_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def update_gen_job(self, job_id: int, patch: dict) -> dict | None:
        keys = [k for k in patch if k != "id"]
        if not keys:
            return self.get_gen_job(job_id)
        now = utc_now_iso()
        sets = [f"{k}=?" for k in keys]
        vals = [patch[k] for k in keys]
        sets.append("updated_at=?")
        vals.append(now)
        vals.append(job_id)
        self.conn.execute(f"UPDATE gen_jobs SET {', '.join(sets)} WHERE id=?", tuple(vals))
        self.conn.commit()
        return self.get_gen_job(job_id)

    def set_gen_job_status(self, job_id: int, status: str) -> None:
        self.conn.execute("UPDATE gen_jobs SET status=?, updated_at=? WHERE id=?",
                          (str(status), utc_now_iso(), job_id))
        self.conn.commit()

    def create_gen_job_images(self, job_id: int, slots: list[dict]) -> None:
        now = utc_now_iso()
        for s in slots:
            self.conn.execute(
                "INSERT INTO gen_job_images (job_id, slot_id, label, status, updated_at)"
                " VALUES (?,?,?,?,?)",
                (job_id, str(s.get("slot_id") or ""), str(s.get("label") or ""), "pending", now),
            )
        self.conn.commit()

    def get_gen_job_images(self, job_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM gen_job_images WHERE job_id=? ORDER BY id ASC", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def set_gen_job_image_status(self, image_id: int, status: str, url: str | None = None,
                                 error: str | None = None) -> None:
        now = utc_now_iso()
        self.conn.execute(
            "UPDATE gen_job_images SET status=?, url=?, error=?, updated_at=? WHERE id=?",
            (str(status), url or None, error or None, now, image_id),
        )
        self.conn.commit()

    def count_gen_job_images_by_status(self, job_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) c FROM gen_job_images WHERE job_id=? GROUP BY status",
            (job_id,),
        ).fetchall()
        counts: dict[str, int] = {}
        for r in rows:
            counts[str(r["status"])] = int(r["c"])
        return counts
