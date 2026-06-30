"""ISODateTime:库里存 DateTime(MySQL DATETIME(6)),Python 层收发 ISO 字符串(对齐 utc_now_iso)。

对外行为(parity):仓储/应用代码读写的仍是 `2026-06-27T12:34:56.789012+00:00` 这种
带时区的 ISO 字符串,与 `ozon_common.jsonio.utc_now_iso()` 产出对齐;
底层落到 DB 用原生 DATETIME(MySQL 取 fsp=6 保微秒,SQLite 用普通 DateTime 本就保微秒)。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.types import TypeDecorator


class ISODateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        # MySQL 默认 DATETIME 秒级会丢微秒;显式取 fsp=6 保微秒。
        if dialect.name == "mysql":
            return dialect.type_descriptor(MySQLDateTime(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            s = str(value).strip()
            if s == "":
                # 旧代码常用空串占位时间列;DATETIME 不接受空串,语义上等价 NULL。
                return None
            dt = datetime.fromisoformat(s)
        # 统一转 UTC 并去掉 tzinfo(DB 列是 naive DATETIME,语义上即 UTC)。
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        # DB 取出为 naive,语义上是 UTC,补 +00:00 还原成与 utc_now_iso 对齐的 ISO 字符串。
        return value.replace(tzinfo=timezone.utc).isoformat()
