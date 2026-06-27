# 数据访问层 M2：其余聚合迁仓储 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** 把 M1 未迁的 ~17 张表按聚合迁成 SQLAlchemy Core 仓储,webui `Store` 对应方法逐个转调,绞杀掉 `Store` 的裸 SQL,为 M3 退役 `db.py`/`translate()`/全局锁铺路。全程 545 测试不下降。

**Architecture:** 沿用 M1 已验证的模式——每个聚合一个 Repo(`ozon_common/dal/repositories/`,基于 Core,返回 dict 形状不变),`Store` 方法经 `_in_scope` 转调。M1 已建好 engine/session/schema(全表 metadata 已就位,M2 不改 schema)。本里程碑**不改 schema 类型/约束**(M4)、**不删 db.py/translate**(M3)、**不优化 N+1/分页**(M5,DraftRepo 照搬现有行为含 N+1)。

**Tech Stack:** SQLAlchemy 2.x Core、pytest、uv workspace。

**全局约定:**
- 仓库根 `E:\personal\ozon-helper`;分支 `feat/auto-listing-ai-pipeline`;**`uv` 用 `python -m uv`**;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- **回归闸门**:每 Task 末尾 `python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py' -q -p no:cacheprovider`,**≥ 545 passed**(随新增仓储单测上升)。
- Windows SQLite 临时库测试:`try/finally: eng.dispose()` + `ignore_cleanup_errors=True`(参照 `packages/ozon_common/tests/test_settings_repo.py`)。

---

## 每个 Repo Task 的统一模板(M1 已验证)

每个聚合一个 Task,subagent 照此做:
1. **读源**:读 `apps/webui/src/webui/store.py` 里该聚合的方法(给定行号区间),记下每个方法的 SQL 语义、参数、返回形状(dict/list[dict]/标量)。必要时对照 `db.py` MYSQL_DDL 确认列。
2. **建 Repo**:`packages/ozon_common/src/ozon_common/dal/repositories/<name>_repo.py`,继承 `BaseRepo`(`self.s` = current_session),用 Core `select/insert/update/delete` 逐方法实现,**返回形状与 Store 完全一致**(`dict(row._mapping)` 还原整行)。`utc_now_iso`/`loads_json`/`dumps_json` 从 `ozon_common.jsonio`。
3. **单测**:`packages/ozon_common/tests/test_<name>_repo.py`,绑临时 SQLite(`metadata.create_all` + `bind_engine`,`session_scope` 内调),覆盖该聚合关键 CRUD + 边界,移植 store 现有测试的断言。
4. **转调**:把 `store.py` 里该聚合方法体改为 `_in_scope(lambda: <Repo>().<m>(...))`,删原裸 SQL + `with self.lock`,签名/返回不变。`_in_scope` 已在 store.py(M1 加的)。
5. **闸门**:跑该聚合相关 webui 测试 + 全量回归(≥545),全绿。ruff `--select I --fix`(只带本 Task 文件)。提交 `feat(dal): <Name>Repo(Core)+ 转调 Store`。

**通用约束**:不改 schema、不改 db.py、不改 worker、不动 M1 已迁的 settings/gen_job/draft_image、不优化 N+1(照搬现有 SQL 行为)。parity 第一(行为不变,545 兜底)。遇结构性难点报 BLOCKED。

---

## Repo 清单与顺序(易→难,各一个 Task)

> 方法行号以当前 `store.py` 为准(M1 后已变动,subagent 以实际 grep 定位 `def <方法名>` 为准,下表行号仅参考)。

### Task 1：OfferSnapshotRepo(最简,先验证模板在 M2 仍成立)
- 表:`offer_snapshots`。方法:`add_offer_snapshot`、`latest_offer_snapshot`、`list_offer_snapshots`。
- 注意:`offer_snapshots` 有 `store_client_id` 列(按店过滤),list 方法可能带该过滤,照搬。

### Task 2：CatalogCacheRepo(缓存表,纯 save/load)
- 表:`catalog_cache`、`catalog_tree_cache`、`category_attr_cache`、`category_attr_values_cache`、`attribute_values_cache`。
- 方法:`save_catalog_leaves`/`load_catalog_leaves`、`save_catalog_tree`/`load_catalog_tree`、`save_category_attrs`/`load_category_attrs`、`save_attr_values`/`load_attr_values`、`save_attribute_values`/`find_attribute_values`。
- 注意:多为 upsert(`INSERT ... ON CONFLICT DO UPDATE`)+ 复合主键(含 language);`find_attribute_values` 走 `idx_av_cache`;`oversized` 列。照搬 SQL 语义。

### Task 3：CommissionRepo
- 方法:`save_commission_map`/`load_commission_map`、`get_realfbs_routes`/`set_realfbs_routes`、`get_commission_categories`/`set_commission_categories`。
- **先确认存储位置**:`commission_map` 是表;`realfbs_routes`/`commission_categories` 可能存在 `commission_map` 或别的表或 settings——subagent 读 store 实现确认每个方法读写哪张表(schema.py 里有的表才有对应 Table;若发现某方法其实读写 settings 或没有对应表,报告 NEEDS_CONTEXT)。

