# -*- coding: utf-8 -*-
"""数据库后端选择层：默认 SQLite；设了 OZON_MYSQL_HOST 则走 MySQL。

MySQL 走一个**薄适配层**，让 store.py 现有的 sqlite 风格代码（`conn.execute(sql, params)`、
`?` 占位符、`sqlite3.Row` 的按名/按位访问、`ON CONFLICT ... DO UPDATE`）几乎原样可用：
适配层在 execute 时把 SQL 方言翻成 MySQL，并把返回行包成兼容 Row。

只有部署到服务器(容器里设了 OZON_MYSQL_* 环境变量)才启用 MySQL；本地开发仍是 SQLite，
store.py 的 SQLite 建表/迁移代码完全不变。
"""
from __future__ import annotations

import os
import re
from typing import Any


def mysql_enabled() -> bool:
    return bool(os.environ.get("OZON_MYSQL_HOST"))


def mysql_config() -> dict[str, Any]:
    return {
        "host": os.environ["OZON_MYSQL_HOST"],
        "port": int(os.environ.get("OZON_MYSQL_PORT") or 3306),
        "user": os.environ.get("OZON_MYSQL_USER") or "root",
        "password": os.environ.get("OZON_MYSQL_PASSWORD") or "",
        "database": os.environ.get("OZON_MYSQL_DB") or "ozon",
    }


# ---------------- SQL 方言翻译（SQLite -> MySQL） ----------------
_RE_COLLATE = re.compile(r"\bCOLLATE\s+NOCASE\b", re.IGNORECASE)
_RE_INS_REPLACE = re.compile(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", re.IGNORECASE)
_RE_INS_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.IGNORECASE)
_RE_UPSERT = re.compile(r"\bON\s+CONFLICT\s*\([^)]*\)\s*DO\s+UPDATE\s+SET\b", re.IGNORECASE)
_RE_EXCLUDED = re.compile(r"\bexcluded\.([A-Za-z_][A-Za-z0-9_]*)")


def translate(sql: str) -> str:
    s = sql
    s = _RE_COLLATE.sub("", s)                       # MySQL utf8mb4 默认大小写不敏感，去掉 COLLATE NOCASE
    s = _RE_INS_REPLACE.sub("REPLACE INTO", s)
    s = _RE_INS_IGNORE.sub("INSERT IGNORE INTO", s)
    s = _RE_UPSERT.sub("ON DUPLICATE KEY UPDATE", s)  # ON CONFLICT(...) DO UPDATE SET -> ON DUPLICATE KEY UPDATE
    s = _RE_EXCLUDED.sub(r"VALUES(\1)", s)            # excluded.col -> VALUES(col)
    # json_extract(value,'$') -> 取裸标量（与 SQLite 语义一致）
    s = s.replace("json_extract(value,'$')", "JSON_UNQUOTE(JSON_EXTRACT(`value`,'$'))")
    # `key` 是 MySQL 保留字（settings 表列名），裸词边界处加反引号；value 非保留字不动
    s = re.sub(r"(?<![\w.`])key(?![\w`])", "`key`", s)
    s = s.replace("?", "%s")                          # 占位符
    return s


class Row:
    """兼容 sqlite3.Row：支持 row[i] / row['col'] / row.keys() / dict(row) / 'col' in row。"""
    __slots__ = ("_keys", "_vals", "_map")

    def __init__(self, keys: list[str], vals: tuple):
        self._keys = keys
        self._vals = vals
        self._map = dict(zip(keys, vals))

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._map[k]

    def keys(self):
        return list(self._keys)

    def __contains__(self, k):
        return k in self._map

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._vals)


class _Cursor:
    """包一层 pymysql 游标，fetch 出来的行包成 Row。"""
    def __init__(self, cur):
        self._cur = cur
        self._cols = [d[0] for d in cur.description] if cur.description else []

    def fetchone(self):
        r = self._cur.fetchone()
        return Row(self._cols, r) if r is not None else None

    def fetchall(self):
        return [Row(self._cols, r) for r in self._cur.fetchall()]

    def __iter__(self):
        for r in self._cur:
            yield Row(self._cols, r)

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return self._cur.lastrowid


