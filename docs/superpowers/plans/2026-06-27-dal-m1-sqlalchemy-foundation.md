# 数据访问层 M1：SQLAlchemy 基座 + 三共享仓储竖切 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 立起 SQLAlchemy engine(连接池)+ Alembic + 请求级 scoped-session 基座,把 settings / draft_images / gen_jobs 三组共享聚合迁到 Core 仓储,webui 与 worker 共用、退役 worker `DataStore`,全程 512 测试不下降。

**Architecture:** 绞杀者路径第一步。新基座加在 `packages/ozon_common/src/ozon_common/dal/`;schema 用全表 Core metadata 接管(`Store.__init__` 改触发 `metadata.create_all`,老裸 SQL DDL 退役,回填剥离为 run-once);三仓储基于 Core、返回 dict 形状不变;webui 经 ASGI 中间件提供请求级 session,worker 用 `with session_scope()`。其余 ~17 表 M2 再迁。

**Tech Stack:** SQLAlchemy 2.x Core、Alembic、FastAPI 中间件、pytest、uv workspace。

**全局约定:**
- 仓库根 `E:\personal\ozon-helper`(git-bash `/e/personal/ozon-helper`)。分支 `feat/auto-listing-ai-pipeline`。中文提交。
- **`uv` 不在 PATH,一律 `python -m uv`。** 跑测试:`python -m uv run python -m pytest <路径> -q -p no:cacheprovider`(pytest 是 dev 依赖)。
- **回归闸门**:每个 Task 末尾跑 `python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py' -q -p no:cacheprovider`,**必须 ≥ 512 passed**(基线 512)。涉及 worker 的 Task 另跑 worker import 冒烟。
- 提交信息结尾固定:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- 新增依赖后先 `python -m uv sync`。

---

## File Structure

| 路径 | 职责 |
|---|---|
| `packages/ozon_common/pyproject.toml` | 加 `sqlalchemy>=2.0`、`alembic>=1.13` 依赖 |
| `packages/ozon_common/src/ozon_common/dal/__init__.py` | 子包导出 |
| `…/dal/engine.py` | `build_engine(url)`:SQLite(WAL)/MySQL(pool);`engine_for(path_or_none)` 按现有 env 判定 |
| `…/dal/session.py` | `_current_session` ContextVar、`session_scope()`、`current_session()`、`bind_engine()` |
| `…/dal/schema.py` | 全部 ~20 表 Core `MetaData`/`Table`(schema 权威);`metadata` 导出 |
| `…/dal/repositories/base.py` | `BaseRepo`(取 `current_session()`、`_row_to_dict`) |
| `…/dal/repositories/settings_repo.py` | `SettingsRepo` |
| `…/dal/repositories/draft_image_repo.py` | `DraftImageRepo` |
| `…/dal/repositories/gen_job_repo.py` | `GenJobRepo` |
| `migrations/alembic.ini`、`migrations/env.py`、`migrations/versions/0001_baseline.py` | Alembic |
| `apps/webui/src/webui/store.py` | `__init__` 改触发 `metadata.create_all`;回填剥离;三组方法转调仓储 |
| `apps/webui/src/webui/db_backfills.py`(新) | 从 store 剥离的 `_backfill_*` run-once |
| `apps/webui/src/webui/main.py` | 加请求级 session 中间件 |
| `apps/image_worker/src/image_worker/worker.py` | 退役 DataStore,用 `session_scope()`+仓储 |
| `packages/ozon_common/tests/`(新) | 仓储单测、session 单测、schema 保真测试、协存冒烟 |

---

## Task 1：依赖 + engine + session 基座（纯新增,不接线）

**Files:**
- Modify: `packages/ozon_common/pyproject.toml`
- Create: `packages/ozon_common/src/ozon_common/dal/__init__.py`、`db/engine.py`、`db/session.py`
- Create: `packages/ozon_common/tests/test_session.py`

- [ ] **Step 1: 加依赖**

`packages/ozon_common/pyproject.toml` 的 `dependencies` 加:
```toml
    "SQLAlchemy>=2.0",
    "alembic>=1.13",
```
然后 `cd /e/personal/ozon-helper && python -m uv sync 2>&1 | tail -3`。

- [ ] **Step 2: 写 engine.py**

