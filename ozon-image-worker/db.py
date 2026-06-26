"""MySQL 连接层：worker 轻量版，只连 MySQL（不连 SQLite）。"""

from __future__ import annotations

import os
import re
from typing import Any


def mysql_config() -> dict[str, Any]:
    return {
        "host": os.environ["OZON_MYSQL_HOST"],
        "port": int(os.environ.get("OZON_MYSQL_PORT") or 3306),
        "user": os.environ.get("OZON_MYSQL_USER") or "root",
        "password": os.environ.get("OZON_MYSQL_PASSWORD") or "",
        "database": os.environ.get("OZON_MYSQL_DB") or "ozon",
    }


# ---------------- SQL 方言翻译（SQLite -> MySQL） ----------------
_RE_COLLATE = re.compile(r"\bCOLLATE\s+NOCASE\b", re.IGNORECASE)
_RE_INS_REPLACE = re.compile(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", re.IGNORECASE)
_RE_INS_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.IGNORECASE)
_RE_UPSERT = re.compile(r"\bON\s+CONFLICT\s*\([^)]*\)\s*DO\s+UPDATE\s+SET\b", re.IGNORECASE)
_RE_EXCLUDED = re.compile(r"\bexcluded\.([A-Za-z_][A-Za-z0-9_]*)")
_RE_IGNORE_REQUESTS = re.compile(r"(?i)(?:--.*)?$")  # 放行注释行


def translate(sql: str) -> str:
    s = sql
    s = _RE_COLLATE.sub("", s)
    s = _RE_INS_REPLACE.sub("REPLACE INTO", s)
    s = _RE_INS_IGNORE.sub("INSERT IGNORE INTO", s)
    s = _RE_UPSERT.sub("ON DUPLICATE KEY UPDATE", s)
    s = _RE_EXCLUDED.sub(r"VALUES(\1)", s)
    s = s.replace("json_extract(value,'$')", "JSON_UNQUOTE(JSON_EXTRACT(`value`,'$'))")
    s = re.sub(r"(?<![\w.`])key(?![\w`])", "`key`", s)
    s = s.replace("?", "%s")
    return s


class Row:
    """兼容 sqlite3.Row：支持 row[i] / row['col'] / dict(row) / 'col' in row。"""
    __slots__ = ("_keys", "_vals", "_map")

    def __init__(self, keys: list[str], vals: tuple):
        self._keys = keys
        self._vals = vals
        self._map = dict(zip(keys, vals))

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._map[k]

    def keys(self):
        return list(self._keys)

    def __contains__(self, k):
        return k in self._map

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._vals)


class _Cursor:
    def __init__(self, cur):
        self._cur = cur
        self._cols = [d[0] for d in cur.description] if cur.description else []

    def fetchone(self):
        r = self._cur.fetchone()
        return Row(self._cols, r) if r is not None else None

    def fetchall(self):
        return [Row(self._cols, r) for r in self._cur.fetchall()]

    def __iter__(self):
        for r in self._cur:
            yield Row(self._cols, r)

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid


class MySQLConn:
    def __init__(self, cfg: dict[str, Any]):
        self._cfg = cfg
        self._conn = self._connect()

    def _connect(self):
        import pymysql
        from pymysql.constants import CLIENT
        c = pymysql.connect(
            charset="utf8mb4", autocommit=False, connect_timeout=10,
            client_flag=CLIENT.FOUND_ROWS,
            **self._cfg,
        )
        with c.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        c.commit()
        return c

    def _ensure(self):
        try:
            self._conn.ping(reconnect=True)
        except Exception:
            self._conn = self._connect()

    def execute(self, sql: str, params=None):
        self._ensure()
        cur = self._conn.cursor()
        cur.execute(translate(sql), tuple(params) if params else None)
        return _Cursor(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def make_conn() -> MySQLConn:
    return MySQLConn(mysql_config())
