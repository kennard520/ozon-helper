# 数据访问层 M4：schema 规范化 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps 用 checkbox。

**Goal:** 把 schema 类型/约束修对——加索引、钱 Float→`Numeric(18,4)`(Python 用 Decimal 精确)、时间 TEXT→DateTime(用 `ISODateTime` TypeDecorator 对外仍 ISO 字符串)、6 条外键加 ON DELETE CASCADE(先清孤儿)。每子阶段配 Alembic 迁移,全程 641 不降。

**Architecture:** M1-M3 已把数据访问全迁 SQLAlchemy 仓储。M4 改 `dal/schema.py` 的列类型/约束 + 写 Alembic 增量迁移(`0002`-`0005`)。**新库/测试 = `metadata.create_all` + `stamp head`;现网 = 跑增量迁移**。时间转换用自定义 SQLAlchemy 类型把牵连收敛到类型层,仓储零改。钱用 Decimal,FK 用 DB 级联替代手写。

**Tech Stack:** SQLAlchemy 2.x Core(TypeDecorator/ForeignKey/Numeric/DateTime)、Alembic、pytest。

**全局约定:** 仓库根 `E:\personal\ozon-helper`;分支 `feat/auto-listing-ai-pipeline`;**`uv` 用 `python -m uv`**;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
**回归闸门**:每 Task 末 `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider`,**≥ 641**(子阶段可能调整/新增断言)。ruff 只带本 Task 文件。
**⚠️ MySQL 验证盲区**:测试全 SQLite。M4 的 ALTER/DECIMAL/DATETIME/FK + 数据转换 + 孤儿清理在 MySQL 行为不同,**641 绿不充分**。每个 Task 报告须重申「该 Alembic 迁移需在真实 MySQL 验证」。M4 完成后做一次 MySQL 集成验证(Task 5)。

**Alembic 迁移文件**:都放 `migrations/versions/`,`down_revision` 串成链(0001→0002→0003→0004→0005)。迁移里 dialect 分支用 `op.get_bind().dialect.name`(`'sqlite'` vs `'mysql'`),SQLite 分支多为 no-op(测试走 create_all),MySQL 分支做真 ALTER。

---

## File Structure

| 路径 | 改动 |
|---|---|
| `packages/ozon_common/src/ozon_common/dal/schema.py` | 索引/钱类型/时间类型/FK 全在此改 |
| `packages/ozon_common/src/ozon_common/dal/types.py`(新) | `ISODateTime` TypeDecorator |
| `packages/ozon_common/src/ozon_common/dal/repositories/wallet_repo.py` | 钱算术改 Decimal |
| `migrations/versions/0002_indexes.py` … `0005_fk.py`(新) | 各子阶段迁移 |
| `apps/webui/src/webui/store.py` / `app_service.py` | M4d 删冗余手写级联(delete_draft/delete_user) |
| `packages/ozon_common/tests/test_*`(新/改) | ISODateTime/钱 Decimal/FK 级联单测;现有断言按需调整 |

---

## Task 1（M4a）：索引

**Files:** Modify `dal/schema.py`;Create `migrations/versions/0002_indexes.py`

- [ ] **Step 1: schema.py 加索引**
在 `drafts` Table 定义里(与现有 `Index("idx_drafts_variant_group", "variant_group")` 并列)加:
```python
    Index("idx_drafts_offer_id", "offer_id"),
    Index("idx_drafts_user_status", "user_id", "status"),
    Index("idx_drafts_ozon_pid", "ozon_product_id"),
    Index("idx_drafts_media_status", "media_status"),
```
(确认这些列在 drafts Table 里都有;`ozon_product_id`/`media_status` 若列名不同以 schema 实际为准。)

- [ ] **Step 2: Alembic 0002_indexes**
Create `migrations/versions/0002_indexes.py`:
```python
"""0002 indexes: drafts offer_id/(user_id,status)/ozon_product_id/media_status"""
from alembic import op

revision = "0002_indexes"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_IDX = [
    ("idx_drafts_offer_id", ["offer_id"]),
    ("idx_drafts_user_status", ["user_id", "status"]),
    ("idx_drafts_ozon_pid", ["ozon_product_id"]),
    ("idx_drafts_media_status", ["media_status"]),
]

def upgrade() -> None:
    for name, cols in _IDX:
        op.create_index(name, "drafts", cols)

def downgrade() -> None:
    for name, _ in _IDX:
        op.drop_index(name, "drafts")
```

