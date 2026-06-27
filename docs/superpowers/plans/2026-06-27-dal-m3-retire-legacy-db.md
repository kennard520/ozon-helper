# 数据访问层 M3：退役老 db.py / translate / 全局锁 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps 用 checkbox。

**Goal:** 绞杀收口——删除 Store 的死迁移代码、把回填与 analytics_report 迁到 SQLAlchemy、移除 `Store.self.conn`/`self.lock`,最终**整个删除 `ozon_common/db.py`**(手写 `translate()`/`MySQLConn`/`make_mysql_conn`/`init_mysql`/`MYSQL_DDL`/全局锁体系)。全程 641 测试不下降。

**Architecture:** M1/M2 已把所有数据访问迁到 SQLAlchemy 仓储 + 请求级 session;Store 仅剩连接管理 + 死迁移代码 + 回填仍用裸 `self.conn`。M3 把最后这点裸连接也清掉,老 db.py 零消费者后删除。MySQL 连接走 `dal/engine.py`(`mysql+pymysql` 池),不再用手写 MySQLConn。

**Tech Stack:** SQLAlchemy 2.x Core、pytest、uv workspace。

**全局约定:** 仓库根 `E:\personal\ozon-helper`;分支 `feat/auto-listing-ai-pipeline`;**`uv` 用 `python -m uv`**;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
**回归闸门**:每 Task 末 `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider`,**必须 641 passed**(webui 513 + ozon_common 128)。ruff 只带本 Task 文件。

**⚠️ 测试盲区(贯穿 M3)**:测试全跑 SQLite。本里程碑删的 `translate`/`MySQLConn` 是 **MySQL 部署路径**;641 绿**不能**证明 MySQL 生产无恙。**M3 完成后必须在真实 MySQL 环境人工验证**(起 webui + worker,跑关键流程:登录/列草稿/出图/发布)。每个删除 Task 的报告都要重申这一点。

---

## M3 残留盘点(已盘好,直接照做)
- Store 剩 41 处裸 `self.conn.execute` **全在死代码**:`_ensure_column` + `_migrate_attribute_values_cache_language`/`_migrate_category_attr_cache_language`/`_migrate_drafts_multiuser`/`_migrate_drafts_store_scoped`/`_migrate_settings_multiuser`/`_migrate_store_scoped_aux`(init 已不调)。
- `self.conn` 唯一**活**引用:`init()` 里 `run_backfills(self.conn)`(+ `close()` 的 `self.conn.close()`)。
- `db.py` 消费者:`store.py:14`(`db.mysql_enabled()`/`db.make_mysql_conn()`)、`analytics_report.py`(`db.mysql_enabled()`/`db.load_raw_settings()`)。
- `dal/engine.py` 不依赖 db.py(自带 `mysql_url_from_env`)。

---

## Task 1：删 Store 死迁移代码（_ensure_column / _migrate_*）
**Files:** Modify `apps/webui/src/webui/store.py`
- [ ] **Step 1**:确认这些方法已无任何调用方:`grep -nE "self\._ensure_column|self\._migrate_" apps/webui/src/webui/store.py | grep -v "def "` → **应只剩定义、无调用**(init 已不调)。若有调用,停下报告。
- [ ] **Step 2**:删除这 7 个方法定义:`_ensure_column`、`_migrate_attribute_values_cache_language`、`_migrate_category_attr_cache_language`、`_migrate_drafts_multiuser`、`_migrate_drafts_store_scoped`、`_migrate_settings_multiuser`、`_migrate_store_scoped_aux`(整段删)。删后 `grep -c "self.conn.execute" store.py` 应骤降到只剩 backfill/close 相关(理论 0,因为 backfill 在 db_backfills.py)。
- [ ] **Step 3**:回归 641。提交 `refactor(store): 删退役的 _ensure_column/_migrate_* 死迁移代码`。

## Task 2：回填迁到 SQLAlchemy engine（解开 self.conn 的最后活引用）
**Files:** Modify `apps/webui/src/webui/db_backfills.py`、`apps/webui/src/webui/store.py`(init)
- [ ] **Step 1**:读 `db_backfills.py` 的 `run_backfills(conn)` + 3 个 `_backfill_*(conn)`(用裸 `conn.execute` + `?` 占位)。
- [ ] **Step 2**:改 `run_backfills` 用 SQLAlchemy:签名改 `run_backfills(engine)`,内部 `with engine.begin() as conn:` 用 `conn.execute(text(sql), params)`(SQLAlchemy text + 命名参数,或用 Core 对 schema 表操作)。三个回填 SQL 逐句迁(SELECT/UPDATE/INSERT 照搬语义,占位符改 SQLAlchemy 风格)。**自限逻辑不变**。
- [ ] **Step 3**:改 `store.py` 的 `init()`:`run_backfills(self.conn)` → `run_backfills(eng)`(复用 init 里已建的 `eng = engine_for(...)`,在 `eng.dispose()` 之前调)。
- [ ] **Step 4**:回归 641(**`test_draft_images.py` 的回填用例是关键**,它覆盖 draft_images 回填)。`packages/ozon_common/tests` 全绿。提交 `refactor(backfills): 回填改用 SQLAlchemy engine,解开 Store.self.conn`。

