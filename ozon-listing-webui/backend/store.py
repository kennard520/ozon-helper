from __future__ import annotations

import os
import sqlite3
import threading
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend import db
from backend.drafts import dumps_json, loads_json, utc_now_iso, validate_draft

# 当前请求的用户 ID（多用户隔离）。HTTP 中间件按 JWT 设置；非请求上下文(测试/启动)默认 1(admin)。
# store 方法 user_id 传 None 时读这里——让 App 各方法无需逐个加 user_id 参数就自动按当前用户隔离。
current_user_id: ContextVar[int] = ContextVar("current_user_id", default=1)


def _uid(user_id: int | None) -> int:
    return int(current_user_id.get() if user_id is None else user_id)


# 默认落 ozon-listing-webui/data/products.db（data/ 不随 backend/ 下移，故用 parents[1]）；
# 可用 OZON_WEBUI_DB 环境变量改指（测试/多库时不污染主库）
DEFAULT_DB = Path(os.environ.get("OZON_WEBUI_DB") or (Path(__file__).resolve().parents[1] / "data" / "products.db"))

# 系统级全局设置（不归任何用户，存 user_id=0）：JWT 密钥 + 服务级共享 OSS 桶配置。
# 其余设置（Ozon 凭证/AI 配置/汇率/店铺等）按用户隔离。
GLOBAL_SETTING_KEYS = {
    "jwt_secret",
    "oss_endpoint", "oss_bucket", "oss_access_key_id", "oss_access_key_secret", "oss_public_base",
}


