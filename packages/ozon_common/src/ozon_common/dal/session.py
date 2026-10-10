"""请求级 scoped-session:ContextVar 绑定 + session_scope 上下文管理器。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_current_session: ContextVar["Session | None"] = ContextVar("_current_session", default=None)
_factory: "sessionmaker | None" = None


def bind_engine(engine: Engine) -> None:
    """进程启动时调一次,绑定全局 sessionmaker。"""
    global _factory
    _factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)


def unbind_engine() -> None:
    """Clear the process-global sessionmaker after Store.close()."""
    global _factory
    _factory = None


@contextmanager
def session_scope():
    """开一个 Session、绑到 ContextVar,正常提交/异常回滚/最终关闭。"""
    if _factory is None:
        raise RuntimeError("session 未初始化:先调 bind_engine(engine)")
    existing = _current_session.get()
    if existing is not None:
        yield existing
        return
    sess = _factory()
    token = _current_session.set(sess)
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
        _current_session.reset(token)


def current_session() -> Session:
    s = _current_session.get()
    if s is None:
        raise RuntimeError("current_session(): 不在 session_scope 内")
    return s