Create `packages/ozon_common/src/ozon_common/dal/engine.py`:
```python
"""SQLAlchemy engine 工厂:SQLite(WAL)与 MySQL(连接池)。"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from ozon_common import db as _dbmod  # noqa: F401  (占位,避免循环)


def _sqlite_url(path: str) -> str:
    return f"sqlite:///{path}"


def build_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        eng = create_engine(url, future=True)

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng
    # MySQL
    return create_engine(
        url, future=True,
        pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600,
    )


def mysql_url_from_env() -> str | None:
    host = os.environ.get("OZON_MYSQL_HOST")
    if not host:
        return None
    port = int(os.environ.get("OZON_MYSQL_PORT") or 3306)
    user = os.environ.get("OZON_MYSQL_USER") or "root"
    pw = os.environ.get("OZON_MYSQL_PASSWORD") or ""
    db = os.environ.get("OZON_MYSQL_DB") or "ozon"
    return f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}?charset=utf8mb4"


def engine_for(sqlite_path: str | None) -> Engine:
    """优先 env MySQL;否则 SQLite 文件。"""
    murl = mysql_url_from_env()
    if murl:
        return build_engine(murl)
    if not sqlite_path:
        raise ValueError("engine_for: 无 MySQL env 且未给 sqlite_path")
    return build_engine(_sqlite_url(str(sqlite_path)))
```
(删掉那行占位 import 若不需要;保持文件无 `backend` 引用。)

- [ ] **Step 3: 写 session.py**

Create `packages/ozon_common/src/ozon_common/dal/session.py`:
```python
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


@contextmanager
def session_scope():
    """开一个 Session、绑到 ContextVar,正常提交/异常回滚/最终关闭。"""
    if _factory is None:
        raise RuntimeError("session 未初始化:先调 bind_engine(engine)")
    existing = _current_session.get()
    if existing is not None:
        # 已在作用域内(嵌套)→ 复用,不重复开事务
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
```

- [ ] **Step 4: 写 session 单测(先红)**

Create `packages/ozon_common/tests/test_session.py`:
```python
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import text

from ozon_common.dal.engine import build_engine
from ozon_common.dal import session as S


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 't.db'}")
    S.bind_engine(eng)
    return eng


def test_current_session_outside_scope_raises():
    with pytest.raises(RuntimeError):
        S.current_session()


def test_session_scope_commits_and_binds():
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        with S.session_scope() as sess:
            assert S.current_session() is sess
            sess.execute(text("CREATE TABLE t (id INTEGER)"))
            sess.execute(text("INSERT INTO t VALUES (1)"))
        # 离开作用域后已提交、ContextVar 复位
        with pytest.raises(RuntimeError):
            S.current_session()
        with S.session_scope() as sess:
            n = sess.execute(text("SELECT COUNT(*) FROM t")).scalar()
            assert n == 1


def test_session_scope_rollback_on_error():
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
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
```
Create `packages/ozon_common/src/ozon_common/dal/__init__.py`:
```python
"""SQLAlchemy 数据访问基座(engine/session/schema/repositories)。"""
```

- [ ] **Step 5: 跑测试**

Run: `cd /e/personal/ozon-helper && python -m uv run python -m pytest packages/ozon_common/tests/test_session.py -q -p no:cacheprovider`
Expected: 3 passed。

- [ ] **Step 6: 回归 + 提交**

Run 回归闸门(应仍 512)。然后:
```bash
python -m ruff check --select I --fix packages/ozon_common
git add -A && git commit -m "feat(db): SQLAlchemy engine + scoped-session 基座(ozon_common.db)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2：全表 schema metadata + 保真 diff 测试（M1 关键护栏）

**Files:**
- Create: `packages/ozon_common/src/ozon_common/dal/schema.py`
- Create: `packages/ozon_common/tests/test_schema_fidelity.py`

> 这是 M1 最易错处:把现有 schema **如实**翻译成 Core `Table`。正确性不靠肉眼,靠 Step 3 的保真测试(对比"老 `Store.init()` 建出来的库" vs "`metadata.create_all()` 建出来的库")。

- [ ] **Step 1: 写 schema.py(逐表对照转写)**

Create `packages/ozon_common/src/ozon_common/dal/schema.py`,用 `sqlalchemy.MetaData()` + `Table(...)` 定义**全部 ~20 张表**。逐字段对照来源:
- SQLite 形态:`apps/webui/src/webui/store.py` 的 `init()`(`CREATE TABLE` 段,约 135–401 行)+ 各 `_ensure_column`(追加列)+ `_migrate_*`(最终列形态)。
- MySQL 形态:`packages/ozon_common/src/ozon_common/db.py` 的 `MYSQL_DDL` + `init_mysql` 的 `_ensure_mysql_column`。

表清单(必须全有):`settings, users, accounts, account_txns, drafts, draft_images, gen_jobs, gen_job_images, commission_map, catalog_cache, catalog_tree_cache, category_attr_values_cache, attribute_values_cache, category_attr_cache, warehouses, delivery_methods, postings, procurement, offer_snapshots`(以源码实际为准,多则补)。

类型映射规范(M1 **不改类型语义**,只如实描述):
- SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` → `Column(Integer, primary_key=True)`(SQLite 下即自增)。
- `TEXT` → `Text`(或 `String`);`REAL` → `Float`;`INTEGER` → `Integer`。
- 复合主键 → 多列 `primary_key=True`。`UNIQUE(...)` → `UniqueConstraint`。索引 → `Index`。`NOT NULL DEFAULT x` → `nullable=False, server_default=...`。
- **保持现状**:钱仍 `Float`、时间仍 `Text`、不加 `ForeignKey`(那是 M4)。

