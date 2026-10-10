"""护栏:dal.schema 的 metadata.create_all 必须与老 Store.init() 建出的 schema 一致(SQLite)。"""
import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from ozon_common.dal.schema import metadata


def _snapshot(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out = {}
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in sorted(tables):
        cols = {c["name"]: bool(c["notnull"]) for c in con.execute(f"PRAGMA table_info({t})")}
        out[t] = cols
    con.close()
    return out


def test_metadata_matches_legacy_init():
    with tempfile.TemporaryDirectory() as tmp:
        import webui.store as store_mod
        legacy = str(Path(tmp) / "legacy.db")
        store_mod.DEFAULT_DB = Path(legacy)
        s = store_mod.Store(Path(legacy)); s.close()

        new = str(Path(tmp) / "new.db")
        eng = create_engine(f"sqlite:///{new}", future=True)
        metadata.create_all(eng); eng.dispose()

        L, N = _snapshot(legacy), _snapshot(new)
        assert set(L) == set(N), f"表差异 仅老={set(L)-set(N)} 仅新={set(N)-set(L)}"
        for t in L:
            assert set(L[t]) == set(N[t]), f"{t} 列差异 仅老={set(L[t])-set(N[t])} 仅新={set(N[t])-set(L[t])}"
