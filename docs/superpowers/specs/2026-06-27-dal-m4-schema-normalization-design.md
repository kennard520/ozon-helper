# 数据访问层 M4：schema 规范化(钱/时间/外键/索引)— 设计

- 日期：2026-06-27
- 所属:数据访问层重构 · 子项目1。M1 基座✓ / M2 全仓储✓ / M3 退役 db.py✓。**本 spec = M4**:把 schema 类型/约束修对。
- 与 M1-M3 的本质区别:**M4 真改 schema + 迁移生产数据**(不再是 behavior-preserving),风险更高,每子阶段配 Alembic 迁移 + 数据转换 + 回滚。

## 0. 已定决策
1. **范围 = 四项全做**:索引 + 钱 Float→Numeric + 时间 TEXT→DateTime + 外键+级联。
2. **钱** = `Numeric(18, 4)`(`asdecimal=True`):MySQL 真 DECIMAL、Python 层收发 `Decimal`(钱包算术精确)、SQLite 近似存储可接受。**仅真钱列**;`dropoff_lat/lng`(经纬度)保持 Float。
3. **时间** = 列改 `DateTime`,但**对外仍 ISO 字符串**(前端/测试/契约不变)。用自定义 `ISODateTime` TypeDecorator 在 SQLAlchemy 类型层做 datetime↔ISO 转换,**仓储零改动**。
4. **外键** = 6 条强父子加 `ON DELETE CASCADE`;弱引用(warehouse_id)不加;加 FK 前清孤儿;`store_client_id` 维度仍手写;删冗余手写级联。
5. **拆 4 子阶段**(M4a 索引 → M4b 钱 → M4c 时间 → M4d 外键),按风险递增,各自 Alembic 迁移 + 641 闸门。

## 1. 迁移机制(M4 起首次用 Alembic 做真迁移)
- **测试/新库**:`metadata.create_all(engine)` 直接建**最终 schema**(schema.py 改完即新类型/索引/FK),不跑迁移。
- **现网 prod**:已 `stamp 0001_baseline`,跑 `0002`–`0005` 增量迁移(ALTER + 数据转换)升级。
- **baseline 一致性(简化处置)**:`0001_baseline.py` 是 `metadata.create_all(live metadata)`——M4 改 metadata 后它会建新 schema。**不冻结它**(autogenerate 冻结 fiddly 易错)。约定:**新库(测试/全新部署)= `metadata.create_all` + `alembic stamp head`**(直接得最终 schema 并标记已迁,**从不从零 `upgrade`**);**现网已 stamp 0001 = 跑 0002+ 增量**。两条路径都不会双重应用,baseline 保持原样即可。这条约定写进部署文档。
- 每个 `000N` 迁移:`upgrade()` 做 ALTER/数据转换,`downgrade()` 反向(尽力,数据有损转换标注不可逆)。
- **⚠️ MySQL 验证(贯穿,M4 后必做)**:测试全 SQLite,M4 的 ALTER/DECIMAL/DATETIME/FK 行为 SQLite 与 MySQL 不同,**每个子阶段的 Alembic 迁移必须在真实 MySQL 跑一遍验证**(尤其数据转换 + 孤儿清理 + FK 添加)。641 绿不充分。

## 2. M4a:索引(最稳,先做)
schema.py 加 `Index`,Alembic `0002_indexes` 用 `op.create_index`:
- `drafts`:`idx_drafts_offer_id`(offer_id)、`idx_drafts_user_status`(user_id, status)、`idx_drafts_ozon_pid`(ozon_product_id)、`idx_drafts_media_status`(media_status)。
- 其余按需(`source_offer_id` 若有热查询)。
- 无数据/代码改动。验证:641 + 迁移在 MySQL 建索引成功。

## 3. M4b:钱 Float→Numeric(18,4)
- **schema.py**:9 个真钱列 `Float`→`Numeric(18, 4, asdecimal=True)`(accounts.balance/total_recharge/total_consume、account_txns.amount/balance_after、drafts.cost_cny、offer_snapshots.price_min/price_max、procurement.cost_cny)。`dropoff_lat/lng` 不动。
- **仓储**:WalletRepo 的 recharge/deduct/refund 用 `Decimal` 算(`from decimal import Decimal`;入参 `float`/`str`→`Decimal`);读返回 `Decimal`。条件 UPDATE `balance >= :amount` 的 amount 用 Decimal。其它读 cost_cny/price_* 的仓储自然返回 Decimal。
- **Alembic `0003_money`**:MySQL `ALTER ... MODIFY ... DECIMAL(18,4)`(float→decimal MySQL 自动转,基本无损;标注极端浮点尾差风险)。SQLite 测试走 create_all。
- **parity 风险**:
  - 测试断言 `== 0.1` 这类:`Decimal('0.1') == 0.1`(float)为 False → 改测试断言为 Decimal 或近似比较(641 暴露,逐个修)。
  - **JSON 序列化**:钱 API 当前返回 JSON number。`Decimal` 经 FastAPI `jsonable_encoder`→float(number),前端不变;**M4b 必须实测一个钱 API 响应仍是 number 而非 string**(test_wallet API + 手验)。若变 string,在 API 边界 `float(decimal)` 或配置序列化。
