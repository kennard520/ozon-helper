# 数据访问层重构 · M1:SQLAlchemy 基座 + 第一条竖切 — 设计

- 日期：2026-06-27
- 所属大改造：接口/数据访问层重构 · 子项目 1(数据访问层性能)。整体走 SQLAlchemy Core + Alembic + Repository/UoW 分层,绞杀者(strangler)路径,分 M1–M5 里程碑。**本 spec 只覆盖 M1**。
- 前置：monorepo 四包重构已完成(`packages/ozon_common`、`packages/ozon_api`、`apps/webui`、`apps/image_worker`),512 测试绿。

## 0. 已定架构决策(贯穿 M1–M5)

1. **持久化根基** = SQLAlchemy **Core**(非 ORM)+ Alembic。理由:当前 `Store` 返回 dict、裸 SQL,Core 显式、无 ORM 懒加载隐式 N+1、仓储可继续返回 dict 保持调用方不变。
2. **UoW 访问** = 请求级 **scoped-session(ContextVar 绑定)**,worker/脚本用 `with session_scope()`。随 M2+ service 抽出后,对已抽出的 service 收紧为显式注入。
3. **schema 权威** = **Alembic + 全表 metadata**(M1 就接管),老 `Store.init()` 的建表逻辑退役。
4. 绞杀者:每里程碑 shippable、过 512 回归、可回滚。

## 1. M1 目标与范围

**目标**:立起 SQLAlchemy engine(连接池)+ Alembic + scoped-session 基座;把 **settings / drafts+draft_images / gen_jobs+gen_job_images** 三组共享聚合迁到 Core 仓储,**webui 与 worker 共用同一套仓储**,打通 `engine→repo→session→双端消费`这条 walking skeleton,顺带**消灭 worker `DataStore` 重复**。

**M1 做**:
- 全部 ~20 张表的 SQLAlchemy Core `MetaData`/`Table` 定义(schema 权威)。
- Alembic 立项 + baseline 迁移(= 当前最终 schema)。
- engine 工厂(QueuePool,SQLite/MySQL 双路)+ scoped-session/UoW。
- 3 个共享仓储(SettingsRepo / DraftImageRepo / GenJobRepo,基于 Core)。
- webui `Store` 的这三组方法 → 薄壳转调仓储(`APP.store.xxx` 签名不变)。
- worker `DataStore` → 退役,改用 `session_scope()` + 三仓储。

**M1 不做**(留后续里程碑):
- 其余 ~17 张表的仓储迁移(M2)。
- 删 `translate()`/全局 RLock/手写 `MySQLConn`(M3,等所有查询都上 SQLAlchemy 后)。
- schema 类型规范(钱→Numeric、FK、时间→DateTime、补索引)(M4)。
- N+1/keyset 分页(M5,部分在仓储重写时自然消除)。
- 不改任何 HTTP 接口契约(前端/插件零改动)。

## 2. 组件与分层

```
packages/ozon_common/src/ozon_common/db/
├── engine.py        # build_engine():QueuePool;SQLite 走 WAL,MySQL 走 pool_pre_ping/recycle
├── session.py       # session_scope() 上下文管理器 + ContextVar(_current_session)+ current_session()
├── schema.py        # 全部 ~20 表 Core MetaData/Table(schema 唯一权威)
└── repositories/
    ├── base.py              # Repo 基类:持有 current_session(),通用 row→dict
    ├── settings_repo.py
    ├── draft_image_repo.py  # drafts 出图相关读 + draft_images 读写
    └── gen_job_repo.py      # gen_jobs / gen_job_images
migrations/                  # 仓库根
├── alembic.ini
├── env.py                   # target_metadata = ozon_common.db.schema.metadata;双后端 URL 由 env 决定
└── versions/0001_baseline.py
```

分层(目标形态,M1 打通竖切部分):
```
route(薄) → service → repository(Core,在 current_session() 上跑) → engine/pool
                              ↑ schema.py
请求级 session:webui 中间件开/绑 ContextVar/请求结束 commit-or-rollback;worker/脚本/启动:with session_scope()
```