- [ ] **Step 3: 验证 metadata 一致(新库带索引)**
```bash
cd /e/personal/ozon-helper && python -m uv run python -c "
import tempfile,sqlite3,pathlib
from sqlalchemy import create_engine
from ozon_common.dal.schema import metadata
d=tempfile.mkdtemp(); db=str(pathlib.Path(d)/'x.db')
e=create_engine(f'sqlite:///{db}'); metadata.create_all(e); e.dispose()
con=sqlite3.connect(db); idx={r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='index'\")}; con.close()
print('have idx_drafts_offer_id:', 'idx_drafts_offer_id' in idx)
assert {'idx_drafts_offer_id','idx_drafts_user_status','idx_drafts_ozon_pid','idx_drafts_media_status'} <= idx
print('OK')
"
```
预期 `OK`。

- [ ] **Step 4: 回归 + 提交**
回归 ≥641。`git add dal/schema.py migrations/versions/0002_indexes.py && commit "feat(dal): M4a 加 drafts 缺失索引(offer_id/user_status/ozon_pid/media_status)"`。报告重申「0002 迁移需 MySQL 验证」。

---

## Task 2（M4b）：钱 Float→Numeric(18,4)

**Files:** Modify `dal/schema.py`、`dal/repositories/wallet_repo.py`;Create `migrations/versions/0003_money.py`、`packages/ozon_common/tests/test_money_decimal.py`

- [ ] **Step 1: schema.py 改 9 个钱列**
把这些 `Float` 改 `Numeric(18, 4, asdecimal=True)`(顶部 `from sqlalchemy import Numeric`):
- `accounts`: balance, total_recharge, total_consume
- `account_txns`: amount, balance_after
- `drafts`: cost_cny
- `offer_snapshots`: price_min, price_max
- `procurement`: cost_cny
**不改** `delivery_methods.dropoff_lat/dropoff_lng`(经纬度,保持 Float)。

- [ ] **Step 2: WalletRepo 用 Decimal**
`wallet_repo.py`:`from decimal import Decimal`。入参金额 `Decimal(str(amount))`(避免 float 直转 Decimal 引入误差);余额算术用 Decimal;条件 UPDATE `AC.c.balance >= Decimal(str(amount))`。读回的 balance/amount 已是 Decimal(asdecimal)。其它仓储(读 cost_cny/price_*)无需改(自然返回 Decimal)。

- [ ] **Step 3: Decimal 往返单测**
Create `test_money_decimal.py`:绑临时 SQLite(`metadata.create_all`+bind),`session_scope` 内 WalletRepo recharge `Decimal('10.10')` 三次 → 断言 balance == `Decimal('30.30')`(**精确,无浮点误差**);deduct `Decimal('0.30')` → `Decimal('30.00')`。验证 Decimal 精确累加。

- [ ] **Step 4: Alembic 0003_money**
Create `migrations/versions/0003_money.py`(`down_revision="0002_indexes"`):`upgrade()` 里 `if op.get_bind().dialect.name == "mysql":` 对 9 列逐个 `op.alter_column("表","列", type_=sa.Numeric(18,4), existing_type=sa.Float())`(MySQL float→DECIMAL 自动转)。SQLite 分支 no-op(测试走 create_all)。`downgrade()` 反向 alter 回 Float。

- [ ] **Step 5: 钱 JSON 序列化实测(parity 关键)**
确认钱 API 响应仍是 JSON number 不是 string:
```bash
cd /e/personal/ozon-helper && python -m uv run python -m pytest apps/webui/tests/test_wallet.py -q -p no:cacheprovider 2>&1 | tail -4
```
若 test_wallet 里有 API 层断言钱字段类型/值,确认通过。**另**:`grep` 钱 API 端点(/api/wallet)返回路径,确认经 FastAPI `jsonable_encoder`(Decimal→float)。若发现响应变 string,在端点边界 `float(...)` 或自定义 encoder——并在报告说明。

- [ ] **Step 6: 修测试断言 + 回归**
跑全量,失败处多为 `assertEqual(money, 0.1)`(float) vs Decimal → 改成 `Decimal('0.1')` 或 `assertAlmostEqual`。**逐个修绿,≥641**。

- [ ] **Step 7: 提交**
`git add ...; commit "feat(dal): M4b 钱 Float→Numeric(18,4),WalletRepo 用 Decimal 精确算术"`。报告重申「0003 迁移需 MySQL 验证 + 钱 JSON 类型已实测」。

---

## Task 3（M4c）：时间 TEXT→DateTime（ISODateTime TypeDecorator）

**Files:** Create `dal/types.py`;Modify `dal/schema.py`;Create `migrations/versions/0004_timestamps.py`、`packages/ozon_common/tests/test_isodatetime.py`

