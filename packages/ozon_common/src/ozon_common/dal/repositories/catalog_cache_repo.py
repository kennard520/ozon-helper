"""CatalogCacheRepo — catalog/属性值 5 张缓存表的 SQLAlchemy Core 访问层。

等价替换 apps/webui/src/webui/store.py 中的方法:
  - save_catalog_leaves / load_catalog_leaves
  - save_catalog_tree  / load_catalog_tree
  - save_category_attrs / load_category_attrs
  - save_attr_values   / load_attr_values
  - save_attribute_values / find_attribute_values

upsert 统一用 delete+insert 等价实现（同 SettingsRepo），对 SQLite/MySQL 均适用。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import (
    attribute_values_cache,
    catalog_cache,
    catalog_tree_cache,
    category_attr_cache,
    category_attr_values_cache,
)
from ozon_common.jsonio import dumps_json, loads_json, utc_now_iso


def _parse_iso(value: Any) -> datetime | None:
    """解析 ISO 时间字符串,对齐 store.py::_parse_iso 语义。"""
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class CatalogCacheRepo(BaseRepo):
    # ------------------------------------------------------------------ #
    # catalog_cache                                                         #
    # ------------------------------------------------------------------ #

    def save_catalog_leaves(self, language: str, leaves: list[dict[str, Any]]) -> None:
        """保存类目叶节点列表（upsert by language）。"""
        lang = str(language)
        self.s.execute(
            delete(catalog_cache).where(catalog_cache.c.language == lang)
        )
        self.s.execute(
            insert(catalog_cache).values(
                language=lang,
                leaves_json=dumps_json(leaves),
                fetched_at=utc_now_iso(),
            )
        )

    def load_catalog_leaves(self, language: str) -> list[dict[str, Any]] | None:
        """读取类目叶节点列表，无缓存返回 None。"""
        row = self.s.execute(
            select(catalog_cache.c.leaves_json).where(
                catalog_cache.c.language == str(language)
            )
        ).first()
        return loads_json(row.leaves_json, None) if row else None

    # ------------------------------------------------------------------ #
    # catalog_tree_cache                                                    #
    # ------------------------------------------------------------------ #

    def save_catalog_tree(self, language: str, tree: Any) -> None:
        """保存类目树（upsert by language）。"""
        lang = str(language)
        self.s.execute(
            delete(catalog_tree_cache).where(catalog_tree_cache.c.language == lang)
        )
        self.s.execute(
            insert(catalog_tree_cache).values(
                language=lang,
                tree_json=dumps_json(tree),
                fetched_at=utc_now_iso(),
            )
        )

    def load_catalog_tree(self, language: str) -> Any | None:
        """读取类目树，无缓存返回 None。"""
        row = self.s.execute(
            select(catalog_tree_cache.c.tree_json).where(
                catalog_tree_cache.c.language == str(language)
            )
        ).first()
        return loads_json(row.tree_json, None) if row else None

    # ------------------------------------------------------------------ #
    # category_attr_cache                                                   #
    # ------------------------------------------------------------------ #

    def save_category_attrs(
        self, cat: int, type_id: int, attrs: list[dict[str, Any]], language: str = "ZH_HANS"
    ) -> None:
        """保存类目属性（upsert by cat/type_id/language）。"""
        lang = str(language or "ZH_HANS")
        self.s.execute(
            delete(category_attr_cache).where(
                category_attr_cache.c.description_category_id == int(cat),
                category_attr_cache.c.type_id == int(type_id),
                category_attr_cache.c.language == lang,
            )
        )
        self.s.execute(
            insert(category_attr_cache).values(
                description_category_id=int(cat),
                type_id=int(type_id),
                language=lang,
                attrs_json=dumps_json(attrs),
                fetched_at=utc_now_iso(),
            )
        )

    def load_category_attrs(
        self, cat: int, type_id: int, language: str = "ZH_HANS", *, max_age_days: int = 30
    ) -> list[dict[str, Any]] | None:
        """读取类目属性，过期/空/无缓存返回 None（对齐 store.py TTL 语义）。"""
        lang = str(language or "ZH_HANS")
        row = self.s.execute(
            select(
                category_attr_cache.c.attrs_json,
                category_attr_cache.c.fetched_at,
            ).where(
                category_attr_cache.c.description_category_id == int(cat),
                category_attr_cache.c.type_id == int(type_id),
                category_attr_cache.c.language == lang,
            )
        ).first()
        if not row:
            return None
        # TTL：超过 max_age_days 视为过期，返回 None 触发重新拉取
        fetched = _parse_iso(row.fetched_at)
        if fetched is not None:
            age = datetime.now(timezone.utc) - fetched
            if age > timedelta(days=max_age_days):
                return None
        attrs = loads_json(row.attrs_json, None)
        # 空列表不算有效缓存
        if not attrs:
            return None
        return attrs

    # ------------------------------------------------------------------ #
    # category_attr_values_cache                                            #
    # ------------------------------------------------------------------ #

    def save_attr_values(
        self,
        cat: int,
        type_id: int,
        attr_id: int,
        values: list[dict[str, Any]],
        oversized: bool,
        language: str = "RU",
    ) -> None:
        """保存属性可选值列表（upsert by cat/type_id/attr_id/language）。"""
        lang = str(language or "RU")
        self.s.execute(
            delete(category_attr_values_cache).where(
                category_attr_values_cache.c.description_category_id == int(cat),
                category_attr_values_cache.c.type_id == int(type_id),
                category_attr_values_cache.c.attribute_id == int(attr_id),
                category_attr_values_cache.c.language == lang,
            )
        )
        self.s.execute(
            insert(category_attr_values_cache).values(
                description_category_id=int(cat),
                type_id=int(type_id),
                attribute_id=int(attr_id),
                language=lang,
                values_json=dumps_json(values),
                oversized=1 if oversized else 0,
                fetched_at=utc_now_iso(),
            )
        )

    def load_attr_values(
        self, cat: int, type_id: int, attr_id: int, language: str = "RU"
    ) -> tuple[list[dict[str, Any]], bool] | None:
        """读取属性可选值，返回 (values, oversized) 或 None。"""
        lang = str(language or "RU")
        row = self.s.execute(
            select(
                category_attr_values_cache.c.values_json,
                category_attr_values_cache.c.oversized,
            ).where(
                category_attr_values_cache.c.description_category_id == int(cat),
                category_attr_values_cache.c.type_id == int(type_id),
                category_attr_values_cache.c.attribute_id == int(attr_id),
                category_attr_values_cache.c.language == lang,
            )
        ).first()
        if not row:
            return None
        vals = loads_json(row.values_json, None)
        if vals is None:
            return None
        return (vals, bool(row.oversized))

    # ------------------------------------------------------------------ #
    # attribute_values_cache                                                #
    # ------------------------------------------------------------------ #

    def save_attribute_values(
        self,
        cat: int,
        type_id: int,
        attr: int,
        values: list[dict[str, Any]],
        language: str = "ZH_HANS",
    ) -> int:
        """按条目 upsert attribute_values_cache，返回写入条目数（等价 store.py 逐条 ON CONFLICT）。"""
        now = utc_now_iso()
        lang = str(language or "ZH_HANS")
        n = 0
        for v in values or []:
            vid = v.get("id") or v.get("dictionary_value_id")
            if not vid:
                continue
            # delete+insert 等价 ON CONFLICT DO UPDATE（主键: cat/type/attr/lang/dict_val_id）
            self.s.execute(
                delete(attribute_values_cache).where(
                    attribute_values_cache.c.description_category_id == int(cat),
                    attribute_values_cache.c.type_id == int(type_id),
                    attribute_values_cache.c.attribute_id == int(attr),
                    attribute_values_cache.c.language == lang,
                    attribute_values_cache.c.dictionary_value_id == int(vid),
                )
            )
            self.s.execute(
                insert(attribute_values_cache).values(
                    description_category_id=int(cat),
                    type_id=int(type_id),
                    attribute_id=int(attr),
                    language=lang,
                    dictionary_value_id=int(vid),
                    value=str(v.get("value") or ""),
                    info=str(v.get("info") or ""),
                    fetched_at=now,
                )
            )
            n += 1
        return n

    def find_attribute_values(
        self,
        cat: int,
        type_id: int,
        attr: int,
        query: str,
        language: str = "ZH_HANS",
        *,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """模糊搜索属性值（LIKE %query%，不区分大小写），返回 [{"id":..,"value":..,"info":..}]。

        SQLite 原生 LIKE 对 ASCII 已大小写不敏感；MySQL 默认 ci 排序也不敏感——无需额外处理。
        """
        lang = str(language or "ZH_HANS")
        rows = self.s.execute(
            select(
                attribute_values_cache.c.dictionary_value_id.label("id"),
                attribute_values_cache.c.value,
                attribute_values_cache.c.info,
            ).where(
                attribute_values_cache.c.description_category_id == int(cat),
                attribute_values_cache.c.type_id == int(type_id),
                attribute_values_cache.c.attribute_id == int(attr),
                attribute_values_cache.c.language == lang,
                attribute_values_cache.c.value.ilike(f"%{query}%"),
            ).limit(int(limit))
        ).all()
        return [dict(r._mapping) for r in rows]