class MySQLConn:
    """暴露 sqlite3.Connection 风格的 .execute()/.commit()/.close()。线程安全由 store 的 RLock 保证。"""
    def __init__(self, cfg: dict[str, Any]):
        self._cfg = cfg
        self._conn = self._connect()

    def _connect(self):
        import pymysql
        from pymysql.constants import CLIENT
        c = pymysql.connect(
            charset="utf8mb4", autocommit=False, connect_timeout=10,
            # FOUND_ROWS：让 UPDATE 的 rowcount = 命中行数(而非实际改动行数)，
            # 与 sqlite 一致——deduct() 的原子扣款判断依赖它。
            client_flag=CLIENT.FOUND_ROWS,
            **self._cfg,
        )
        # 单连接 + 上层串行化；用 READ COMMITTED 避免长读快照导致看不到自己提交后的新数据
        with c.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        c.commit()
        return c

    def _ensure(self):
        try:
            self._conn.ping(reconnect=True)
        except Exception:
            self._conn = self._connect()

    def execute(self, sql: str, params=None):
        self._ensure()
        cur = self._conn.cursor()
        cur.execute(translate(sql), tuple(params) if params else None)
        return _Cursor(cur)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def make_mysql_conn() -> MySQLConn:
    return MySQLConn(mysql_config())


