import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.settings_repo import SettingsRepo
from ozon_common.dal.schema import metadata


def _bind(tmp):
    """构建 SQLite engine 并初始化 schema,返回 engine 供 dispose。"""
    eng = build_engine(f"sqlite:///{Path(tmp) / 's.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def test_save_and_get_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                SettingsRepo().save_settings({"oss_bucket": "b1", "ai_text": {"engine": "x"}}, user_id=1)
            with S.session_scope():
                got = SettingsRepo().get_settings(1)
                assert got["oss_bucket"] == "b1"
                assert got["ai_text"] == {"engine": "x"}
        finally:
            eng.dispose()


def test_user_overrides_global():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                SettingsRepo().save_settings({"k": "global"}, user_id=0)
                SettingsRepo().save_settings({"k": "user1"}, user_id=1)
            with S.session_scope():
                assert SettingsRepo().get_settings(1)["k"] == "user1"
        finally:
            eng.dispose()


def test_resave_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                SettingsRepo().save_settings({"k": "v1"}, user_id=1)
                SettingsRepo().save_settings({"k": "v2"}, user_id=1)
            with S.session_scope():
                assert SettingsRepo().get_settings(1)["k"] == "v2"
        finally:
            eng.dispose()