**为何 schema/engine/共享仓储放 `ozon_common`**:DB 是 webui+worker 共用的同一个库,schema 是两端共享契约,归共享基础设施层。webui 专属表的仓储 M2 进 webui,但**表 metadata 全在 ozon_common**(Alembic 需要统一的 MetaData)。

## 3. engine 与连接池

`build_engine(url)`:
- **MySQL**:`create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600, future=True)`。`pool_pre_ping` + `pool_recycle` 解决 `wait_timeout` 失效连接(替代手写 `MySQLConn` 的重连)。
- **SQLite**:`create_engine("sqlite:///<path>", future=True)` + `connect` 事件监听里执行 `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON`。WAL 让协存期老连接与池连接并发读不互斥;busy_timeout 缓解写争用。
- engine 进程级单例(按 URL 缓存);测试每个临时库 URL 各自 engine。
- URL 来源:复用现有 `mysql_enabled()`/env 判定;MySQL URL 由 `OZON_MYSQL_*` 拼;否则 `sqlite:///<DEFAULT_DB 或传入 path>`。

## 4. scoped-session / UoW

`session.py`:
- `_current_session: ContextVar[Session | None]`。
- `@contextmanager session_scope()`:从 engine 开 `Session`,设进 ContextVar,`try: yield; commit except: rollback; finally: close + 复位 ContextVar`。
- `current_session() -> Session`:读 ContextVar;未在作用域内则抛清晰错误(仓储只在 session 作用域里被调)。
- **webui 集成**:一个 ASGI 中间件,每请求 `with session_scope():` 包住 handler——请求成功提交、异常回滚。读多写少端点也走同一作用域(只读不写则 commit 无副作用)。
- **worker 集成**:`handle_job` 内 `with session_scope():` 包一次任务的仓储操作。
- **启动/脚本**:迁移、回填、CLI 各自 `with session_scope():`。

**协存期事务边界(M1 如实接受的成本)**:一个请求里若同时碰"已迁移表(走 session)"和"未迁移表(走老 Store 裸连接)",是**两个独立事务**,无跨两者的原子性。M1 接受此现状(绞杀固有),M3 全切 session 后统一为请求级单事务。

## 5. schema metadata 与 Alembic 接管(决策 A)

- `schema.py` 用 Core `Table()` **逐字段对照**现有 `store.py`(SQLite CREATE)+ `db.py`(MYSQL_DDL)定义全部 ~20 表的**当前最终形态**(列名/类型/默认/主键/唯一键/索引)。M1 **不改任何列类型/约束**(钱仍 float、无 FK——那是 M4),只是"如实描述现状"。
- Alembic baseline `0001_baseline.py` = `metadata.create_all()` 等价(从 metadata 自动生成后人工核对)。
- **新库(测试)**:`metadata.create_all(engine)` 直接建最终 schema。
- **现网 prod 库**:已由老 `init()` 跑完所有历史迁移,schema 已是最终态 → `alembic stamp 0001_baseline` 采纳(不重建)。**采纳前**用一致性脚本核对现网实际表结构 == metadata。
- 老 `Store.init()` 的建表/`_ensure_column`/`_migrate_*` **退役**。

**关键衔接(载荷:512 测试)**:现有 512 测试与本地启动大量靠 `Store(tmp_path)` 在 `__init__` 里建表。退役老 DDL 后,`Store.__init__`(协存期)改为调 **`metadata.create_all(engine)`** 来"确保 schema 存在"(幂等),替代原来的裸 SQL 建表块——这样 `Store(tmp)` 构造仍得到一个建好全部 ~20 表的库,512 测试无感。即:建表权威从"老裸 SQL"切到"metadata",但触发点(Store 构造/启动)对调用方不变。

**数据回填的处理(option A 的关键风险点,显式定清)**:老 `init()` 里有 `_backfill_variant_group`/`_backfill_offer_id`/`_backfill_draft_images` 三个**数据**回填(非 DDL)。
- 现网:已回填,无需再跑。
- 新库(测试):无历史数据,回填是 no-op——**但 `test_draft_images` 等测试依赖 `_backfill_draft_images` 的行为**(手动塞 images_json → 重开 Store → 表被回填)。
- 处置:M1 **保留这三个回填为"数据迁移"函数**(从 `init()` 里剥离到一个 `migrations`/`backfills` 模块,启动时在 `session_scope()` 内跑一次,自限逻辑不变)。DDL 交给 Alembic,数据回填暂留为显式 run-once,M4/M5 再评估清理。**不在 M1 删这些回填**,以免破坏现有测试与历史数据语义。