# ---------------- MySQL 建表（最终形态，跳过 SQLite 的 PRAGMA/迁移） ----------------
MYSQL_DDL = [
    """
    CREATE TABLE IF NOT EXISTS settings (
        user_id INT NOT NULL DEFAULT 0,
        `key` VARCHAR(191) NOT NULL,
        `value` LONGTEXT NOT NULL,
        PRIMARY KEY (user_id, `key`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(191) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL DEFAULT 'user',
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        created_at VARCHAR(40) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        user_id INT PRIMARY KEY,
        balance DOUBLE NOT NULL DEFAULT 0,
        total_recharge DOUBLE NOT NULL DEFAULT 0,
        total_consume DOUBLE NOT NULL DEFAULT 0,
        updated_at VARCHAR(40)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS account_txns (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        txn_type VARCHAR(32) NOT NULL,
        amount DOUBLE NOT NULL,
        balance_after DOUBLE,
        biz_no VARCHAR(128),
        remark VARCHAR(512),
        created_at VARCHAR(40) NOT NULL,
        KEY idx_txn_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS drafts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL DEFAULT 1,
        store_client_id VARCHAR(64) NOT NULL DEFAULT '',
        source_platform VARCHAR(32) NOT NULL DEFAULT '1688',
        source_url VARCHAR(1024) NOT NULL,
        source_offer_id VARCHAR(191),
        source_title TEXT,
        purchase_url VARCHAR(1024),
        purchase_note TEXT,
        ozon_title TEXT,
        description LONGTEXT,
        category_id VARCHAR(64),
        type_id VARCHAR(64) DEFAULT '',
        brand_id BIGINT,
        brand_name VARCHAR(255) DEFAULT '',
        price VARCHAR(64),
        old_price VARCHAR(64),
        stock INT,
        weight_g INT,
        length_mm INT,
        width_mm INT,
        height_mm INT,
        cost_cny DOUBLE,
        video_url TEXT,
        local_images_json LONGTEXT,
        source VARCHAR(64) DEFAULT '',
        ozon_product_id BIGINT,
        offer_id VARCHAR(191) DEFAULT '',
        supplier VARCHAR(255) DEFAULT '',
        warehouse_id BIGINT,
        source_raw_json LONGTEXT,
        ai_proposal_json LONGTEXT,
        pricing_json LONGTEXT,
        images_json LONGTEXT,
        attributes_json LONGTEXT,
        status VARCHAR(32),
        validation_errors_json LONGTEXT,
        publish_response_json LONGTEXT,
        created_at VARCHAR(40),
        updated_at VARCHAR(40),
        UNIQUE KEY uq_draft (user_id, store_client_id, source_url(255))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS commission_map (
        description_category_id BIGINT,
        type_id BIGINT,
        parent_en TEXT,
        sub_en TEXT,
        rfbs_json LONGTEXT,
        updated_at VARCHAR(40),
        PRIMARY KEY (description_category_id, type_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_cache (
        language VARCHAR(32) PRIMARY KEY,
        leaves_json LONGTEXT NOT NULL,
        fetched_at VARCHAR(40) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS catalog_tree_cache (
        language VARCHAR(32) PRIMARY KEY,
        tree_json LONGTEXT NOT NULL,
        fetched_at VARCHAR(40) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS attribute_values_cache (
        description_category_id BIGINT NOT NULL,
        type_id BIGINT NOT NULL,
        attribute_id BIGINT NOT NULL,
        language VARCHAR(32) NOT NULL DEFAULT 'ZH_HANS',
        dictionary_value_id BIGINT NOT NULL,
        value VARCHAR(1024),
        info TEXT,
        fetched_at VARCHAR(40),
        PRIMARY KEY (description_category_id, type_id, attribute_id, language, dictionary_value_id),
        KEY idx_av_cache (description_category_id, type_id, attribute_id, language, value(100))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS category_attr_cache (
        description_category_id BIGINT NOT NULL,
        type_id BIGINT NOT NULL,
        language VARCHAR(32) NOT NULL DEFAULT 'ZH_HANS',
        attrs_json LONGTEXT NOT NULL,
        fetched_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (description_category_id, type_id, language)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS warehouses (
        warehouse_id BIGINT PRIMARY KEY,
        name VARCHAR(255) NOT NULL DEFAULT '',
        is_rfbs INT NOT NULL DEFAULT 0,
        status VARCHAR(64) NOT NULL DEFAULT '',
        is_default INT NOT NULL DEFAULT 0,
        fetched_at VARCHAR(40),
        store_client_id VARCHAR(64) NOT NULL DEFAULT ''
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS postings (
        posting_number VARCHAR(128) PRIMARY KEY,
        ozon_order_id VARCHAR(128),
        status VARCHAR(64),
        ship_by VARCHAR(64),
        products_json LONGTEXT,
        warehouse_id BIGINT,
        raw_json LONGTEXT,
        synced_at VARCHAR(40),
        store_client_id VARCHAR(64) NOT NULL DEFAULT ''
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS procurement (
        id INT AUTO_INCREMENT PRIMARY KEY,
        posting_number VARCHAR(128) NOT NULL,
        offer_id VARCHAR(191) NOT NULL,
        qty INT NOT NULL DEFAULT 1,
        purchase_state VARCHAR(32) NOT NULL DEFAULT '待采购',
        supplier VARCHAR(255) NOT NULL DEFAULT '',
        purchase_url VARCHAR(1024) NOT NULL DEFAULT '',
        cost_cny DOUBLE,
        note TEXT,
        updated_at VARCHAR(40),
        store_client_id VARCHAR(64) NOT NULL DEFAULT '',
        UNIQUE KEY uq_proc (posting_number, offer_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS offer_snapshots (
        id INT AUTO_INCREMENT PRIMARY KEY,
        product_id VARCHAR(191) NOT NULL,
        sku VARCHAR(191),
        captured_at VARCHAR(40) NOT NULL,
        follow_count INT,
        price_min DOUBLE,
        price_max DOUBLE,
        sellers_json LONGTEXT,
        store_client_id VARCHAR(64) NOT NULL DEFAULT '',
        KEY idx_offer_snap_pid (product_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def init_mysql(conn: MySQLConn) -> None:
    for ddl in MYSQL_DDL:
        conn.execute(ddl)
    conn.commit()


def load_raw_settings() -> dict[str, str]:
    """给 analytics_report 用：返回 {key: value_raw}（沿用旧行为，跨用户后写者覆盖）。"""
    conn = make_mysql_conn()
    try:
        rows = conn.execute("SELECT `key`, `value` FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()