### Task 4：UserRepo
- 表:`users`。方法:`create_user`、`get_user_by_username`、`get_user_by_id`、`count_users`、`list_users`、`set_max_stores`、`set_status`、`set_password_hash`、`delete_user`。
- 注意:`password_hash` 原样存取(不碰认证逻辑);`role`/`status`/`max_stores` 默认值。

### Task 5：WalletRepo
- 表:`accounts`、`account_txns`。方法:`get_account`、`recharge`、`deduct`、`refund`、`list_txns`。
- **注意 parity 关键**:钱相关方法有事务语义(账户余额 + 流水一致)。M1 起这些走 session——`_in_scope` 单次 session 内 recharge/deduct 的「改余额 + 写流水」要在**同一 session**里(一个 `_in_scope` 调用内完成,session_scope 结束才 commit),保证原子。**钱仍 Float(M4 才改 Numeric),本 Task 不动类型。** 移植 `test_wallet.py` 断言。

### Task 6：WarehouseRepo
- 表:`warehouses`、`delivery_methods`。方法:`upsert_warehouses`、`list_warehouses`、`set_default_warehouse`、`replace_delivery_methods`、`list_delivery_methods`。
- 注意:`replace_delivery_methods` 是「全删该店再批量插」(store_client_id 维度),照搬;delivery_methods 列多(自提点等)。

### Task 7：OrderRepo
- 表:`postings`、`procurement`。方法:`upsert_postings`、`list_postings`、`get_posting`、`rebuild_procurement`、`list_procurement`、`set_procurement_state`。
- 注意:`rebuild_procurement` 从 postings 重建采购行(按 store_client_id);`procurement` 有 `UNIQUE(posting_number, offer_id)`。移植 `test_store_fulfillment.py`/`test_ship.py` 相关断言。

### Task 8：DraftRepo(最大最后,含 M1 留下的热读路径)
- 表:`drafts`、`draft_images`(把 M1 留在裸连接的草稿读也迁过来)。方法(~15):`insert_draft`、`update_draft`、`get_draft`、`list_drafts`、`list_drafts_page`、`count_by_status`、`find_by_source_url`、`find_by_offer_id`、`set_ai_proposal`、`delete_draft`、`set_media_status`、`apply_media_oss`、`list_pending_media_drafts`、`list_drafts_by_variant_group`、`_load_draft_images`、`_sync_draft_images`、`_row_to_draft`(+ M1 已迁的 `add_draft_image` 并入本 Repo)。
- **N+1 照旧**:`_row_to_draft` 仍逐行查 draft_images(N+1 不在 M2 修,M5 才用批量),**行为完全照搬**。
- **draft_images 写**:`_sync_draft_images`(insert/update 时同步图行)照搬。
- 这是最大的转调,subagent 要特别小心 parity;`list_drafts_page` 的分组/分页逻辑、`_migrate_*`/`_backfill_*` 不在此(已在 db_backfills);移植 `test_drafts.py`/`test_pagination.py`/`test_draft_images.py`/`test_publish_group.py`/`test_variant_publish.py`/`test_store_scoped_drafts.py` 全过。
- 完成后 webui `Store` 的草稿访问全部走仓储;为 M3 删 translate/裸连接做好准备。

---

## 收尾(Task 9)：M2 验证 + db.py 消费者盘点

- [ ] 全量回归(≥545+各仓储新测试)、`packages/ozon_common/tests` 全绿、三包 import 冒烟。
- [ ] 盘点 `Store` 还剩哪些方法走裸 `self.conn`(理论上 M2 后应几乎清空,只剩 `__init__`/`close`/`init` 的连接管理)+ `grep -rn "from ozon_common import db\|self.conn\|translate" apps/webui` 列出 M3 要清的残留,写进 memory 给 M3。
- [ ] 提交 `test(dal): M2 收尾验证 + M3 残留盘点`,更新 memory。

---

## Self-Review 记录

- **覆盖**:M1 的 8 个未迁聚合 → Task 1-8 各一;收尾 → Task 9。模板覆盖 spec 的「Store 方法逐个转调、parity、545 闸门」。
- **占位符**:每 Task 给定表/方法清单 + 模板,精确 SQL 转写由 subagent 读 store.py 现有实现完成(与 M1 同法,行为由移植的现有测试 + 545 兜底)——非占位,是「读源照搬」的明确指令。
- **风险点**:Task 3(realfbs/commission_categories 存储位置存疑→NEEDS_CONTEXT)、Task 5(钱的事务原子性,同 session)、Task 8(最大转调 + N+1 照旧)已分别标注。
- **顺序**:易→难,DraftRepo 最后(最多调用方、最大 parity 面)。
