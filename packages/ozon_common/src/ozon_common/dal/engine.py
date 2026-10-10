"""SQLAlchemy engine 工厂:SQLite(WAL)与 MySQL(连接池)。"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


def _sqlite_url(path: str) -> str:
    return f"sqlite:///{path}"


def build_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, future=True)

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng
    return create_engine(
        url, future=True,
        pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600,
    )


def mysql_url_from_env() -> str | None:
    host = os.environ.get("OZON_MYSQL_HOST")
    if not host:
        return None
    port = int(os.environ.get("OZON_MYSQL_PORT") or 3306)
    user = os.environ.get("OZON_MYSQL_USER") or "root"
    pw = os.environ.get("OZON_MYSQL_PASSWORD") or ""
    db = os.environ.get("OZON_MYSQL_DB") or "ozon"
    return f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4"


def engine_for(sqlite_path: str | None) -> Engine:
    """优先 env MySQL;否则 SQLite 文件。"""
    murl = mysql_url_from_env()
    if murl:
        return build_engine(murl)
    if not sqlite_path:
        raise ValueError("engine_for: 无 MySQL env 且未给 sqlite_path")
    return build_engine(_sqlite_url(str(sqlite_path)))
