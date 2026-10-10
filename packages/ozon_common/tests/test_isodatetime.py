"""ISODateTime 往返单测:验证对外仍是对齐 utc_now_iso 的 ISO 字符串(parity 核心)。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, Table, create_engine, insert, select

from ozon_common.dal.types import ISODateTime
from ozon_common.jsonio import utc_now_iso


def _roundtrip(written):
    """建临时 SQLite 表写入 written,读回唯一一行的 ts。"""
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "t.db"
    eng = create_engine(f"sqlite:///{db_path}")
    md = MetaData()
    t = Table("t", md, Column("ts", ISODateTime))
    try:
        md.create_all(eng)
        with eng.begin() as conn:
            conn.execute(insert(t).values(ts=written))
        with eng.connect() as conn:
            return conn.execute(select(t.c.ts)).scalar_one()
    finally:
        eng.dispose()


def test_roundtrip_preserves_iso_string_and_microseconds():
    written = utc_now_iso()
    read = _roundtrip(written)
    # ① 仍是 str
    assert isinstance(read, str)
    # ② 可被 fromisoformat 解析
    parsed = datetime.fromisoformat(read)
    # ③ 解析后与写入值 datetime 相等到微秒
    assert parsed == datetime.fromisoformat(written)
    # ④ 末尾带 +00:00
    assert read.endswith("+00:00")


def test_roundtrip_explicit_microseconds():
    # 显式带 6 位微秒,确认不被截断
    written = "2026-06-27T12:34:56.789012+00:00"
    read = _roundtrip(written)
    assert isinstance(read, str)
    assert datetime.fromisoformat(read) == datetime.fromisoformat(written)
    assert read.endswith("+00:00")
    assert read == "2026-06-27T12:34:56.789012+00:00"


def test_none_roundtrips_to_none():
    assert _roundtrip(None) is None


def test_bind_accepts_datetime_with_tz():
    written = datetime(2026, 6, 27, 12, 0, 0, 123456, tzinfo=timezone.utc)
    read = _roundtrip(written)
    assert datetime.fromisoformat(read) == written
    assert read.endswith("+00:00")