- [ ] **Step 1: ISODateTime TypeDecorator**
Create `packages/ozon_common/src/ozon_common/dal/types.py`:
```python
"""ISODateTime:库里存 DateTime(MySQL DATETIME),Python 层收发 ISO 字符串(与 utc_now_iso 一致)。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class ISODateTime(TypeDecorator):
    impl = DateTime  # MySQL DATETIME / SQLite DATETIME
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # 写:接 ISO 字符串/datetime/None → naive UTC datetime
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def process_result_value(self, value, dialect):
        # 读:naive datetime → ISO 字符串带 +00:00(对齐 utc_now_iso 输出)
        if value is None:
            return None
        if isinstance(value, str):  # 某些后端可能回字符串
            value = datetime.fromisoformat(value)
        return value.replace(tzinfo=timezone.utc).isoformat()
```

- [ ] **Step 2: 往返单测(格式必须对齐 utc_now_iso)**
Create `test_isodatetime.py`:绑临时 SQLite 建一张含 `ISODateTime` 列的表,写入 `utc_now_iso()` 的输出 → 读回断言**仍是字符串、可被 `datetime.fromisoformat` 解析、且 `==` 写入值(或秒级对齐)**。重点验证:写 ISO 字符串、读回 ISO 字符串、时区为 +00:00。
> 注意微秒:SQLite 存 datetime 保微秒;MySQL `DATETIME` 默认秒级(要微秒需 `DATETIME(6)`)。若现有测试断言带微秒的 created_at 精确值,M4c 要么 MySQL 用 `DATETIME(6)`(`DateTime` 的 mysql variant)、要么接受秒级并确认测试不依赖微秒。单测里覆盖这点。

- [ ] **Step 3: schema.py 22 个时间列改 ISODateTime**
顶部 `from ozon_common.dal.types import ISODateTime`。把所有 `created_at/updated_at/fetched_at/synced_at/captured_at` 列的类型 `Text`→`ISODateTime`(保持 nullable/default 不变;注意 `server_default` 若是空字符串要去掉或改 None——DateTime 列不能 server_default ''. 确认每列原 default,时间列一般无 server_default 或 NOT NULL 无 default)。**仓储不动**(仍收发字符串)。

- [ ] **Step 4: Alembic 0004_timestamps**
Create `migrations/versions/0004_timestamps.py`(`down_revision="0003_money"`):`upgrade()` MySQL 分支:对 22 列 `op.alter_column(... type_=sa.DateTime(), existing_type=sa.Text())`——**但现网数据是 `2026-..T..+00:00` 字符串,MySQL 直接 ALTER 会失败/截断**。正确做法:先把列里的 ISO 字符串规整成 MySQL 能解析的格式再 ALTER,或用中间列。迁移里写:
```python
# 伪:MySQL 把 ISO 文本转 DATETIME(裁掉 'T'/时区)
# UPDATE 表 SET col = STR_TO_DATE(REPLACE(SUBSTRING_INDEX(col,'+',1),'T',' '), '%Y-%m-%d %H:%i:%s.%f') WHERE col<>'' ;
# 再 ALTER col DATETIME(6)
```
对每个时间列生成上述 UPDATE + ALTER。**这是 M4 最易错处**,SQL 写清、标注「需 MySQL 演练」。SQLite 分支 no-op。`downgrade()` 标注有损/尽力。

- [ ] **Step 5: 回归(断言时间字符串的测试)**
全量 ≥641。失败多为 ISODateTime 读出格式与原 `utc_now_iso()` 不完全一致(微秒/时区) → 调 `process_result_value` 对齐。逐个修绿。

- [ ] **Step 6: 提交**
`commit "feat(dal): M4c 时间 TEXT→DateTime(ISODateTime TypeDecorator,对外仍 ISO 字符串)"`。报告重申「0004 数据转换需 MySQL 演练验证」。

---

## Task 4（M4d）：外键 + 级联

**Files:** Modify `dal/schema.py`、`apps/webui/src/webui/store.py`(delete_draft/delete_user)、可能 `app_service.py`;Create `migrations/versions/0005_fk.py`、`packages/ozon_common/tests/test_fk_cascade.py`

- [ ] **Step 1: schema.py 加 6 条 FK**
顶部 `from sqlalchemy import ForeignKey`。在子表对应列加 FK(ondelete CASCADE):
- `draft_images.draft_id`:`Column("draft_id", Integer, ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)`
- `gen_jobs.draft_id` → `ForeignKey("drafts.id", ondelete="CASCADE")`
- `gen_job_images.job_id` → `ForeignKey("gen_jobs.id", ondelete="CASCADE")`
- `accounts.user_id` → `ForeignKey("users.id", ondelete="CASCADE")`
- `account_txns.user_id` → `ForeignKey("users.id", ondelete="CASCADE")`
- `procurement.posting_number` → `ForeignKey("postings.posting_number", ondelete="CASCADE")`
弱引用 `drafts.warehouse_id`、`delivery_methods.warehouse_id` **不加**。