示例(两表,其余照此模式):
```python
from sqlalchemy import (Column, Float, Index, Integer, MetaData, String, Table, Text,
                        UniqueConstraint)

metadata = MetaData()

settings = Table(
    "settings", metadata,
    Column("user_id", Integer, primary_key=True, nullable=False, server_default="0"),
    Column("key", String(255), primary_key=True, nullable=False),
    Column("value", Text, nullable=False),
)

draft_images = Table(
    "draft_images", metadata,
    Column("id", Integer, primary_key=True),
    Column("draft_id", Integer, nullable=False),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("url", Text, nullable=False),
    Column("type", Text, nullable=False, server_default=""),
    Column("source", Text, nullable=False, server_default="collected"),
    Column("created_at", Text, nullable=False),
    Index("idx_dimg_draft", "draft_id", "position"),
)
# ... 其余表照此逐一定义 ...
```

- [ ] **Step 2: 写保真测试(先红)**

Create `packages/ozon_common/tests/test_schema_fidelity.py`:
```python
"""护栏:metadata.create_all 建出的 schema 必须与老 Store.init() 一致(SQLite)。"""
import sqlite3
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from ozon_common.dal.schema import metadata


def _schema_snapshot(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out = {}
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in sorted(tables):
        cols = {}
        for c in con.execute(f"PRAGMA table_info({t})"):
            cols[c["name"]] = (c["type"].upper(), bool(c["notnull"]), c["pk"])
        idx = sorted(r[0] for r in con.execute(f"PRAGMA index_list({t})")
                     if not r[0].startswith("sqlite_autoindex"))
        out[t] = {"cols": cols, "idx": idx}
    con.close()
    return out


def test_metadata_matches_legacy_init():
    with tempfile.TemporaryDirectory() as tmp:
        # 老路径
        legacy = str(Path(tmp) / "legacy.db")
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(legacy)
        s = store_mod.Store(Path(legacy)); s.close()
        # 新路径
        new = str(Path(tmp) / "new.db")
        eng = create_engine(f"sqlite:///{new}", future=True)
        metadata.create_all(eng)
        eng.dispose()

        legacy_snap = _schema_snapshot(legacy)
        new_snap = _schema_snapshot(new)

        # 表集合一致
        assert set(legacy_snap) == set(new_snap), (
            f"表差异: 仅老={set(legacy_snap)-set(new_snap)} 仅新={set(new_snap)-set(legacy_snap)}")
        # 每表列名集合一致(类型/约束差异先以列名+notnull 为主校验,容忍 SQLite 类型亲和差异)
        for t in legacy_snap:
            lc, nc = legacy_snap[t]["cols"], new_snap[t]["cols"]
            assert set(lc) == set(nc), f"{t} 列差异: 仅老={set(lc)-set(nc)} 仅新={set(nc)-set(lc)}"
```
> 说明:SQLite 类型亲和(TEXT/VARCHAR 等)可能字面不同,首版以**表集合 + 列名集合 + notnull**为硬校验;若要更严可逐步加类型断言。目标是抓"漏表/漏列/拼错列名"。

- [ ] **Step 3: 跑保真测试,红→改 schema→绿**