## Task 3：移除 Store.self.conn / self.lock / 老连接创建
**Files:** Modify `apps/webui/src/webui/store.py`
- [ ] **Step 1**:确认 self.conn 已无活引用:`grep -nE "self\.conn" apps/webui/src/webui/store.py` → Task1/2 后应只剩 `__init__` 创建 + `close()`。`grep -nE "self\.lock" store.py` → 应只剩 `__init__` 定义(方法都转调仓储了,不再 `with self.lock`)。若仍有活引用,停下报告。
- [ ] **Step 2**:改 `Store.__init__`:
  - 删 `self.lock = threading.RLock()`(若 threading 仅此用,删 import)。
  - 判定 MySQL 改用 dal:`from ozon_common.dal.engine import mysql_url_from_env`;`self._is_mysql = bool(mysql_url_from_env())`;`self.path = None if self._is_mysql else Path(path or DEFAULT_DB)`(保留 path 给 engine_for/测试)。
  - 删 `self.conn = db.make_mysql_conn()` / `sqlite3.connect(...)` / `row_factory` 整段——**Store 不再持有裸连接**。
  - `init()` 仍 `bind_engine(engine_for(...))` + `metadata.create_all` + `run_backfills(eng)`。
  - `close()`:删 `self.conn.close()`;改为 dispose engine(若 init 里 eng 是局部的,close 可空操作或 dispose 全局 engine——保持测试能清理 SQLite 文件:沿用 M1 在 close 里 `engine.dispose()` 的做法,确认临时库可删)。
- [ ] **Step 3**:删 `store.py:14 from ozon_common import db`(若 db 已无其它用)。`grep -n "\bdb\." store.py` 确认无 `db.xxx` 残留。
- [ ] **Step 4**:回归 641(尤其 Windows 临时库清理不报 WinError)。提交 `refactor(store): 移除 self.conn/self.lock,连接统一走 dal engine`。

## Task 4：analytics_report 迁到 dal
**Files:** Modify `apps/webui/src/webui/analytics_report.py`
- [ ] **Step 1**:读 `_load_settings_raw()`——它 `db.mysql_enabled()` 时 `db.load_raw_settings()`,否则裸 `sqlite3.connect(DB).execute("SELECT key,value FROM settings")`。目的:拿 admin 凭证设置({key:value_raw})。
- [ ] **Step 2**:改为走 dal:`bind_engine(engine_for(None if mysql_url_from_env() else str(DB)))` + `with session_scope(): SettingsRepo().get_settings(...)`——但注意原是 `value_raw`(不 JSON 解析,后面自己 `json.loads` 试),而 `SettingsRepo.get_settings` 会 decode。**为 parity**:可在 analytics 里直接用 dal engine 跑一条 `SELECT key,value FROM settings WHERE user_id=0`(用 Core/text),拿原始 value,保持后续 `g()` 的解析逻辑不变。**不引入对 db.py 的依赖**。
- [ ] **Step 3**:确认 analytics_report 无 `from ozon_common import db`。回归 641(注:analytics_report 是 CLI,可能无单测覆盖——若无,做一次 `python -m uv run python -c "import webui.analytics_report"` import 冒烟 + 人工核对逻辑等价,并在报告里标注「无自动化覆盖」)。提交 `refactor(analytics): settings 读取改 dal,脱离 db.py`。

## Task 5：删除 db.py + 收尾
**Files:** Delete `packages/ozon_common/src/ozon_common/db.py`;Modify 相关 import
- [ ] **Step 1**:全仓确认 db.py 零消费者:`grep -rn "from ozon_common import db\|ozon_common\.db\b\|import ozon_common.db\|from ozon_common.db import" apps packages --include=*.py | grep -v "ozon_common.dal"` → **应为空**。非空则先迁那些引用。
- [ ] **Step 2**:`git rm packages/ozon_common/src/ozon_common/db.py`。
- [ ] **Step 3**:回归 641 + 三包 import 冒烟(`python -m uv run python -c "import webui.main, image_worker.worker, ozon_api.client; print('ok')"`)。`grep -rn "translate\|MySQLConn" packages/ozon_common --include=*.py` 应无残留。
- [ ] **Step 4**:提交 `refactor(common): 删除 db.py(translate/MySQLConn 退役,绞杀者收口)`。更新 memory:M3 完成、db.py 已删、**强调 MySQL 部署需人工验证**。

---

## Self-Review
- 覆盖盘点的 4 类残留:死代码(T1)、回填(T2)、Store 连接(T3)、analytics(T4)、db.py 删除(T5)。
- 占位符:无;各 Task 给精确文件/方法/grep 验证。
- 顺序依赖:T2(解开 self.conn 活引用)必须在 T3(删 self.conn)前;T1-T4(清消费者)必须在 T5(删 db.py)前。
- 风险:MySQL 部署测试盲区(全程标注,M3 后人工验);回填迁 SQLAlchemy(test_draft_images 兜底);analytics 无自动覆盖(import 冒烟 + 人工核)。
