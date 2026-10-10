# DAL M4 上线前 MySQL 集成验证清单

> M1–M4 的所有自动化测试都跑 **SQLite**。M4 的 Alembic 迁移 `0002`–`0005`(索引/钱 DECIMAL/时间 DATETIME/外键)以及其中的**数据转换**只在 SQLite 路径(多为 no-op)走过,**MySQL 生产路径未经测试覆盖**。**M4 上线前必须在真实 MySQL(测试库/staging,拿一份生产数据副本)走完本清单。** 出错则不要上线。

## 0. 前置
- 在测试 MySQL 上恢复一份**生产数据副本**(或结构+代表性数据)。
- 部署该 commit 的代码(含 `migrations/versions/0002`–`0005`)。
- 设好 `OZON_MYSQL_*` 环境变量指向该测试库。

## 1. 迁移演练(核心)
```bash
# 现网已 stamp 0001_baseline → 跑增量到 head
python -m uv run alembic upgrade head
```
逐项确认(无报错 + 数据正确):

### 1.1 — 0002 索引
- `SHOW INDEX FROM drafts;` 含 `idx_drafts_offer_id` / `idx_drafts_user_status` / `idx_drafts_ozon_pid` / `idx_drafts_media_status`。
- 0002 用了 `inspect.get_indexes` 幂等检测——确认 MySQL 上不重复建/不报错。

### 1.2 — 0003 钱 DECIMAL
- `DESCRIBE accounts;` 等:9 列(accounts.balance/total_recharge/total_consume、account_txns.amount/balance_after、drafts.cost_cny、offer_snapshots.price_min/price_max、procurement.cost_cny)类型为 `decimal(18,4)`。
- **数据无损**:迁移前后抽样几条账户余额/流水金额,值不变(浮点→DECIMAL 应无损;留意极端浮点尾差)。
- `delivery_methods.dropoff_lat/lng` 仍是 `double`(未误改)。

### 1.3 — 0004 时间 DATETIME(最易错)
- `DESCRIBE drafts;` 等:22 个时间列(created_at/updated_at/fetched_at/synced_at/captured_at)类型为 `datetime(6)`。
- **数据转换正确**(`STR_TO_DATE(REPLACE(SUBSTRING_INDEX(col,'+',1),'T',' '), ...)`):抽样几条 created_at,迁移前的 ISO 文本(如 `2026-06-27T02:32:14.888745+00:00`)→ 迁移后 `2026-06-27 02:32:14.888745`(UTC、保微秒)。**重点核对没有 NULL 化正常值、没有时区错位**。
- 空串原值应变成 NULL(迁移里有 `SET col=NULL WHERE col=''`)。

### 1.4 — 0005 外键 + 孤儿清理
- 跑迁移时**看 stdout 的 `[0005_fk] {child}.{key} 孤儿行将删: N`**——记录每张子表删了多少孤儿。**N 异常大要警惕**(可能数据有问题,先查再继续)。
- `SHOW CREATE TABLE draft_images;` 等:6 条 FK 存在且 `ON DELETE CASCADE`(draft_images/gen_jobs/gen_job_images/accounts/account_txns/procurement)。

## 2. 关键流程冒烟(真实 MySQL 上起服务)
起 webui + worker(连测试 MySQL),手动验:
- **登录** `/api/auth/login` 正常(users 表读写 + 时间列)。
- **列草稿** `/api/drafts`:列表/分页正常,排序对(created_at 现 DATETIME);响应里 **cost_cny 是 JSON number 或 null,不是字符串**。
- **钱包** `/api/wallet` + recharge/deduct:响应 balance 是 **JSON number**(不是 `"0.3000"` 字符串);recharge `0.10` ×3 后余额精确 `0.30`(Decimal 精确,非 0.30000000000000004)。
- **删草稿**:删一个有图 + 有出图任务的草稿 → draft_images / gen_jobs / gen_job_images **随级联删**(FK CASCADE 生效)。
- **删用户**(admin):accounts/account_txns 随删;store_client_id 维度的 warehouses/postings 等也被(手写)删。
- **出图**:worker 消费一个任务、落 draft_images 正常。
- **快照** `/api/ext/snapshots`:price_min/max 是 number。

## 3. 回滚演练
```bash
python -m uv run alembic downgrade 0001_baseline   # 回到 M4 前
```
确认能回滚(FK drop、类型回退)。**注**:0004 时间 downgrade(DATETIME→TEXT)可能有损/格式变化,生产回滚需谨慎评估;首选向前修而非回滚。

## 4. 结论
- 全部 ✅ → M4 可上线。
- 任一项异常 → 记录现象,**不上线**,回来修迁移/代码。

---
相关:[memory dal-refactor-progress]、[memory mysql-docker-deploy](部署 recipe)。