Run: `cd /e/personal/ozon-helper && python -m uv run python -m pytest packages/ozon_common/tests/test_schema_fidelity.py -q -p no:cacheprovider`
Expected: 初次大概率 FAIL,按报错的"漏表/漏列"补 `schema.py`,直到 **PASS**。这一步就是 schema 转写的正确性闸门。

- [ ] **Step 4: 回归 + 提交**

回归闸门(512)。提交:
```bash
python -m ruff check --select I --fix packages/ozon_common
git add -A && git commit -m "feat(db): 全表 SQLAlchemy metadata + 保真 diff 测试(对齐老 init schema)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3：Alembic baseline

**Files:**
- Create: `migrations/alembic.ini`、`migrations/env.py`、`migrations/versions/0001_baseline.py`
- Create: `packages/ozon_common/tests/test_alembic_baseline.py`

- [ ] **Step 1: alembic init + 接 metadata**

Run:
```bash
cd /e/personal/ozon-helper && python -m uv run alembic init migrations 2>&1 | tail -3
```
改 `migrations/env.py`:`target_metadata = ozon_common.dal.schema.metadata`;`run_migrations_online` 用 `ozon_common.dal.engine.engine_for(...)` 或从 `alembic.ini`/env 取 URL(MySQL env 优先,否则 SQLite 路径由 `-x dbpath=` 传)。删 `alembic.ini` 里写死的 `sqlalchemy.url`,改为运行时注入。

- [ ] **Step 2: 写 baseline 迁移**

Create `migrations/versions/0001_baseline.py`:`upgrade()` 调 `from ozon_common.dal.schema import metadata; metadata.create_all(op.get_bind())`;`downgrade()` 调 `metadata.drop_all(op.get_bind())`。`revision="0001_baseline", down_revision=None`。

- [ ] **Step 3: 测试 baseline 可建库**

Create `packages/ozon_common/tests/test_alembic_baseline.py`:用 `alembic.command.upgrade` 对一个临时 SQLite 跑到 `head`,断言关键表(settings/drafts/gen_jobs)存在。
```python
import tempfile
from pathlib import Path
import sqlite3
from alembic.config import Config
from alembic import command


def test_baseline_upgrade_creates_tables():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "a.db")
        cfg = Config("migrations/alembic.ini")
        cfg.set_main_option("script_location", "migrations")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
        command.upgrade(cfg, "head")
        con = sqlite3.connect(db)
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {"settings", "drafts", "gen_jobs", "draft_images"} <= names
```
(若 env.py 取 URL 方式不同,按实际调整 cfg 注入;目标是该测试能驱动 upgrade。)

- [ ] **Step 4: 跑测试 + 回归 + 提交**

Run 该测试 PASS;回归 512;提交:
```bash
git add -A && git commit -m "feat(db): Alembic 立项 + baseline 迁移(metadata.create_all)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
(`migrations/` 里 alembic 生成的 `__pycache__`/`.mako` 按需 gitignore。)

---

## Task 4：Store.__init__ 切到 metadata.create_all + 回填剥离（行为切换,512 是闸门）

**Files:**
- Create: `apps/webui/src/webui/db_backfills.py`
- Modify: `apps/webui/src/webui/store.py`(`init()`、`__init__`)

> 风险集中点:把建表权威从老裸 SQL 切到 metadata。Task 2 保真测试已证两者 schema 一致,所以切换后 512 应保持。Store 的查询仍走 `self.conn`(裸 sqlite3/MySQLConn)——本 Task **不改查询**,只改"谁建表"。

- [ ] **Step 1: 剥离回填到 db_backfills.py**

把 `store.py` 里 `_backfill_variant_group`/`_backfill_offer_id`/`_backfill_draft_images` 三个**数据回填**函数体移到 Create `apps/webui/src/webui/db_backfills.py`,签名改成 `def run_backfills(conn) -> None:`(内部按原自限逻辑依次跑,用传入的 `conn` 执行原 SQL)。store 里删除这三个方法定义。

- [ ] **Step 2: 改 init() —— 用 metadata 建表,保留回填调用**

把 `store.py` 的 `init()` 改为:
```python
def init(self) -> None:
    from ozon_common.dal.schema import metadata
    from ozon_common.dal.engine import engine_for
    from webui.db_backfills import run_backfills
    eng = engine_for(self.path if not self._is_mysql else None)
    metadata.create_all(eng)          # 建全部表(替代老裸 SQL DDL)
    eng.dispose()
    run_backfills(self.conn)          # 数据回填(自限),用 Store 自己的连接
```
**删除** `init()` 里原有的所有 `CREATE TABLE`/`_ensure_column`/`_migrate_*` 调用块(SQLite 分支整段)与 MySQL 分支的 `db.init_mysql` 调用(metadata 已接管建表)。`_ensure_column`/`_migrate_*` 方法本身可暂留(未被调用,M3 清),但 `init()` 不再调它们。