- 验证:test_wallet(钱 parity)+ 641 + MySQL 迁移验。

## 4. M4c:时间 TEXT→DateTime(用 TypeDecorator 把牵连收敛到类型层)
- **新建 `packages/ozon_common/src/ozon_common/dal/types.py`**:`ISODateTime(TypeDecorator)`,`impl = DateTime`:
  - `process_bind_param`(写):接 ISO 字符串(如 `utc_now_iso()` 产出,带 'T' + `+00:00`)→ 解析成 **naive UTC datetime** 存库(MySQL DATETIME 无时区,统一 UTC)。也容忍已是 datetime/None。
  - `process_result_value`(读):库里 naive datetime → 格式化回 **ISO 字符串带 `+00:00`**(与 `utc_now_iso()` 输出一致),保证仓储拿到的仍是字符串。
- **schema.py**:22 个时间列 `Text`→`ISODateTime`。**仓储/应用代码零改动**(仍收发 ISO 字符串),`utc_now_iso()` 保留。
- **Alembic `0004_timestamps`**:MySQL `ALTER ... MODIFY ... DATETIME` + 把现有 ISO 文本转 DATETIME(现网数据是 `2026-..T..+00:00`,需 `STR_TO_DATE`/裁掉 'T' 与时区后转;**数据转换是本阶段最易错处**,迁移里写清转换 SQL 并标注)。SQLite 测试走 create_all(无历史数据)。
- **parity 风险**:`ISODateTime` 的读出格式必须**逐字符匹配** `utc_now_iso()`(含毫秒精度/`+00:00`),否则断言时间字符串的测试会挂 → 641 暴露,对齐格式。排序:DateTime 列 ORDER BY 与原 ISO 字典序同为时间序,分页/排序行为不变。
- 验证:641(尤其断言 created_at/updated_at 的测试)+ MySQL 数据转换验。

## 5. M4d:外键 + 级联(最后,孤儿数据风险)
- **schema.py**:6 列加 `ForeignKey("父表.列", ondelete="CASCADE")`:
  `draft_images.draft_id→drafts.id`、`gen_jobs.draft_id→drafts.id`、`gen_job_images.job_id→gen_jobs.id`、`accounts.user_id→users.id`、`account_txns.user_id→users.id`、`procurement.posting_number→postings.posting_number`。
  弱引用(`drafts.warehouse_id`、`delivery_methods.warehouse_id`)**不加 FK**。
- **Alembic `0005_fk`**:**先清孤儿**(`DELETE FROM 子 WHERE 父键 NOT IN (SELECT ... FROM 父)`,逐表),**再** `op.create_foreign_key(..., ondelete="CASCADE")`。SQLite 测试走 create_all + `PRAGMA foreign_keys=ON`(M1 已开)强制。
- **代码**:删 `delete_draft`/`delete_user` 里**手写删 user_id/draft_id/job_id 子表**的冗余代码(FK CASCADE 接管);**保留** `store_client_id` 维度的手写删(非 FK)。641 验证级联等价。
- 验证:641(删草稿/删用户的级联测试)+ MySQL 孤儿清理 + FK 添加验。

## 6. 测试与回归
- 每子阶段后 `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py'`,**≥ 641**(随子阶段可能修改/新增断言)。
- 新增:`ISODateTime` 单测(bind/result 往返格式 == utc_now_iso)、钱 Decimal 往返单测、FK 级联单测(SQLite PRAGMA on)。
- **MySQL 集成验证(M4 完成后,人工/脚本)**:在测试 MySQL 上跑 0002–0005 迁移 + 关键流程(钱包 recharge/deduct、删草稿级联、列草稿排序、出图)。

## 7. 风险与回滚
- **MySQL 数据转换**(M4c 时间最险、M4b 钱次之):迁移写清转换 SQL,先在测试 MySQL 演练;`downgrade` 尽力反向(时间转换可能有损,标注)。
- **孤儿数据**(M4d):清理前先 `SELECT COUNT` 记录将删多少,日志输出,避免静默删大量数据。
- **Decimal JSON**(M4b):实测 API 响应类型。
- **ISO 格式漂移**(M4c):TypeDecorator 输出逐字符对齐 utc_now_iso。
- 回滚:每子阶段独立提交;Alembic `downgrade`;镜像 rollback(见 [[mysql-docker-deploy]])。

## 8. 非目标
- 不动 `dropoff_lat/lng`(经纬度,Float 正确)。
- 不改 HTTP 契约(钱仍 number、时间仍 ISO 字符串)。
- 不引入 ORM 关系映射(继续 Core + 显式 FK 约束)。
- N+1/keyset 留 M5。
