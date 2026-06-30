"""test_catalog_cache_repo — CatalogCacheRepo roundtrip 单测。

覆盖:
- save/load 命中
- 不同 language 隔离
- re-save 覆盖（upsert 语义）
- TTL 过期返回 None (load_category_attrs)
- find_attribute_values 按条件命中
"""
import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.catalog_cache_repo import CatalogCacheRepo
from ozon_common.dal.schema import metadata


def _bind(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'cat.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# ------------------------------------------------------------------ #
# catalog_cache                                                         #
# ------------------------------------------------------------------ #

def test_catalog_leaves_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            leaves = [{"id": 1, "name": "cat1"}, {"id": 2, "name": "cat2"}]
            with S.session_scope():
                CatalogCacheRepo().save_catalog_leaves("RU", leaves)
            with S.session_scope():
                got = CatalogCacheRepo().load_catalog_leaves("RU")
            assert got == leaves
        finally:
            eng.dispose()


def test_catalog_leaves_missing_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                got = CatalogCacheRepo().load_catalog_leaves("ZH_HANS")
            assert got is None
        finally:
            eng.dispose()


def test_catalog_leaves_language_isolation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_catalog_leaves("RU", [{"id": 1}])
                CatalogCacheRepo().save_catalog_leaves("ZH_HANS", [{"id": 2}])
            with S.session_scope():
                assert CatalogCacheRepo().load_catalog_leaves("RU") == [{"id": 1}]
                assert CatalogCacheRepo().load_catalog_leaves("ZH_HANS") == [{"id": 2}]
        finally:
            eng.dispose()


def test_catalog_leaves_resave_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_catalog_leaves("RU", [{"id": 1}])
                CatalogCacheRepo().save_catalog_leaves("RU", [{"id": 99}])
            with S.session_scope():
                assert CatalogCacheRepo().load_catalog_leaves("RU") == [{"id": 99}]
        finally:
            eng.dispose()


# ------------------------------------------------------------------ #
# catalog_tree_cache                                                    #
# ------------------------------------------------------------------ #

def test_catalog_tree_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            tree = {"root": [{"id": 1, "children": []}]}
            with S.session_scope():
                CatalogCacheRepo().save_catalog_tree("RU", tree)
            with S.session_scope():
                got = CatalogCacheRepo().load_catalog_tree("RU")
            assert got == tree
        finally:
            eng.dispose()


def test_catalog_tree_language_isolation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_catalog_tree("RU", {"a": 1})
                CatalogCacheRepo().save_catalog_tree("ZH_HANS", {"b": 2})
            with S.session_scope():
                assert CatalogCacheRepo().load_catalog_tree("RU") == {"a": 1}
                assert CatalogCacheRepo().load_catalog_tree("ZH_HANS") == {"b": 2}
        finally:
            eng.dispose()


def test_catalog_tree_resave_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_catalog_tree("RU", {"v": 1})
                CatalogCacheRepo().save_catalog_tree("RU", {"v": 2})
            with S.session_scope():
                assert CatalogCacheRepo().load_catalog_tree("RU") == {"v": 2}
        finally:
            eng.dispose()


# ------------------------------------------------------------------ #
# category_attr_cache                                                   #
# ------------------------------------------------------------------ #

def test_category_attrs_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            attrs = [{"id": 10, "name": "Color", "is_required": True}]
            with S.session_scope():
                CatalogCacheRepo().save_category_attrs(100, 1, attrs, "ZH_HANS")
            with S.session_scope():
                got = CatalogCacheRepo().load_category_attrs(100, 1, "ZH_HANS")
            assert got == attrs
        finally:
            eng.dispose()


def test_category_attrs_missing_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                got = CatalogCacheRepo().load_category_attrs(999, 1, "ZH_HANS")
            assert got is None
        finally:
            eng.dispose()


def test_category_attrs_language_isolation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_category_attrs(100, 1, [{"id": 1}], "ZH_HANS")
                CatalogCacheRepo().save_category_attrs(100, 1, [{"id": 2}], "RU")
            with S.session_scope():
                assert CatalogCacheRepo().load_category_attrs(100, 1, "ZH_HANS") == [{"id": 1}]
                assert CatalogCacheRepo().load_category_attrs(100, 1, "RU") == [{"id": 2}]
        finally:
            eng.dispose()


def test_category_attrs_resave_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_category_attrs(100, 1, [{"id": 1}])
                CatalogCacheRepo().save_category_attrs(100, 1, [{"id": 2}])
            with S.session_scope():
                assert CatalogCacheRepo().load_category_attrs(100, 1) == [{"id": 2}]
        finally:
            eng.dispose()


def test_category_attrs_empty_returns_none():
    """空列表不算有效缓存（对齐 store.py 语义）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_category_attrs(100, 1, [])
            with S.session_scope():
                got = CatalogCacheRepo().load_category_attrs(100, 1)
            assert got is None
        finally:
            eng.dispose()


def test_category_attrs_ttl_expired(monkeypatch):
    """TTL 过期后 load_category_attrs 返回 None。"""
    import ozon_common.dal.repositories.catalog_cache_repo as m

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_category_attrs(100, 1, [{"id": 1}])
            # 模拟当前时间比 fetched_at 超出 30 天
            from datetime import datetime, timedelta, timezone
            real_now = datetime.now(timezone.utc)
            future_now = real_now + timedelta(days=31)

            original_parse = m._parse_iso

            def fake_parse(v):
                dt = original_parse(v)
                return dt

            # monkeypatch datetime.now inside the module to simulate old timestamp
            class FakeDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return future_now

            monkeypatch.setattr(m, "datetime", FakeDatetime)

            with S.session_scope():
                got = CatalogCacheRepo().load_category_attrs(100, 1)
            assert got is None
        finally:
            eng.dispose()


# ------------------------------------------------------------------ #
# category_attr_values_cache                                            #
# ------------------------------------------------------------------ #

def test_attr_values_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            vals = [{"id": 1, "value": "Red"}, {"id": 2, "value": "Blue"}]
            with S.session_scope():
                CatalogCacheRepo().save_attr_values(100, 1, 10, vals, False, "RU")
            with S.session_scope():
                got = CatalogCacheRepo().load_attr_values(100, 1, 10, "RU")
            assert got is not None
            loaded_vals, oversized = got
            assert loaded_vals == vals
            assert oversized is False
        finally:
            eng.dispose()


def test_attr_values_oversized_flag():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attr_values(100, 1, 10, [{"id": 1, "value": "x"}], True, "RU")
            with S.session_scope():
                got = CatalogCacheRepo().load_attr_values(100, 1, 10, "RU")
            assert got is not None
            _, oversized = got
            assert oversized is True
        finally:
            eng.dispose()


def test_attr_values_missing_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                got = CatalogCacheRepo().load_attr_values(999, 1, 10)
            assert got is None
        finally:
            eng.dispose()


def test_attr_values_language_isolation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attr_values(100, 1, 10, [{"id": 1, "value": "Red"}], False, "RU")
                CatalogCacheRepo().save_attr_values(100, 1, 10, [{"id": 1, "value": "红"}], False, "ZH_HANS")
            with S.session_scope():
                ru_res = CatalogCacheRepo().load_attr_values(100, 1, 10, "RU")
                zh_res = CatalogCacheRepo().load_attr_values(100, 1, 10, "ZH_HANS")
            assert ru_res is not None and ru_res[0][0]["value"] == "Red"
            assert zh_res is not None and zh_res[0][0]["value"] == "红"
        finally:
            eng.dispose()


def test_attr_values_resave_overwrites():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attr_values(100, 1, 10, [{"id": 1, "value": "old"}], False, "RU")
                CatalogCacheRepo().save_attr_values(100, 1, 10, [{"id": 1, "value": "new"}], True, "RU")
            with S.session_scope():
                got = CatalogCacheRepo().load_attr_values(100, 1, 10, "RU")
            assert got is not None
            vals, oversized = got
            assert vals[0]["value"] == "new"
            assert oversized is True
        finally:
            eng.dispose()


# ------------------------------------------------------------------ #
# attribute_values_cache                                                #
# ------------------------------------------------------------------ #

def test_save_attribute_values_roundtrip():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            values = [
                {"id": 101, "value": "Apple", "info": "品牌"},
                {"id": 102, "value": "Samsung", "info": "品牌"},
            ]
            with S.session_scope():
                n = CatalogCacheRepo().save_attribute_values(100, 1, 10, values, "ZH_HANS")
            assert n == 2
            with S.session_scope():
                found = CatalogCacheRepo().find_attribute_values(100, 1, 10, "Apple", "ZH_HANS")
            assert len(found) == 1
            assert found[0]["id"] == 101
            assert found[0]["value"] == "Apple"
        finally:
            eng.dispose()


def test_save_attribute_values_skips_no_id():
    """无 id/dictionary_value_id 的条目跳过。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            values = [
                {"value": "NoId", "info": ""},
                {"id": 50, "value": "HasId", "info": ""},
            ]
            with S.session_scope():
                n = CatalogCacheRepo().save_attribute_values(100, 1, 10, values)
            assert n == 1
        finally:
            eng.dispose()


def test_save_attribute_values_resave_overwrites():
    """同一 dictionary_value_id 重存后读到新值。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attribute_values(100, 1, 10, [{"id": 1, "value": "v1", "info": ""}])
                CatalogCacheRepo().save_attribute_values(100, 1, 10, [{"id": 1, "value": "v2", "info": ""}])
            with S.session_scope():
                found = CatalogCacheRepo().find_attribute_values(100, 1, 10, "v2")
            assert len(found) == 1
            assert found[0]["value"] == "v2"
        finally:
            eng.dispose()


def test_find_attribute_values_case_insensitive():
    """find 大小写不敏感（ilike）。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attribute_values(
                    100, 1, 10,
                    [{"id": 1, "value": "Apple iPhone", "info": ""}],
                    "ZH_HANS",
                )
            with S.session_scope():
                found = CatalogCacheRepo().find_attribute_values(100, 1, 10, "iphone", "ZH_HANS")
            assert len(found) == 1
        finally:
            eng.dispose()


def test_find_attribute_values_language_isolation():
    """find 在 language 维度隔离。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attribute_values(100, 1, 10, [{"id": 1, "value": "Apple", "info": ""}], "ZH_HANS")
                CatalogCacheRepo().save_attribute_values(100, 1, 10, [{"id": 2, "value": "Apple", "info": ""}], "RU")
            with S.session_scope():
                zh = CatalogCacheRepo().find_attribute_values(100, 1, 10, "Apple", "ZH_HANS")
                ru = CatalogCacheRepo().find_attribute_values(100, 1, 10, "Apple", "RU")
            assert len(zh) == 1 and zh[0]["id"] == 1
            assert len(ru) == 1 and ru[0]["id"] == 2
        finally:
            eng.dispose()


def test_find_attribute_values_limit():
    """limit 参数生效。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            values = [{"id": i, "value": f"Brand{i}", "info": ""} for i in range(1, 51)]
            with S.session_scope():
                CatalogCacheRepo().save_attribute_values(100, 1, 10, values)
            with S.session_scope():
                found = CatalogCacheRepo().find_attribute_values(100, 1, 10, "Brand", limit=5)
            assert len(found) == 5
        finally:
            eng.dispose()


def test_find_attribute_values_no_match_returns_empty():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                CatalogCacheRepo().save_attribute_values(100, 1, 10, [{"id": 1, "value": "Apple", "info": ""}])
            with S.session_scope():
                found = CatalogCacheRepo().find_attribute_values(100, 1, 10, "Samsung")
            assert found == []
        finally:
            eng.dispose()