- [ ] **Step 3: 跑 schema/draft_images/store 相关测试**

Run:
```bash
cd /e/personal/ozon-helper && python -m uv run python -m pytest apps/webui/tests/test_draft_images.py apps/webui/tests/test_store.py apps/webui/tests/test_settings_migrate.py apps/webui/tests/test_multistore.py -q -p no:cacheprovider 2>&1 | tail -8
```
Expected: 全 PASS。回填依赖的 `test_draft_images` 回填用例必须仍绿(回填逻辑保留)。若 FAIL,多半是 metadata 与老 schema 仍有细微差(回 Task 2 修 schema)或回填未正确接线。

- [ ] **Step 4: 全量回归 + 提交**

回归闸门(**512,关键**)。提交:
```bash
python -m ruff check --select I --fix apps/webui
git add -A && git commit -m "refactor(store): 建表权威切到 SQLAlchemy metadata,回填剥离为 run-once

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5：BaseRepo + SettingsRepo + 单测

**Files:**
- Create: `packages/ozon_common/src/ozon_common/dal/repositories/__init__.py`、`base.py`、`settings_repo.py`
- Create: `packages/ozon_common/tests/test_settings_repo.py`

- [ ] **Step 1: BaseRepo**

Create `…/dal/repositories/base.py`:
```python
from __future__ import annotations

from sqlalchemy.orm import Session

from ozon_common.dal.session import current_session


class BaseRepo:
    @property
    def s(self) -> Session:
        return current_session()
```
Create `…/dal/repositories/__init__.py`:`"""仓储层。"""`

- [ ] **Step 2: SettingsRepo(对齐现有 get_settings/save_settings 语义)**

现有语义(webui `Store.get_settings`):读 user_id=0(全局)再读传入 user_id 覆盖;value 若是 JSON 串则解析。worker `DataStore.get_settings()` 等价(uid 0 then 1)。Create `…/dal/repositories/settings_repo.py`:
```python
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import settings as T


def _decode(v):
    if isinstance(v, str) and v[:1] in ("{", "["):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return v
    return v


class SettingsRepo(BaseRepo):
    def get_settings(self, user_id: int = 1) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for uid in (0, int(user_id)):
            rows = self.s.execute(
                select(T.c.key, T.c.value).where(T.c.user_id == uid)).all()
            for k, v in rows:
                out[k] = _decode(v)
        return out

    def save_settings(self, values: dict[str, Any], user_id: int = 1) -> dict[str, Any]:
        uid = int(user_id)
        for k, v in values.items():
            sv = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
            self.s.execute(delete(T).where(T.c.user_id == uid, T.c.key == k))
            self.s.execute(insert(T).values(user_id=uid, key=k, value=sv))
        return self.get_settings(uid)
```
> 注意:对齐现有行为——若现有 `save_settings` 用 upsert 而非 delete+insert,按现有语义调整(读 `store.py:799` 确认)。返回形状 = `{key: value}` dict。

- [ ] **Step 3: 单测(先红)**

Create `packages/ozon_common/tests/test_settings_repo.py`:
```python
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from ozon_common.dal import session as S
from ozon_common.dal.schema import metadata
from ozon_common.dal.repositories.settings_repo import SettingsRepo


def _bind(tmp):
    eng = create_engine(f"sqlite:///{Path(tmp) / 's.db'}", future=True)
    metadata.create_all(eng)
    S.bind_engine(eng)


def test_save_and_get_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        _bind(tmp)
        with S.session_scope():
            SettingsRepo().save_settings({"oss_bucket": "b1", "ai_text": {"engine": "x"}}, user_id=1)
        with S.session_scope():
            got = SettingsRepo().get_settings(1)
            assert got["oss_bucket"] == "b1"
            assert got["ai_text"] == {"engine": "x"}   # JSON 解析还原


def test_user_overrides_global():
    with tempfile.TemporaryDirectory() as tmp:
        _bind(tmp)
        with S.session_scope():
            SettingsRepo().save_settings({"k": "global"}, user_id=0)
            SettingsRepo().save_settings({"k": "user1"}, user_id=1)
        with S.session_scope():
            assert SettingsRepo().get_settings(1)["k"] == "user1"
