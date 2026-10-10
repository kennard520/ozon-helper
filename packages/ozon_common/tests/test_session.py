import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 't.db'}")
    S.bind_engine(eng)
    return eng


def test_current_session_outside_scope_raises():
    with pytest.raises(RuntimeError):
        S.current_session()


def test_session_scope_commits_and_binds():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope() as sess:
                assert S.current_session() is sess
                sess.execute(text("CREATE TABLE t (id INTEGER)"))
                sess.execute(text("INSERT INTO t VALUES (1)"))
            with pytest.raises(RuntimeError):
                S.current_session()
            with S.session_scope() as sess:
                n = sess.execute(text("SELECT COUNT(*) FROM t")).scalar()
                assert n == 1
        finally:
            eng.dispose()


def test_session_scope_rollback_on_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope() as sess:
                sess.execute(text("CREATE TABLE t (id INTEGER)"))
            try:
                with S.session_scope() as sess:
                    sess.execute(text("INSERT INTO t VALUES (1)"))
                    raise ValueError("boom")
            except ValueError:
                pass
            with S.session_scope() as sess:
                n = sess.execute(text("SELECT COUNT(*) FROM t")).scalar()
                assert n == 0
        finally:
            eng.dispose()