def _parse_iso(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, "", " "):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", " "):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        self.lock = threading.RLock()
        # 部署到服务器(容器设了 OZON_MYSQL_*) 走 MySQL；否则本地 SQLite（行为不变）。
        if db.mysql_enabled():
            self.path = None
            self._is_mysql = True
            self.conn = db.make_mysql_conn()
        else:
            # 调用时读模块级 DEFAULT_DB（而非定义时绑定默认参数），
            # 这样测试 `store.DEFAULT_DB = 临时库` 能真正生效、不污染主库。
            self.path = Path(path) if path is not None else Path(DEFAULT_DB)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._is_mysql = False
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        self.init()

    def close(self) -> None:
        self.conn.close()

    def init(self) -> None:
        if self._is_mysql:
            # MySQL：直接建最终形态表结构，跳过 SQLite 的 PRAGMA/RENAME 迁移
            db.init_mysql(self.conn)
            return
        with self.lock:
            # 多用户：settings 按 user_id 隔离（user_id=0 为系统级全局）
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    user_id INTEGER NOT NULL DEFAULT 0,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY(user_id, key)
                )
                """
            )
            self._migrate_settings_multiuser()
            # 多用户：用户表（裸 sqlite3，密码 PBKDF2 哈希存 password_hash）
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column("users", "max_stores", "INTEGER NOT NULL DEFAULT 1")
            # 钱包：账户（每用户一条）+ 流水
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    user_id INTEGER PRIMARY KEY,
                    balance REAL NOT NULL DEFAULT 0,
                    total_recharge REAL NOT NULL DEFAULT 0,
                    total_consume REAL NOT NULL DEFAULT 0,
                    updated_at TEXT
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_txns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    txn_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL,
                    biz_no TEXT,
                    remark TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_txn_user ON account_txns(user_id)")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_platform TEXT NOT NULL DEFAULT '1688',
                    source_url TEXT NOT NULL UNIQUE,
                    source_offer_id TEXT,
                    source_title TEXT NOT NULL,
                    purchase_url TEXT NOT NULL DEFAULT '',
                    purchase_note TEXT NOT NULL DEFAULT '',
                    ozon_title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    price TEXT NOT NULL,
                    old_price TEXT NOT NULL,
                    stock INTEGER NOT NULL,
                    images_json TEXT NOT NULL,
                    attributes_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    validation_errors_json TEXT NOT NULL,
                    publish_response_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column("drafts", "source_platform", "TEXT NOT NULL DEFAULT '1688'")
            self._ensure_column("drafts", "purchase_url", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("drafts", "purchase_note", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("drafts", "weight_g", "INTEGER")
            self._ensure_column("drafts", "length_mm", "INTEGER")
            self._ensure_column("drafts", "width_mm", "INTEGER")
            self._ensure_column("drafts", "height_mm", "INTEGER")
            self._ensure_column("drafts", "type_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("drafts", "brand_id", "INTEGER")
            self._ensure_column("drafts", "brand_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("drafts", "cost_cny", "REAL")      # 1688 进价(¥)，定价用
            self._ensure_column("drafts", "video_url", "TEXT")     # 来源视频(1688)
            self._ensure_column("drafts", "local_images_json", "TEXT")  # 下载到本地的图片(/media 路径)
            self._ensure_column("drafts", "pricing_json", "TEXT")  # 完整定价快照(参数+结果)
            self._ensure_column("drafts", "source", "TEXT NOT NULL DEFAULT ''")           # 来源: ozon_import/ozon_scrape/1688_scrape
            self._ensure_column("drafts", "ozon_product_id", "INTEGER")                    # Ozon 商品ID，反向同步用
            self._ensure_column("drafts", "offer_id", "TEXT NOT NULL DEFAULT ''")          # 卖家货号，订单关联钥匙
            self._ensure_column("drafts", "supplier", "TEXT NOT NULL DEFAULT ''")          # 1688 供应商名
            self._ensure_column("drafts", "warehouse_id", "INTEGER")                        # 本地关联的发货仓(④仓库)，批量设置用
            self._ensure_column("drafts", "source_raw_json", "TEXT")   # 采集原始全量(喂 AI)
            self._ensure_column("drafts", "ai_proposal_json", "TEXT")   # AI 待确认草案(整份JSON)，应用后清空
            self._migrate_drafts_multiuser()   # 加 user_id + 把 source_url 全局唯一改成 (user_id,source_url) 唯一
            self._migrate_drafts_store_scoped()  # 加 store_client_id（草稿绑定店）+ 唯一键改成 (user_id,store_client_id,source_url)
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS commission_map ("
                "description_category_id INTEGER, type_id INTEGER, "
                "parent_en TEXT, sub_en TEXT, rfbs_json TEXT, updated_at TEXT, "
                "PRIMARY KEY(description_category_id, type_id))"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS catalog_cache ("
                "language TEXT PRIMARY KEY, leaves_json TEXT NOT NULL, fetched_at TEXT NOT NULL)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS catalog_tree_cache ("
                "language TEXT PRIMARY KEY, tree_json TEXT NOT NULL, fetched_at TEXT NOT NULL)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS attribute_values_cache ("
                "description_category_id INTEGER, type_id INTEGER, attribute_id INTEGER, language TEXT NOT NULL DEFAULT 'ZH_HANS', "
                "dictionary_value_id INTEGER, value TEXT, info TEXT, fetched_at TEXT, "
                "PRIMARY KEY(description_category_id, type_id, attribute_id, language, dictionary_value_id))"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS category_attr_cache ("
                "description_category_id INTEGER, type_id INTEGER, language TEXT NOT NULL DEFAULT 'ZH_HANS', "
                "attrs_json TEXT NOT NULL, fetched_at TEXT NOT NULL, "
                "PRIMARY KEY(description_category_id, type_id, language))"
            )
            self._migrate_attribute_values_cache_language()
            self._migrate_category_attr_cache_language()
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_av_cache "
                "ON attribute_values_cache(description_category_id, type_id, attribute_id, language, value)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS warehouses ("
                "warehouse_id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', "
                "is_rfbs INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT '', "
                "is_default INTEGER NOT NULL DEFAULT 0, fetched_at TEXT)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS postings ("
                "posting_number TEXT PRIMARY KEY, ozon_order_id TEXT, status TEXT, "
                "ship_by TEXT, products_json TEXT NOT NULL DEFAULT '[]', "
                "warehouse_id INTEGER, raw_json TEXT, synced_at TEXT)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS procurement ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, posting_number TEXT NOT NULL, "
                "offer_id TEXT NOT NULL, qty INTEGER NOT NULL DEFAULT 1, "
                "purchase_state TEXT NOT NULL DEFAULT '待采购', supplier TEXT NOT NULL DEFAULT '', "
                "purchase_url TEXT NOT NULL DEFAULT '', cost_cny REAL, note TEXT NOT NULL DEFAULT '', "
                "updated_at TEXT, UNIQUE(posting_number, offer_id))"
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS offer_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    sku TEXT,
                    captured_at TEXT NOT NULL,
                    follow_count INTEGER,
                    price_min REAL,
                    price_max REAL,
                    sellers_json TEXT
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_offer_snap_pid ON offer_snapshots(product_id)"
            )
            # 店铺级隔离：仓库/订单/采购/快照都加 store_client_id（按当前店过滤）
            self._ensure_column("warehouses", "store_client_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("postings", "store_client_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("procurement", "store_client_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("offer_snapshots", "store_client_id", "TEXT NOT NULL DEFAULT ''")
            self._migrate_store_scoped_aux()
            self.conn.commit()

    # ---------- 类目/属性值 本地缓存 ----------
    def save_catalog_leaves(self, language: str, leaves: list[dict[str, Any]]) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO catalog_cache(language, leaves_json, fetched_at) VALUES(?,?,?) "
                "ON CONFLICT(language) DO UPDATE SET leaves_json=excluded.leaves_json, fetched_at=excluded.fetched_at",
                (language, dumps_json(leaves), utc_now_iso()),
            )
            self.conn.commit()

    def load_catalog_leaves(self, language: str) -> list[dict[str, Any]] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT leaves_json FROM catalog_cache WHERE language=?", (language,)
            ).fetchone()
        return loads_json(row["leaves_json"], None) if row else None

    def save_catalog_tree(self, language: str, tree: Any) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO catalog_tree_cache(language, tree_json, fetched_at) VALUES(?,?,?) "
                "ON CONFLICT(language) DO UPDATE SET tree_json=excluded.tree_json, fetched_at=excluded.fetched_at",
                (language, dumps_json(tree), utc_now_iso()),
            )
            self.conn.commit()

    def load_catalog_tree(self, language: str) -> Any | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT tree_json FROM catalog_tree_cache WHERE language=?", (language,)
            ).fetchone()
        return loads_json(row["tree_json"], None) if row else None

    def save_category_attrs(self, cat: int, type_id: int, attrs: list[dict[str, Any]], language: str = "ZH_HANS") -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO category_attr_cache(description_category_id, type_id, language, attrs_json, fetched_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(description_category_id, type_id, language) "
                "DO UPDATE SET attrs_json=excluded.attrs_json, fetched_at=excluded.fetched_at",
                (int(cat), int(type_id), str(language or "ZH_HANS"), dumps_json(attrs), utc_now_iso()),
            )
            self.conn.commit()

    def load_category_attrs(
        self, cat: int, type_id: int, language: str = "ZH_HANS", *, max_age_days: int = 30
    ) -> list[dict[str, Any]] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT attrs_json, fetched_at FROM category_attr_cache "
                "WHERE description_category_id=? AND type_id=? AND language=?",
                (int(cat), int(type_id), str(language or "ZH_HANS")),
            ).fetchone()
        if not row:
            return None
        # TTL：超过 max_age_days 视为过期，返回 None 触发重新拉取（属性表会随类目调整变化）
        fetched = _parse_iso(row["fetched_at"])
        if fetched is not None:
            age = datetime.now(timezone.utc) - fetched
            if age > timedelta(days=max_age_days):
                return None
        attrs = loads_json(row["attrs_json"], None)
        # 空列表不算有效缓存：可能是当时 API 抽风返回空，别让它永久屏蔽必填校验
        if not attrs:
            return None
        return attrs

    # ---------- 佣金类目映射（按 Ozon 类目记住对应的 realFBS 佣金类目）----------
    def save_commission_map(
        self, cat: int, type_id: int, parent_en: str, sub_en: str, rfbs: list[float]
    ) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO commission_map(description_category_id, type_id, parent_en, sub_en, rfbs_json, updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(description_category_id, type_id) "
                "DO UPDATE SET parent_en=excluded.parent_en, sub_en=excluded.sub_en, "
                "rfbs_json=excluded.rfbs_json, updated_at=excluded.updated_at",
                (int(cat), int(type_id), str(parent_en or ""), str(sub_en or ""),
                 dumps_json(rfbs or []), utc_now_iso()),
            )
            self.conn.commit()

    def load_commission_map(self, cat: int, type_id: int) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT parent_en, sub_en, rfbs_json FROM commission_map "
                "WHERE description_category_id=? AND type_id=?",
                (int(cat), int(type_id)),
            ).fetchone()
        if not row:
            return None
        return {"parent_en": row["parent_en"], "sub_en": row["sub_en"],
                "rfbs": loads_json(row["rfbs_json"], [])}

    def save_attribute_values(
        self, cat: int, type_id: int, attr: int, values: list[dict[str, Any]], language: str = "ZH_HANS"
    ) -> int:
        now = utc_now_iso()
        n = 0
        lang = str(language or "ZH_HANS")
        with self.lock:
            for v in values or []:
                vid = v.get("id") or v.get("dictionary_value_id")
                if not vid:
                    continue
                self.conn.execute(
                    "INSERT INTO attribute_values_cache"
                    "(description_category_id,type_id,attribute_id,language,dictionary_value_id,value,info,fetched_at) "
                    "VALUES(?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(description_category_id,type_id,attribute_id,language,dictionary_value_id) "
                    "DO UPDATE SET value=excluded.value, info=excluded.info, fetched_at=excluded.fetched_at",
                    (int(cat), int(type_id), int(attr), lang, int(vid),
                     str(v.get("value") or ""), str(v.get("info") or ""), now),
                )
                n += 1
            self.conn.commit()
        return n

    def find_attribute_values(
        self, cat: int, type_id: int, attr: int, query: str, language: str = "ZH_HANS", *, limit: int = 30
    ) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT dictionary_value_id AS id, value, info FROM attribute_values_cache "
                "WHERE description_category_id=? AND type_id=? AND attribute_id=? AND language=? "
                "AND value LIKE ? COLLATE NOCASE LIMIT ?",
                (int(cat), int(type_id), int(attr), str(language or "ZH_HANS"), f"%{query}%", int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_category_attr_cache_language(self) -> None:
        info = self.conn.execute("PRAGMA table_info(category_attr_cache)").fetchall()
        names = [row["name"] for row in info]
        if "language" in names:
            return
        rows = self.conn.execute(
            "SELECT description_category_id, type_id, attrs_json, fetched_at FROM category_attr_cache"
        ).fetchall()
        self.conn.execute("ALTER TABLE category_attr_cache RENAME TO category_attr_cache_old")
        self.conn.execute(
            "CREATE TABLE category_attr_cache ("
            "description_category_id INTEGER, type_id INTEGER, language TEXT NOT NULL DEFAULT 'ZH_HANS', "
            "attrs_json TEXT NOT NULL, fetched_at TEXT NOT NULL, "
            "PRIMARY KEY(description_category_id, type_id, language))"
        )
        for row in rows:
            self.conn.execute(
                "INSERT OR REPLACE INTO category_attr_cache"
                "(description_category_id, type_id, language, attrs_json, fetched_at) VALUES(?,?,?,?,?)",
                (row["description_category_id"], row["type_id"], "ZH_HANS", row["attrs_json"], row["fetched_at"]),
            )
        self.conn.execute("DROP TABLE category_attr_cache_old")
        self.conn.commit()

    def _migrate_attribute_values_cache_language(self) -> None:
        info = self.conn.execute("PRAGMA table_info(attribute_values_cache)").fetchall()
        names = [row["name"] for row in info]
        if "language" in names:
            return
        rows = self.conn.execute(
            "SELECT description_category_id, type_id, attribute_id, dictionary_value_id, value, info, fetched_at "
            "FROM attribute_values_cache"
        ).fetchall()
        self.conn.execute("ALTER TABLE attribute_values_cache RENAME TO attribute_values_cache_old")
        self.conn.execute(
            "CREATE TABLE attribute_values_cache ("
            "description_category_id INTEGER, type_id INTEGER, attribute_id INTEGER, language TEXT NOT NULL DEFAULT 'ZH_HANS', "
            "dictionary_value_id INTEGER, value TEXT, info TEXT, fetched_at TEXT, "
            "PRIMARY KEY(description_category_id, type_id, attribute_id, language, dictionary_value_id))"
        )
        for row in rows:
            self.conn.execute(
                "INSERT OR REPLACE INTO attribute_values_cache"
                "(description_category_id,type_id,attribute_id,language,dictionary_value_id,value,info,fetched_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    row["description_category_id"], row["type_id"], row["attribute_id"], "ZH_HANS",
                    row["dictionary_value_id"], row["value"], row["info"], row["fetched_at"],
                ),
            )
        self.conn.execute("DROP TABLE attribute_values_cache_old")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_av_cache "
            "ON attribute_values_cache(description_category_id, type_id, attribute_id, language, value)"
        )
        self.conn.commit()

    def _migrate_settings_multiuser(self) -> None:
        """旧库 settings 是 (key,value) 单例 → 迁移到 (user_id,key,value)。
        全局键(jwt_secret/oss_*)归 user_id=0，其余归 user_id=1(admin 承接旧配置)。"""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(settings)").fetchall()]
        if "user_id" in cols:
            return  # 已是新结构
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        self.conn.execute("ALTER TABLE settings RENAME TO settings_old")
        self.conn.execute(
            "CREATE TABLE settings (user_id INTEGER NOT NULL DEFAULT 0, key TEXT NOT NULL, "
            "value TEXT NOT NULL, PRIMARY KEY(user_id, key))"
        )
        for row in rows:
            uid = 0 if row["key"] in GLOBAL_SETTING_KEYS else 1
            self.conn.execute(
                "INSERT INTO settings(user_id, key, value) VALUES(?, ?, ?)",
                (uid, row["key"], row["value"]),
            )
        self.conn.execute("DROP TABLE settings_old")
        self.conn.commit()

    def _migrate_drafts_multiuser(self) -> None:
        """旧 drafts 无 user_id 且 source_url 全局 UNIQUE → 重建为带 user_id、UNIQUE(user_id,source_url)。
        动态读列定义重建（schema 漂移安全）；旧数据全部归 user_id=1(admin)。带行数校验防丢数据。"""
        info = self.conn.execute("PRAGMA table_info(drafts)").fetchall()
        names = [r[1] for r in info]
        if "user_id" in names:
            return
        defs = []
        for r in info:
            name, ctype, notnull, dflt = r[1], r[2], r[3], r[4]
            if name == "id":
                defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
                continue
            d = f"{name} {ctype or 'TEXT'}"
            if notnull:
                d += " NOT NULL"
            if dflt is not None:
                d += f" DEFAULT {dflt}"
            defs.append(d)
        col_defs = ", ".join(defs)
        common = ", ".join(names)
        with self.lock:
            old_count = self.conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            self.conn.execute("ALTER TABLE drafts RENAME TO drafts_old")
            self.conn.execute(
                f"CREATE TABLE drafts (user_id INTEGER NOT NULL DEFAULT 1, {col_defs}, "
                f"UNIQUE(user_id, source_url))"
            )
            self.conn.execute(
                f"INSERT INTO drafts (user_id, {common}) SELECT 1, {common} FROM drafts_old"
            )
            new_count = self.conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            if new_count != old_count:
                self.conn.execute("DROP TABLE drafts")
                self.conn.execute("ALTER TABLE drafts_old RENAME TO drafts")
                raise RuntimeError(f"drafts 迁移行数不符 {old_count}->{new_count}，已回滚")
            self.conn.execute("DROP TABLE drafts_old")
            self.conn.commit()

    def _migrate_drafts_store_scoped(self) -> None:
        """drafts 加 store_client_id（草稿绑定店铺）并把唯一键改成 (user_id, store_client_id, source_url)。
        旧草稿 store_client_id 回填为该用户默认店(settings.ozon_client_id)，无则 ''。带行数校验防丢数据。"""
        info = self.conn.execute("PRAGMA table_info(drafts)").fetchall()
        names = [r[1] for r in info]
        if "store_client_id" in names:
            return
        defs = []
        for r in info:
            name, ctype, notnull, dflt = r[1], r[2], r[3], r[4]
            if name == "id":
                defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
                continue
            d = f"{name} {ctype or 'TEXT'}"
            if notnull:
                d += " NOT NULL"
            if dflt is not None:
                d += f" DEFAULT {dflt}"
            defs.append(d)
        col_defs = ", ".join(defs)
        common = ", ".join(names)
        with self.lock:
            old_count = self.conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            self.conn.execute("ALTER TABLE drafts RENAME TO drafts_old")
            self.conn.execute(
                f"CREATE TABLE drafts ({col_defs}, store_client_id TEXT NOT NULL DEFAULT '', "
                f"UNIQUE(user_id, store_client_id, source_url))"
            )
            # 回填 store_client_id = 该用户默认店(settings.ozon_client_id)，无则 ''
            # settings.value 是 JSON 编码（字符串带引号），用 json_extract 解出裸值，避免存成 "5020196"
            self.conn.execute(
                f"INSERT INTO drafts ({common}, store_client_id) "
                f"SELECT {common}, COALESCE("
                f"(SELECT json_extract(value,'$') FROM settings s "
                f" WHERE s.user_id=drafts_old.user_id AND s.key='ozon_client_id'), '') "
                f"FROM drafts_old"
            )
            new_count = self.conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
            if new_count != old_count:
                self.conn.execute("DROP TABLE drafts")
                self.conn.execute("ALTER TABLE drafts_old RENAME TO drafts")
                raise RuntimeError(f"drafts store 迁移行数不符 {old_count}->{new_count}，已回滚")
            self.conn.execute("DROP TABLE drafts_old")
            self.conn.commit()

    def _migrate_store_scoped_aux(self) -> None:
        """仓库/订单/采购/快照旧行无 store_client_id → 回填管理员默认店(settings user_id=1 ozon_client_id)。
        新行 upsert 时各自带真实店，不会是空；故只回填遗留空行，幂等。"""
        row = self.conn.execute(
            "SELECT json_extract(value,'$') FROM settings WHERE user_id=1 AND key='ozon_client_id'"
        ).fetchone()
        cid = (row[0] if row and row[0] is not None else "") or ""
        if not cid:
            return
        for t in ("warehouses", "postings", "procurement", "offer_snapshots"):
            self.conn.execute(
                f"UPDATE {t} SET store_client_id=? WHERE store_client_id=''", (str(cid),)
            )

    def get_settings(self, user_id: int | None = None) -> dict[str, Any]:
        """某用户的设置；自动并入系统级全局(user_id=0，如 OSS/jwt_secret)。"""
        user_id = _uid(user_id)
        with self.lock:
            rows = self.conn.execute(
                "SELECT key, value FROM settings WHERE user_id IN (0, ?)", (user_id,)
            ).fetchall()
        settings: dict[str, Any] = {}
        for row in rows:
            settings[row["key"]] = loads_json(row["value"], row["value"])
        return settings

    def save_settings(self, settings: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        """写设置：全局键(GLOBAL_SETTING_KEYS)落 user_id=0，其余落该用户。"""
        user_id = _uid(user_id)
        with self.lock:
            for key, value in settings.items():
                uid = 0 if key in GLOBAL_SETTING_KEYS else user_id
                self.conn.execute(
                    "INSERT INTO settings(user_id, key, value) VALUES(?, ?, ?) "
                    "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
                    (uid, key, dumps_json(value)),
                )
            self.conn.commit()
        return self.get_settings(user_id)

    # ---- 用户（多用户鉴权）----
    def create_user(self, username: str, password_hash: str, role: str = "user",
                    max_stores: int = 1) -> dict[str, Any]:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO users(username, password_hash, role, status, created_at, max_stores) "
                "VALUES(?, ?, ?, 'active', ?, ?)",
                (username, password_hash, role, utc_now_iso(), int(max_stores)),
            )
            self.conn.commit()
            uid = cur.lastrowid
        return self.get_user_by_id(uid)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def count_users(self) -> int:
        with self.lock:
            return int(self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    # ---- 钱包（按 user_id 隔离，contextvar 默认）----
    def get_account(self, user_id: int | None = None) -> dict[str, Any]:
        """取账户，没有则开户（余额0）。"""
        user_id = _uid(user_id)
        with self.lock:
            row = self.conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO accounts(user_id, balance, total_recharge, total_consume, updated_at) "
                    "VALUES(?, 0, 0, 0, ?)",
                    (user_id, utc_now_iso()),
                )
                self.conn.commit()
                row = self.conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row)

    def _add_txn(self, user_id: int, txn_type: str, amount: float, balance_after: float,
                 biz_no: str | None, remark: str | None) -> None:
        self.conn.execute(
            "INSERT INTO account_txns(user_id, txn_type, amount, balance_after, biz_no, remark, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (user_id, txn_type, float(amount), float(balance_after), biz_no, remark, utc_now_iso()),
        )

    def recharge(self, amount: float, *, remark: str = "", biz_no: str | None = None,
                 user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        self.get_account(user_id)
        with self.lock:
            self.conn.execute(
                "UPDATE accounts SET balance=balance+?, total_recharge=total_recharge+?, updated_at=? "
                "WHERE user_id=?",
                (float(amount), float(amount), utc_now_iso(), user_id),
            )
            bal = self.conn.execute("SELECT balance FROM accounts WHERE user_id=?", (user_id,)).fetchone()[0]
            self._add_txn(user_id, "recharge", amount, bal, biz_no, remark)
            self.conn.commit()
        return self.get_account(user_id)

    def deduct(self, amount: float, *, biz_no: str | None = None, remark: str = "",
               user_id: int | None = None) -> bool:
        """原子扣款：仅 balance>=amount 才扣（条件 UPDATE 防并发超扣）。成功 True，余额不足 False。"""
        user_id = _uid(user_id)
        self.get_account(user_id)
        with self.lock:
            cur = self.conn.execute(
                "UPDATE accounts SET balance=balance-?, total_consume=total_consume+?, updated_at=? "
                "WHERE user_id=? AND balance>=?",
                (float(amount), float(amount), utc_now_iso(), user_id, float(amount)),
            )
            if cur.rowcount != 1:
                self.conn.commit()
                return False
            bal = self.conn.execute("SELECT balance FROM accounts WHERE user_id=?", (user_id,)).fetchone()[0]
            self._add_txn(user_id, "consume", amount, bal, biz_no, remark)
            self.conn.commit()
        return True

    def refund(self, amount: float, *, biz_no: str | None = None, remark: str = "",
               user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        self.get_account(user_id)
        with self.lock:
            self.conn.execute(
                "UPDATE accounts SET balance=balance+?, updated_at=? WHERE user_id=?",
                (float(amount), utc_now_iso(), user_id),
            )
            bal = self.conn.execute("SELECT balance FROM accounts WHERE user_id=?", (user_id,)).fetchone()[0]
            self._add_txn(user_id, "refund", amount, bal, biz_no, remark)
            self.conn.commit()
        return self.get_account(user_id)

    def list_txns(self, user_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        user_id = _uid(user_id)
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM account_txns WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def insert_draft(self, draft: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        store_cid = str(draft.get("store_client_id") or "")
        with self.lock:
            # 草稿绑定店：去重按 (user, store, source_url)，让同一来源能在多个店各存一份
            existing = self.find_by_source_url(draft["source_url"], user_id, store_cid)
            if existing:
                return existing
            errors = validate_draft(draft)
            self.conn.execute(
                """
                INSERT INTO drafts (
                    user_id, store_client_id,
                    source_platform, source_url, source_offer_id, source_title, purchase_url,
                    purchase_note, ozon_title, description, category_id, type_id,
                    brand_id, brand_name, price, old_price,
                    stock, weight_g, length_mm, width_mm, height_mm,
                    cost_cny, video_url, local_images_json,
                    source, ozon_product_id, offer_id, supplier, source_raw_json,
                    images_json, attributes_json, status, validation_errors_json,
                    publish_response_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    store_cid,
                    draft.get("source_platform", "1688"),
                    draft["source_url"],
                    draft.get("source_offer_id"),
                    draft["source_title"],
                    draft.get("purchase_url", ""),
                    draft.get("purchase_note", ""),
                    draft["ozon_title"],
                    draft["description"],
                    draft["category_id"],
                    draft.get("type_id", ""),
                    _to_int_or_none(draft.get("brand_id")),
                    str(draft.get("brand_name") or ""),
                    draft["price"],
                    draft["old_price"],
                    draft["stock"],
                    draft.get("weight_g"),
                    draft.get("length_mm"),
                    draft.get("width_mm"),
                    draft.get("height_mm"),
                    _to_float_or_none(draft.get("cost_cny")),
                    str(draft.get("video_url") or ""),
                    dumps_json(draft.get("local_images") or []),
                    str(draft.get("source") or ""),
                    _to_int_or_none(draft.get("ozon_product_id")),
                    str(draft.get("offer_id") or ""),
                    str(draft.get("supplier") or ""),
                    dumps_json(draft.get("source_raw") or {}),
                    dumps_json(draft["images"]),
                    dumps_json(draft["attributes"]),
                    "invalid" if errors else draft["status"],
                    dumps_json(errors),
                    dumps_json(draft["publish_response"]) if draft["publish_response"] is not None else None,
                    draft["created_at"],
                    draft["updated_at"],
                ),
            )
            self.conn.commit()
            return self.find_by_source_url(draft["source_url"], user_id) or draft

    def list_drafts(self, user_id: int | None = None) -> list[dict[str, Any]]:
        user_id = _uid(user_id)
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM drafts WHERE user_id = ? ORDER BY id DESC", (int(user_id),)
            ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    def count_by_status(self, user_id: int | None = None, store_client_id: str | None = None) -> dict[str, int]:
        """各状态计数 + all 总数（给前端 Tab 用，后端分页后前端无法自算）。
        store_client_id 非 None 时按当前店过滤（草稿绑定店后，列表/计数都是店级）。"""
        user_id = _uid(user_id)
        where, params = ("WHERE user_id = ?", [int(user_id)])
        if store_client_id is not None:
            where += " AND store_client_id = ?"
            params.append(str(store_client_id or ""))
        with self.lock:
            total = self.conn.execute(
                f"SELECT COUNT(*) c FROM drafts {where}", params
            ).fetchone()["c"]
            rows = self.conn.execute(
                f"SELECT status, COUNT(*) c FROM drafts {where} GROUP BY status", params
            ).fetchall()
        counts = {"all": total, "invalid": 0, "ready": 0, "failed": 0, "published": 0}
        for r in rows:
            if r["status"] in counts:
                counts[r["status"]] += r["c"]
        return counts

    def list_drafts_page(
        self, *, status: str = "all", page: int = 1, page_size: int = 20,
        user_id: int | None = None, store_client_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """真·后端分页：按 user_id + status (+当前店) 过滤 + LIMIT/OFFSET。返回 (当前页草稿, 该过滤下总数)。"""
        user_id = _uid(user_id)
        status = (status or "all").strip()
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))   # 上限 200，防一次拉爆
        where, params = ("WHERE user_id = ?", [int(user_id)])
        if store_client_id is not None:
            where += " AND store_client_id = ?"
            params.append(str(store_client_id or ""))
        if status not in ("", "all"):
            where += " AND status = ?"
            params.append(status)
        offset = (page - 1) * page_size
        with self.lock:
            total = self.conn.execute(
                f"SELECT COUNT(*) c FROM drafts {where}", params
            ).fetchone()["c"]
            rows = self.conn.execute(
                f"SELECT * FROM drafts {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
        return [self._row_to_draft(r) for r in rows], total

    def get_draft(self, draft_id: int, user_id: int | None = None) -> dict[str, Any] | None:
        user_id = _uid(user_id)
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM drafts WHERE id = ? AND user_id = ?", (draft_id, int(user_id))
            ).fetchone()
        return self._row_to_draft(row) if row else None

    def find_by_source_url(
        self, source_url: str, user_id: int | None = None, store_client_id: str | None = None
    ) -> dict[str, Any] | None:
        """按 (user, source_url) 查；store_client_id 非 None 时再按店过滤（草稿绑定店后去重要按店）。"""
        user_id = _uid(user_id)
        sql = "SELECT * FROM drafts WHERE source_url = ? AND user_id = ?"
        params: list[Any] = [source_url, int(user_id)]
        if store_client_id is not None:
            sql += " AND store_client_id = ?"
            params.append(str(store_client_id or ""))
        sql += " ORDER BY id DESC LIMIT 1"
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
        return self._row_to_draft(row) if row else None

    def find_by_offer_id(self, offer_id: str, user_id: int | None = None) -> dict[str, Any] | None:
        user_id = _uid(user_id)
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM drafts WHERE offer_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (str(offer_id), int(user_id)),
            ).fetchone()
        return self._row_to_draft(row) if row else None

    def update_draft(self, draft_id: int, patch: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        with self.lock:
            current = self.get_draft(draft_id, user_id)
            if current is None:
                raise KeyError(f"draft {draft_id} not found")
            updated = {**current, **patch, "updated_at": utc_now_iso()}
            errors = list(validate_draft(updated))
            # 调用方可显式传入额外校验错误（如发布时的"缺必填属性"），合并持久化
            for extra in patch.get("validation_errors") or []:
                if extra not in errors:
                    errors.append(extra)
            status = patch.get("status") or ("ready" if not errors else "invalid")
            self.conn.execute(
                """
                UPDATE drafts
                SET source_platform=?, source_title=?, purchase_url=?, purchase_note=?,
                    ozon_title=?, description=?, category_id=?, type_id=?,
                    brand_id=?, brand_name=?, price=?, old_price=?,
                    stock=?, weight_g=?, length_mm=?, width_mm=?, height_mm=?,
                    cost_cny=?, video_url=?, local_images_json=?,
                    source=?, ozon_product_id=?, offer_id=?, supplier=?, warehouse_id=?, source_raw_json=?,
                    images_json=?, attributes_json=?, status=?,
                    validation_errors_json=?, publish_response_json=?, pricing_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    updated.get("source_platform", "1688"),
                    updated["source_title"],
                    updated.get("purchase_url", ""),
                    updated.get("purchase_note", ""),
                    updated["ozon_title"],
                    updated["description"],
                    updated["category_id"],
                    str(updated.get("type_id") or ""),
                    _to_int_or_none(updated.get("brand_id")),
                    str(updated.get("brand_name") or ""),
                    updated["price"],
                    updated["old_price"],
                    int(updated["stock"]),
                    _to_int_or_none(updated.get("weight_g")),
                    _to_int_or_none(updated.get("length_mm")),
                    _to_int_or_none(updated.get("width_mm")),
                    _to_int_or_none(updated.get("height_mm")),
                    _to_float_or_none(updated.get("cost_cny")),
                    str(updated.get("video_url") or ""),
                    dumps_json(updated.get("local_images") or []),
                    str(updated.get("source") or ""),
                    _to_int_or_none(updated.get("ozon_product_id")),
                    str(updated.get("offer_id") or ""),
                    str(updated.get("supplier") or ""),
                    _to_int_or_none(updated.get("warehouse_id")),
                    dumps_json(updated.get("source_raw") or {}),
                    dumps_json(updated["images"]),
                    dumps_json(updated["attributes"]),
                    status,
                    dumps_json(errors),
                    dumps_json(updated.get("publish_response")) if updated.get("publish_response") is not None else None,
                    dumps_json(updated.get("pricing")) if updated.get("pricing") is not None else None,
                    updated["updated_at"],
                    draft_id,
                ),
            )
            self.conn.commit()
            draft = self.get_draft(draft_id, user_id)
            if draft is None:
                raise KeyError(f"draft {draft_id} not found after update")
            return draft

    def set_ai_proposal(self, draft_id: int, proposal: dict | None) -> None:
        """写/清空草稿的 AI 待确认草案列；不触碰其它字段、不重算 status。"""
        with self.lock:
            self.conn.execute(
                "UPDATE drafts SET ai_proposal_json=? WHERE id=?",
                (dumps_json(proposal) if proposal is not None else None, int(draft_id)),
            )
            self.conn.commit()

    def delete_draft(self, draft_id: int, user_id: int | None = None) -> None:
        user_id = _uid(user_id)
        with self.lock:
            self.conn.execute(
                "DELETE FROM drafts WHERE id = ? AND user_id = ?", (draft_id, int(user_id))
            )
            self.conn.commit()

    # ---------- 仓库（功能4）----------
    def upsert_warehouses(self, items: list[dict[str, Any]], store_client_id: str = "") -> None:
        now = utc_now_iso()
        scid = str(store_client_id or "")
        with self.lock:
            for w in items or []:
                wid = _to_int_or_none(w.get("warehouse_id"))
                if wid is None:
                    continue
                self.conn.execute(
                    "INSERT INTO warehouses(warehouse_id, name, is_rfbs, status, fetched_at, store_client_id) "
                    "VALUES(?,?,?,?,?,?) ON CONFLICT(warehouse_id) DO UPDATE SET "
                    "name=excluded.name, is_rfbs=excluded.is_rfbs, status=excluded.status, "
                    "fetched_at=excluded.fetched_at, store_client_id=excluded.store_client_id",
                    (wid, str(w.get("name") or ""), 1 if w.get("is_rfbs") else 0,
                     str(w.get("status") or ""), now, scid),
                )
            self.conn.commit()

    def list_warehouses(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT warehouse_id, name, is_rfbs, status, is_default, fetched_at, store_client_id "
               "FROM warehouses")
        params: list[Any] = []
        if store_client_id is not None:
            sql += " WHERE store_client_id = ?"
            params.append(str(store_client_id or ""))
        sql += " ORDER BY warehouse_id"
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["is_rfbs"] = bool(d["is_rfbs"])
            d["is_default"] = bool(d["is_default"])
            out.append(d)
        return out

    def set_default_warehouse(self, warehouse_id: int, store_client_id: str = "") -> None:
        """每店一个默认仓：只在该店范围内清旧默认、设新默认。"""
        scid = str(store_client_id or "")
        with self.lock:
            self.conn.execute("UPDATE warehouses SET is_default=0 WHERE store_client_id=?", (scid,))
            self.conn.execute(
                "UPDATE warehouses SET is_default=1 WHERE warehouse_id=? AND store_client_id=?",
                (int(warehouse_id), scid),
            )
            self.conn.commit()

    # ---------- 订单（功能5）----------
    def upsert_postings(self, items: list[dict[str, Any]], store_client_id: str = "") -> None:
        now = utc_now_iso()
        scid = str(store_client_id or "")
        with self.lock:
            for p in items or []:
                num = str(p.get("posting_number") or "").strip()
                if not num:
                    continue
                self.conn.execute(
                    "INSERT INTO postings(posting_number, ozon_order_id, status, ship_by, "
                    "products_json, warehouse_id, raw_json, synced_at, store_client_id) VALUES(?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(posting_number) DO UPDATE SET ozon_order_id=excluded.ozon_order_id, "
                    "status=excluded.status, ship_by=excluded.ship_by, "
                    "products_json=excluded.products_json, warehouse_id=excluded.warehouse_id, "
                    "raw_json=excluded.raw_json, synced_at=excluded.synced_at, store_client_id=excluded.store_client_id",
                    (num, str(p.get("ozon_order_id") or ""), str(p.get("status") or ""),
                     p.get("ship_by"), dumps_json(p.get("products") or []),
                     _to_int_or_none(p.get("warehouse_id")), dumps_json(p.get("raw") or {}), now, scid),
                )
            self.conn.commit()

    def list_postings(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM postings"
        params: list[Any] = []
        if store_client_id is not None:
            sql += " WHERE store_client_id = ?"
            params.append(str(store_client_id or ""))
        sql += " ORDER BY synced_at DESC"
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["products"] = loads_json(d.pop("products_json"), [])
            d["raw"] = loads_json(d.pop("raw_json"), {})
            out.append(d)
        return out

    def get_posting(self, posting_number: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM postings WHERE posting_number=? LIMIT 1", (str(posting_number),)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["products"] = loads_json(d.pop("products_json"), [])
        d["raw"] = loads_json(d.pop("raw_json"), {})
        return d

    # ---------- 备货（功能5）----------
    def rebuild_procurement(self, store_client_id: str = "") -> None:
        """按 postings × drafts(offer_id) JOIN 重建待采购行；已存在的保留采购状态/备注。
        按店重建：只用该店 postings，offer_id 在该店草稿里找供应商/成本，采购行带 store_client_id。"""
        scid = str(store_client_id or "")
        with self.lock:
            existing = {
                (r["posting_number"], r["offer_id"]): r
                for r in self.conn.execute(
                    "SELECT posting_number, offer_id, purchase_state, note FROM procurement WHERE store_client_id=?",
                    (scid,),
                ).fetchall()
            }
            now = utc_now_iso()
            for p in self.conn.execute(
                "SELECT posting_number, products_json FROM postings WHERE store_client_id=?", (scid,)
            ).fetchall():
                for prod in loads_json(p["products_json"], []):
                    offer_id = str(prod.get("offer_id") or "").strip()
                    if not offer_id:
                        continue
                    qty = _to_int_or_none(prod.get("quantity")) or 1
                    src = self.conn.execute(
                        "SELECT supplier, purchase_url, cost_cny FROM drafts "
                        "WHERE offer_id=? AND store_client_id=? LIMIT 1",
                        (offer_id, scid),
                    ).fetchone()
                    # SELECT 已显式取这 3 列；src 为空（草稿里没这个 offer_id）时回退默认
                    supplier = src["supplier"] if src else ""
                    purchase_url = src["purchase_url"] if src else ""
                    cost_cny = src["cost_cny"] if src else None
                    prev = existing.get((p["posting_number"], offer_id))
                    state = prev["purchase_state"] if prev else "待采购"
                    note = prev["note"] if prev else ""
                    self.conn.execute(
                        "INSERT INTO procurement(posting_number, offer_id, qty, purchase_state, "
                        "supplier, purchase_url, cost_cny, note, updated_at, store_client_id) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(posting_number, offer_id) DO UPDATE SET qty=excluded.qty, "
                        "supplier=excluded.supplier, purchase_url=excluded.purchase_url, "
                        "cost_cny=excluded.cost_cny, updated_at=excluded.updated_at, "
                        "store_client_id=excluded.store_client_id",
                        (p["posting_number"], offer_id, qty, state,
                         str(supplier or ""), str(purchase_url or ""), cost_cny, note, now, scid),
                    )
            self.conn.commit()

    def list_procurement(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if store_client_id is not None:
            where = "WHERE p.store_client_id = ?"
            params.append(str(store_client_id or ""))
        with self.lock:
            # JOIN postings 取 ship_by，按截止时间升序（最紧急在前）；
            # NULL/空 ship_by 放最后（CASE coalesce NULL/'' → '9999...'）；
            # 相同 ship_by 按 posting_number 稳定排序。
            rows = self.conn.execute(
                f"""
                SELECT p.*, COALESCE(po.ship_by, '') AS ship_by
                FROM procurement p
                LEFT JOIN postings po ON po.posting_number = p.posting_number
                {where}
                ORDER BY
                    CASE WHEN COALESCE(po.ship_by, '') = '' THEN '9999-99-99' ELSE po.ship_by END ASC,
                    p.posting_number ASC
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def set_procurement_state(self, proc_id: int, state: str, *, note: str | None = None) -> None:
        with self.lock:
            if note is None:
                self.conn.execute(
                    "UPDATE procurement SET purchase_state=?, updated_at=? WHERE id=?",
                    (str(state), utc_now_iso(), int(proc_id)),
                )
            else:
                self.conn.execute(
                    "UPDATE procurement SET purchase_state=?, note=?, updated_at=? WHERE id=?",
                    (str(state), str(note), utc_now_iso(), int(proc_id)),
                )
            self.conn.commit()

    # ---------- 跟卖快照（插件用）----------
    def add_offer_snapshot(self, snap: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO offer_snapshots (product_id, sku, captured_at, follow_count, price_min, price_max, sellers_json, store_client_id)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(snap.get("product_id") or ""),
                    snap.get("sku"),
                    str(snap.get("captured_at") or utc_now_iso()),
                    _to_int_or_none(snap.get("follow_count")),
                    _to_float_or_none(snap.get("price_min")),
                    _to_float_or_none(snap.get("price_max")),
                    snap.get("sellers_json"),
                    str(snap.get("store_client_id") or ""),
                ),
            )
            self.conn.commit()
            return {"id": cur.lastrowid}

    def latest_offer_snapshot(self, product_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT id, product_id, sku, captured_at, follow_count, price_min, price_max, sellers_json"
                " FROM offer_snapshots WHERE product_id=? ORDER BY captured_at DESC, id DESC LIMIT 1",
                (str(product_id),),
            ).fetchone()
        return dict(row) if row else None

    def list_offer_snapshots(self, product_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, product_id, sku, captured_at, follow_count, price_min, price_max, sellers_json"
                " FROM offer_snapshots WHERE product_id=? ORDER BY captured_at ASC, id ASC LIMIT ?",
                (str(product_id), int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_drafts_by_variant_group(self, group: str) -> list[dict[str, Any]]:
        """返回 source_raw.variant_group == group 的所有草稿（按 id 升序）。"""
        if not group:
            return []
        out = []
        with self.lock:
            rows = self.conn.execute("SELECT id FROM drafts ORDER BY id ASC").fetchall()
        for r in rows:
            d = self.get_draft(r["id"])
            sr = d.get("source_raw") if d else None
            if isinstance(sr, str):
                sr = loads_json(sr, {})
            if isinstance(sr, dict) and str(sr.get("variant_group") or "") == str(group):
                out.append(d)
        return out

    def _row_to_draft(self, row: sqlite3.Row) -> dict[str, Any]:
        source_platform = row["source_platform"]
        purchase_url = row["purchase_url"] or (row["source_url"] if source_platform == "1688" else "")
        return {
            "id": row["id"],
            "user_id": row["user_id"] if "user_id" in row.keys() else 1,
            "store_client_id": row["store_client_id"] if "store_client_id" in row.keys() else "",
            "source_platform": source_platform,
            "source_url": row["source_url"],
            "source_offer_id": row["source_offer_id"],
            "source": row["source"] if "source" in row.keys() else "",
            "ozon_product_id": row["ozon_product_id"] if "ozon_product_id" in row.keys() else None,
            "offer_id": row["offer_id"] if "offer_id" in row.keys() else "",
            "supplier": row["supplier"] if "supplier" in row.keys() else "",
            "warehouse_id": row["warehouse_id"] if "warehouse_id" in row.keys() else None,
            "source_raw": loads_json(row["source_raw_json"], {}) if "source_raw_json" in row.keys() else {},
            "source_title": row["source_title"],
            "purchase_url": purchase_url,
            "purchase_note": row["purchase_note"],
            "ozon_title": row["ozon_title"],
            "description": row["description"],
            "category_id": row["category_id"],
            "type_id": row["type_id"],
            "brand_id": row["brand_id"],
            "brand_name": row["brand_name"],
            "price": row["price"],
            "old_price": row["old_price"],
            "stock": row["stock"],
            "weight_g": row["weight_g"],
            "length_mm": row["length_mm"],
            "width_mm": row["width_mm"],
            "height_mm": row["height_mm"],
            "images": loads_json(row["images_json"], []),
            "attributes": loads_json(row["attributes_json"], {}),
            "cost_cny": row["cost_cny"] if "cost_cny" in row.keys() else None,
            "video_url": (row["video_url"] if "video_url" in row.keys() else None) or "",
            "local_images": loads_json(row["local_images_json"], []) if "local_images_json" in row.keys() else [],
            "status": row["status"],
            "validation_errors": loads_json(row["validation_errors_json"], []),
            "publish_response": loads_json(row["publish_response_json"], None),
            "pricing": loads_json(row["pricing_json"], None) if "pricing_json" in row.keys() else None,
            "ai_proposal": loads_json(row["ai_proposal_json"], None) if "ai_proposal_json" in row.keys() else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