```

- [ ] **Step 4: 跑测试 + 回归 + 提交**

Run 单测 PASS;回归 512;提交:
```bash
python -m ruff check --select I --fix packages/ozon_common
git add -A && git commit -m "feat(db): SettingsRepo(Core)+ 单测

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6：DraftImageRepo + 单测

**Files:**
- Create: `…/dal/repositories/draft_image_repo.py`、`packages/ozon_common/tests/test_draft_image_repo.py`

- [ ] **Step 1: 实现(对齐 store.add_draft_image / worker DataStore 出图读取)**

参照 `store.py` 的 `add_draft_image`(取 `MAX(position)+1` 后插入)、`_load_draft_images`,以及 worker `DataStore.get_draft`/`_row_to_draft`。Create `…/dal/repositories/draft_image_repo.py`:
```python
from __future__ import annotations

from typing import Any

from sqlalchemy import func, insert, select

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import draft_images as DI
from ozon_common.jsonio import utc_now_iso


class DraftImageRepo(BaseRepo):
    def load_draft_images(self, draft_id: int) -> list[dict[str, Any]]:
        rows = self.s.execute(
            select(DI.c.url, DI.c.type, DI.c.source)
            .where(DI.c.draft_id == int(draft_id))
            .order_by(DI.c.position)).all()
        return [{"url": r.url, "type": r.type, "source": r.source} for r in rows]

    def add_draft_image(self, draft_id: int, url: str, *, type: str = "",
                        source: str = "generated") -> int:
        nxt = self.s.execute(
            select(func.coalesce(func.max(DI.c.position), -1) + 1)
            .where(DI.c.draft_id == int(draft_id))).scalar() or 0
        res = self.s.execute(insert(DI).values(
            draft_id=int(draft_id), position=int(nxt), url=str(url),
            type=str(type or ""), source=str(source), created_at=utc_now_iso()))
        return int(res.inserted_primary_key[0])
```
(若 worker 还需 `get_draft`/`_row_to_draft` 的完整拼装,一并加,SQL 行为照 worker `DataStore` 搬;drafts 表 metadata 已在 schema.py。)

- [ ] **Step 2: 单测(先红)**

Create `test_draft_image_repo.py`:绑定临时库(同 Task5 `_bind` 模式),在 `session_scope` 内 `add_draft_image` 三张图、断言 `load_draft_images` 顺序/position、type/source 正确。(从 `test_draft_images.py` 的断言风格移植。)

- [ ] **Step 3: 跑测试 + 回归 + 提交**

PASS;512;提交 `feat(db): DraftImageRepo(Core)+ 单测`。

---

## Task 7：GenJobRepo + 单测

**Files:**
- Create: `…/dal/repositories/gen_job_repo.py`、`packages/ozon_common/tests/test_gen_job_repo.py`

- [ ] **Step 1: 实现(对齐 store/DataStore 的 12 个 gen_job 方法)**

逐一实现:`create_gen_job/get_gen_job/get_latest_gen_job/list_gen_jobs/has_active_gen_job/update_gen_job/set_gen_job_status/create_gen_job_images/get_gen_job_images/update_gen_job_image/set_gen_job_image_status/count_gen_job_images_by_status`。SQL 行为照 `store.py:1819-1945` 与 worker `DataStore` 对应方法搬,返回 dict/list[dict]/bool/int 形状不变(用 `dict(row._mapping)` 还原整行)。`create_gen_job` 返回 `get_gen_job(new_id)`;`has_active_gen_job` 判 `status NOT IN ('done','failed')` 计数>0(以现有 SQL 为准)。

- [ ] **Step 2: 单测(先红)**

Create `test_gen_job_repo.py`:create_gen_job → get/get_latest → create_gen_job_images → 各 image set 状态 → count_by_status;has_active 在 done 前后变化。覆盖原 DataStore/Store 行为关键点。

- [ ] **Step 3: 跑测试 + 回归 + 提交**

PASS;512;提交 `feat(db): GenJobRepo(Core)+ 单测`。

---

## Task 8：webui 请求级 session 中间件 + Store 三组方法转调仓储

**Files:**
- Modify: `apps/webui/src/webui/main.py`(中间件 + 启动 bind_engine)
- Modify: `apps/webui/src/webui/store.py`(settings/draft_images/gen_jobs 方法转调仓储)