- [ ] **Step 2: FK 级联单测(SQLite PRAGMA on)**
Create `test_fk_cascade.py`:绑临时 SQLite(engine 已 `PRAGMA foreign_keys=ON`,M1 设的;确认 build_engine 的 sqlite 分支有),`metadata.create_all`。插 draft + draft_images + gen_jobs → `DELETE FROM drafts WHERE id=?` → 断言 draft_images/gen_jobs 随删(级联生效)。同理 users → accounts/account_txns 级联。

- [ ] **Step 3: 删冗余手写级联**
- `store.py` 的 `delete_draft`(经 DraftRepo):删手写删 draft_images/gen_jobs 的代码(FK CASCADE 接管);**保留** drafts 行本身的删除。
- `delete_user`(UserRepo):删手写删 accounts/account_txns(user_id 维度)的代码;**保留** `store_client_id` 维度删 warehouses/postings/procurement/offer_snapshots(非 FK)。
- 确认 DraftRepo/UserRepo 里对应级联代码也删(它们才是真实现)。

- [ ] **Step 4: Alembic 0005_fk(先清孤儿再加 FK)**
Create `migrations/versions/0005_fk.py`(`down_revision="0004_timestamps"`):`upgrade()` MySQL 分支:
```python
# 1) 清孤儿(记数后删),逐子表:
#    DELETE c FROM draft_images c LEFT JOIN drafts p ON c.draft_id=p.id WHERE p.id IS NULL;
#    （gen_jobs/gen_job_images/accounts/account_txns/procurement 同理）
# 2) 加 FK:
#    op.create_foreign_key("fk_dimg_draft","draft_images","drafts",["draft_id"],["id"],ondelete="CASCADE")
#    ...其余 5 条
```
**清孤儿前 SELECT COUNT 各表孤儿数并 print/log**(避免静默删大量数据)。SQLite 分支 no-op(测试 create_all + PRAGMA)。`downgrade()` drop FK。

- [ ] **Step 5: 回归(删草稿/删用户级联测试)**
全量 ≥641。`test_drafts`(删草稿)、`test_admin_users`(删用户)等验证级联等价(手写删 → FK 删,结果一致)。逐个修绿。

- [ ] **Step 6: 提交**
`commit "feat(dal): M4d 加 6 条外键 ON DELETE CASCADE,清孤儿,删冗余手写级联"`。报告重申「0005 孤儿清理 + FK 添加需 MySQL 验证」。

---

## Task 5：M4 收尾 + MySQL 集成验证清单

- [ ] **Step 1: 全量终验**:`pytest apps/webui/tests packages/ozon_common/tests`(≥641)+ 三包 import 冒烟 + `ruff --select I packages/ozon_common/src/ozon_common/dal`。
- [ ] **Step 2: 写 MySQL 验证清单**:在 `docs/` 或部署文档写一份「M4 上线前 MySQL 验证步骤」:① 测试 MySQL 库跑 `alembic upgrade head`(0002→0005),确认无报错、数据转换正确(钱值不变、时间值不变、孤儿清理数合理);② 关键流程冒烟(钱包 recharge/deduct、删草稿级联删图、列草稿排序、出图落库);③ 回滚演练 `alembic downgrade`。
- [ ] **Step 3: 提交 + memory**:`commit "docs(dal): M4 收尾 + MySQL 验证清单"`;更新 memory(M4 完成、schema 已规范、**MySQL 必验**、M5 待做)。

---

## Self-Review
- **Spec 覆盖**:§2 索引→T1;§3 钱→T2;§4 时间→T3;§5 外键→T4;§1 迁移机制(create_all+stamp / 增量)→各 T 的 Alembic + T5 清单;§6 测试→各 T 单测 + 641;§7 风险(MySQL/孤儿/Decimal JSON/ISO 格式)→分散标注 + T5。
- **占位符**:Alembic 迁移的 MySQL 数据转换 SQL 给了模式 + 伪码(实际 SQL 由 subagent 按列生成),因 22 列/6 表逐条展开过长且需按列名,属「给清模式 + 标注易错 + MySQL 演练」,非占位。ISODateTime/Numeric/FK/索引均有真实代码。
- **类型一致**:`ISODateTime`、`Numeric(18,4,asdecimal=True)`、`ForeignKey(...ondelete="CASCADE")`、迁移 down_revision 链(0001→…→0005)贯穿一致。
- **顺序**:索引(无数据)→钱→时间→外键(孤儿),风险递增;T5 收尾。每 Task 独立提交 + 641。
