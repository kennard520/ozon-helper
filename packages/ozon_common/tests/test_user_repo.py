"""UserRepo 单元测试（SQLite 临时库）。

覆盖所有 9 个方法：
  create_user / get_user_by_username / get_user_by_id / count_users /
  list_users / set_max_stores / set_status / set_password_hash / delete_user

以及 username UNIQUE 冲突行为（IntegrityError 上抛）。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.user_repo import UserRepo
from ozon_common.dal.schema import metadata


def _bind(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'u.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# --------------------------------------------------------------------------- #
# 基本 CRUD                                                                    #
# --------------------------------------------------------------------------- #

def test_create_and_get_by_username():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("alice", "hash123", role="admin", max_stores=3)
            assert u["username"] == "alice"
            assert u["role"] == "admin"
            assert u["status"] == "active"
            assert u["max_stores"] == 3
            assert u["password_hash"] == "hash123"
            assert u["id"] is not None
            assert u["created_at"]

            with S.session_scope():
                found = UserRepo().get_user_by_username("alice")
            assert found is not None
            assert found["id"] == u["id"]
            assert found["password_hash"] == "hash123"
        finally:
            eng.dispose()


def test_get_by_id():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("bob", "pw")
            with S.session_scope():
                found = UserRepo().get_user_by_id(u["id"])
            assert found is not None
            assert found["username"] == "bob"
        finally:
            eng.dispose()


def test_get_by_id_missing_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                assert UserRepo().get_user_by_id(9999) is None
        finally:
            eng.dispose()


def test_get_by_username_missing_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                assert UserRepo().get_user_by_username("no-such-user") is None
        finally:
            eng.dispose()


# --------------------------------------------------------------------------- #
# count_users                                                                  #
# --------------------------------------------------------------------------- #

def test_count_users():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                assert UserRepo().count_users() == 0
                UserRepo().create_user("u1", "h1")
                UserRepo().create_user("u2", "h2")
            with S.session_scope():
                assert UserRepo().count_users() == 2
        finally:
            eng.dispose()


# --------------------------------------------------------------------------- #
# list_users                                                                   #
# --------------------------------------------------------------------------- #

def test_list_users():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                UserRepo().create_user("alpha", "h", role="admin")
                UserRepo().create_user("beta", "h")
            with S.session_scope():
                rows = UserRepo().list_users()
            assert len(rows) == 2
            # 顺序 ORDER BY id：alpha 先
            assert rows[0]["username"] == "alpha"
            assert rows[1]["username"] == "beta"
            # 不包含 password_hash
            for r in rows:
                assert "password_hash" not in r
            # 包含必要字段
            for r in rows:
                for f in ("id", "username", "role", "status", "max_stores", "created_at"):
                    assert f in r, f"缺字段 {f}"
        finally:
            eng.dispose()


# --------------------------------------------------------------------------- #
# set_max_stores / set_status / set_password_hash                              #
# --------------------------------------------------------------------------- #

def test_set_max_stores():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("c1", "h")
            with S.session_scope():
                UserRepo().set_max_stores(u["id"], 5)
            with S.session_scope():
                updated = UserRepo().get_user_by_id(u["id"])
            assert updated["max_stores"] == 5
        finally:
            eng.dispose()


def test_set_status():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("c2", "h")
            with S.session_scope():
                UserRepo().set_status(u["id"], "disabled")
            with S.session_scope():
                updated = UserRepo().get_user_by_id(u["id"])
            assert updated["status"] == "disabled"
        finally:
            eng.dispose()


def test_set_password_hash():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("c3", "old_hash")
            with S.session_scope():
                UserRepo().set_password_hash(u["id"], "new_hash")
            with S.session_scope():
                updated = UserRepo().get_user_by_id(u["id"])
            assert updated["password_hash"] == "new_hash"
        finally:
            eng.dispose()


# --------------------------------------------------------------------------- #
# delete_user                                                                  #
# --------------------------------------------------------------------------- #

def test_delete_user():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("d1", "h")
            with S.session_scope():
                UserRepo().delete_user(u["id"])
            with S.session_scope():
                assert UserRepo().get_user_by_id(u["id"]) is None
                assert UserRepo().get_user_by_username("d1") is None
        finally:
            eng.dispose()


def test_delete_user_reduces_count():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u1 = UserRepo().create_user("x1", "h")
                UserRepo().create_user("x2", "h")
            with S.session_scope():
                assert UserRepo().count_users() == 2
            with S.session_scope():
                UserRepo().delete_user(u1["id"])
            with S.session_scope():
                assert UserRepo().count_users() == 1
        finally:
            eng.dispose()


# --------------------------------------------------------------------------- #
# UNIQUE 冲突                                                                   #
# --------------------------------------------------------------------------- #

def test_duplicate_username_raises():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                UserRepo().create_user("dup", "h1")
            with pytest.raises(IntegrityError):
                with S.session_scope():
                    UserRepo().create_user("dup", "h2")
        finally:
            eng.dispose()


# --------------------------------------------------------------------------- #
# 默认字段值验证                                                                 #
# --------------------------------------------------------------------------- #

def test_default_role_and_status():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                u = UserRepo().create_user("def_user", "h")
            assert u["role"] == "user"
            assert u["status"] == "active"
            assert u["max_stores"] == 1
        finally:
            eng.dispose()