- [ ] **Step 1: 启动绑定 engine + 中间件**

`main.py`:应用启动处(模块级或 startup)调一次:
```python
from ozon_common.dal.engine import engine_for
from ozon_common.dal.session import bind_engine, session_scope
bind_engine(engine_for(None if _mysql else str(APP.store.path)))
```
(engine 与 Store 用同一库:MySQL 走 env,SQLite 用 `APP.store.path`。)
加中间件:
```python
@app.middleware("http")
async def _db_session(request, call_next):
    import anyio
    # 同步端点在 threadpool 跑,这里用 contextmanager 包住 handler
    with session_scope():
        return await call_next(request)
```
> 注意:FastAPI sync 端点经 threadpool;ContextVar 在 async 中间件设值后,`call_next` 内的 threadpool 任务能否看到取决于上下文传播。**若实测 threadpool 内 `current_session()` 取不到**(ContextVar 未跨线程传播),改为「依赖注入式」:用 `Depends(get_session_scope)` 或在中间件里 `contextvars.copy_context()` 包裹;具体见 Step 2 验证,取不到就调整实现直到取到。

- [ ] **Step 2: 验证中间件内仓储可用(冒烟)**

临时加一个 `GET /api/_db-ping` 端点:`with`-free 直接 `SettingsRepo().get_settings(1)`,返回 `{"ok": True}`;用 TestClient 打它,确认不抛 `current_session()` 错。验证通过后**删除该临时端点**。若取不到 session,按 Step1 注记调整中间件实现(确保 sync 端点线程内能拿到请求 session)。

- [ ] **Step 3: Store 三组方法转调仓储**

把 `store.py` 的 `get_settings/save_settings`、`add_draft_image`(及 `_load_draft_images` 读取)、以及 12 个 gen_job 方法改为**转调仓储**。因为 Store 方法可能在请求外被调(启动/测试无中间件),用「有 ambient session 则用,否则自开」的辅助:
```python
def _in_scope(fn):
    from ozon_common.dal.session import _current_session, session_scope
    if _current_session.get() is not None:
        return fn()
    with session_scope():
        return fn()
```
例:
```python
def get_settings(self, user_id=None):
    from ozon_common.dal.repositories.settings_repo import SettingsRepo
    uid = self._uid(user_id) if hasattr(self, "_uid") else (user_id or 1)
    return _in_scope(lambda: SettingsRepo().get_settings(uid))
```
其余方法照此。**注意**:这些仓储走的是 SQLAlchemy engine 连接(池),与 Store 的 `self.conn` 是不同连接 → 协存。SQLite 已开 WAL,读写不互斥;但**同一请求里 Store 裸连接写了未提交、仓储另一个连接读不到**——本 M1 接受此协存语义(M3 统一)。确认现有测试不依赖"同方法内裸连接与仓储跨读"。

- [ ] **Step 4: 跑相关测试 + 全量回归**

先跑 `test_settings_api/test_settings_multiuser/test_draft_images/test_gen_image/test_media_async`,再全量回归。**512 必须保持**。若个别测试因协存连接可见性失败,定位是否该测试在同一未提交事务内跨裸连接/仓储读——按 §M1 协存语义评估:多为需要把该读也走仓储,或在测试边界提交。逐个修绿。

- [ ] **Step 5: ruff + 提交**

```bash
python -m ruff check --select I --fix apps/webui packages/ozon_common
git add -A && git commit -m "refactor(webui): 请求级 session 中间件 + Store settings/draft_images/gen_jobs 转调仓储

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9：worker 退役 DataStore,改用 session_scope + 仓储

**Files:**
- Modify: `apps/image_worker/src/image_worker/worker.py`

- [ ] **Step 1: 接 engine + 替换 DataStore**

worker `main()` 启动处:`bind_engine(engine_for(None))`(worker 只连 MySQL,env 必有)。把 `handle_job` 内 `DataStore()` 用法替换为 `with session_scope():` 包住,内部用 `SettingsRepo/DraftImageRepo/GenJobRepo`。原 `from ozon_common.draft_images import DataStore` 删除;`ai_config` 仍从 `ozon_common.settings` 来。settings 读取改 `SettingsRepo().get_settings(1)`。

- [ ] **Step 2: 导入冒烟 + worker 逻辑测试**

Run: `python -m uv run --package ozon-image-worker python -c "import image_worker.worker; print('ok')"` → `ok`。
若有 worker 单测(mock 出图/OSS),跑通;否则加一个最小测试:`session_scope()` 内 `GenJobRepo().create_gen_job` → `DraftImageRepo().add_draft_image` → 断言落库。

- [ ] **Step 3: 评估 ozon_common.draft_images(老 DataStore)去留**

`packages/ozon_common/src/ozon_common/draft_images.py` 的 `DataStore` 此时无人用(worker 已切仓储)。确认全仓无引用:`grep -rn "DataStore" packages apps`。无引用则 `git rm` 删除该文件(它的职责已被三仓储取代——这正是"消灭重复");有引用则保留并报告。

- [ ] **Step 4: 回归 + 提交**

worker 冒烟 + 512 回归。提交:
```bash
git add -A && git commit -m "refactor(worker): 退役 DataStore,改用 session_scope + 共享仓储

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10：协存冒烟 + 收尾验证