## 6. 三个共享仓储(Core)

返回**dict**,形状与现有 `Store`/`DataStore` 对应方法**完全一致**(调用方不变)。每个方法在 `current_session()` 上用 Core `select/insert/update` 构建。

- **SettingsRepo**:`get_settings(user_id)` / `save_settings(...)`(覆盖 webui Store 与 worker DataStore 两版的 settings 读取语义:全局 user_id=0 + 用户覆盖)。
- **DraftImageRepo**:`add_draft_image` / `load_draft_images(draft_id)`(批量友好)/ worker 的 `get_draft`+`_row_to_draft` 出图所需读取。
- **GenJobRepo**:`create_gen_job`/`get_gen_job`/`get_latest_gen_job`/`list_gen_jobs`/`has_active_gen_job`/`update_gen_job`/`set_gen_job_status`/`create_gen_job_images`/`get_gen_job_images`/`update_gen_job_image`/`set_gen_job_image_status`/`count_gen_job_images_by_status`。

webui `Store` 对应方法改为 `return SettingsRepo().get_settings(...)` 之类薄壳(M1 期 `Store` 仍是入口,内部转调)。worker 直接用仓储。

## 7. 双后端与既有适配层的关系

- M1 后,这三组聚合的查询走 SQLAlchemy(原生方言,**不经 `translate()`**)。
- 其余 ~17 表仍走老 `Store` 裸连接 + `translate()`(M2 逐个搬,M3 删 translate)。
- 即 M1 起 `translate()` 只服务"未迁移表",随里程碑收缩,M3 归零。

## 8. 测试

- **回归**:全程 512 不下降(`python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py'`;pytest 已是 dev 依赖)。
- **metadata 保真测试**(M1 关键护栏):分别用「老 `init()` 路径」与「`metadata.create_all()`」在两个临时 SQLite 建库,**diff 两者 schema**(表/列/类型/索引/唯一键),必须一致——证明 metadata 如实描述现状、Alembic 接管不改 schema。
- **仓储单测**:SettingsRepo/DraftImageRepo/GenJobRepo 针对 SQLite 的 CRUD + 边界(覆盖原 DataStore/Store 对应行为)。
- **worker 路径**:`session_scope()` + 仓储跑通一个 mock 出图任务的落库(沿用阶段2 worker 测试)。
- **协存冒烟**:同一进程内老 Store 裸连接 + 新池对同一 SQLite 文件并发读写不死锁(WAL 生效)。
- **并发**(可选):多线程并发打 settings/gen_job 读写,验证去锁后无串行化退化、无连接泄漏。

## 9. 风险与回滚

- **metadata 与现状漂移** → §8 保真测试兜底;不一致则修 metadata。
- **协存双连接对 SQLite 锁** → WAL + busy_timeout;协存冒烟验证。
- **scoped-session 生命周期**(中间件未覆盖的路径、后台线程)→ `current_session()` 未在作用域内即抛错,早暴露。
- **回填语义**(§5) → 不删、剥离为显式 run-once,保历史与测试。
- 回滚:M1 全部新增/旁路,老 `Store` 路径仍在;出问题可让三组方法回退走老实现(保留老实现到 M3 再删),或回滚提交。

## 10. 交付物

M1 完成后:engine/池/Alembic/scoped-session 基座就位;三组共享聚合走 SQLAlchemy 仓储、webui+worker 共用、DataStore 退役;512 绿 + 新护栏测试;`translate()`/全局锁仍在(服务剩余表),M2 起继续绞杀。

## 11. 非目标(YAGNI)

- 不上 ORM/关系映射;不引入 service 层显式注入(M2+ 渐进)。
- 不改 schema 类型/约束、不动 HTTP 契约。
- 不一次性迁全部表。