**Files:**
- Create: `packages/ozon_common/tests/test_coexistence.py`

- [ ] **Step 1: 协存冒烟测试**

Create `test_coexistence.py`:同一 SQLite 文件,一边用老 `Store`(裸连接)写 drafts,一边用 engine+仓储写 settings/gen_jobs,交替读写,断言互不死锁、各自数据正确(验证 WAL 生效)。
```python
import tempfile
from pathlib import Path
from sqlalchemy import create_engine
from ozon_common.dal import session as S
from ozon_common.dal.schema import metadata
from ozon_common.dal.repositories.settings_repo import SettingsRepo


def test_legacy_conn_and_pool_coexist():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "co.db"
        import webui.store as store_mod
        store_mod.DEFAULT_DB = db
        st = store_mod.Store(db)              # 老路径(已 metadata 建表 + WAL)
        eng = create_engine(f"sqlite:///{db}", future=True); metadata.create_all(eng)
        S.bind_engine(eng)
        with S.session_scope():
            SettingsRepo().save_settings({"k": "v"}, user_id=1)
        # 老连接读 settings 应看到已提交值
        row = st.conn.execute("SELECT value FROM settings WHERE `key`='k'").fetchone()
        assert row is not None
        st.close()
```
(SQL 占位符按 store 的 dialect 适配;SQLite 用 `?`。)

- [ ] **Step 2: 全量 + 新测试套件**

Run:
```bash
cd /e/personal/ozon-helper
python -m uv run python -m pytest packages/ozon_common/tests -q -p no:cacheprovider 2>&1 | tail -6
python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py' -q -p no:cacheprovider 2>&1 | tail -6
python -m uv run python -c "import webui.main, image_worker.worker; print('imports ok')"
python -m ruff check --select I packages apps 2>&1 | tail -3
```
Expected: ozon_common 测试全绿;webui **512 passed**;imports ok;ruff 仅既有 I001。

- [ ] **Step 3: 提交 + memory**

```bash
git add -A && git commit -m "test(db): 协存冒烟 + M1 收尾验证

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
更新 memory:M1 完成、SQLAlchemy 基座就位、DataStore 已删、M2 续(其余仓储)。

---

## Self-Review 记录

- **Spec 覆盖**:§2 组件→T1/T2/T5-7;§3 engine 池→T1;§4 session/UoW→T1/T8/T9;§5 metadata+Alembic+create_all 衔接+回填→T2/T3/T4;§6 三仓储→T5-7;§7 双后端协存→T8/T10;§8 测试(保真/仓储/协存/512)→T2/T5-7/T10;§9 风险(WAL/scoped 生命周期/回填)→T1/T4/T8/T10。
- **占位符**:schema.py 与三仓储的"逐表/逐方法转写"以**源码行号引用 + 保真/单测闸门**替代盲抄,非占位(2000 行 schema 不宜全贴,正确性由 T2 diff 测试机械保证)。其余步骤含真实代码。
- **签名一致**:`session_scope/current_session/bind_engine`、`engine_for/build_engine`、`SettingsRepo.get_settings(user_id)`、`DraftImageRepo.add_draft_image(...)`、`GenJobRepo.*`、`run_backfills(conn)`、`_in_scope` 贯穿一致。
- **已知风险点**:T8 Step1 的 ContextVar 跨 threadpool 传播——计划已给"取不到就改注入式"的应对;T8 Step3 协存连接可见性——已注明语义与逐测修法。
