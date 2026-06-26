# Monorepo 项目化重构设计

- 日期：2026-06-26
- 范围：把 `ozon-listing-webui`(后端)与 `ozon-image-worker` 从「脚本堆」改造成规范的 Python 项目，统一为 uv workspace 单仓多包架构，消除两地复制粘贴的重复模块。
- 不在本次范围：业务逻辑改动、前端(Vue)代码改动、变体卡片 UI 等功能需求。本次纯结构/打包重构，行为保持不变。

## 1. 背景与动机

现状诊断：

- **webui** 基本规范：`backend/` 有 `__init__.py`、用绝对导入 `from backend.xxx`、`run_api.py` 顶层启动器。瑕疵是根目录散落游离脚本、无打包元数据。
- **image-worker** 不是包：无 `__init__.py`，平级裸导入 `from gen_image import ...`，只有在该目录内 `python worker.py` 才跑得起来。
- **核心痛点**：worker 把 backend 的 6 个模块裁剪复制了一份，两地各维护、已经漂移：

  | 模块 | worker | backend | 状态 |
  |---|---|---|---|
  | store.py | 220 行 | 1946 行 | 副本(差异大) |
  | db.py | 135 行 | 479 行 | 副本 |
  | gen_image.py | 225 行 | 272 行 | 副本 |
  | oss.py | 47 行 | 130 行 | 副本 |
  | mq.py | 53 行 | 68 行 | 副本 |
  | image_plan.py | 54 行 | 60 行 | 副本 |

  改 backend 时极易与 worker 漂移，是最大的结构债务。

## 2. 已定决策

1. **代码拓扑**：单仓多包(monorepo + 共享包)。
2. **构建/依赖工具**：uv workspace(引入 uv，替代当前 venv+pip)。
3. **store.py 力度**：只抽真正共享的内核(settings 读取、json/时间 helper、`draft_images` 写入)进共享包；webui 那 1946 行业务数据层留在 webui。
4. **webui 包名**：`backend` → `webui`，一次性机械重命名所有 `backend.` 导入。
5. **目录布局**：彻底搬进 `apps/`(物理迁移 frontend/deploy/data，连带改 Docker 构建上下文与 deploy 路径)。

## 3. 目标结构

```
ozon-helper/
├── pyproject.toml                 # uv workspace 根：members=[packages/*, apps/*]；[tool.uv] 阿里云镜像；ruff 配置
├── uv.lock                        # 全仓统一锁
│
├── packages/
│   ├── ozon_common/               # name = ozon-common；依赖：pymysql, oss2, pika, openai
│   │   ├── pyproject.toml
│   │   └── src/ozon_common/
│   │       ├── __init__.py
│   │       ├── db.py              # MySQL 方言适配(backend 版为准)
│   │       ├── oss.py             # OSS 客户端
│   │       ├── mq.py              # RabbitMQ 连接/队列/publish/consume
│   │       ├── gen_image.py       # 出图 SDK(prompt/payload/HTTP)
│   │       ├── image_plan.py      # build_image_plan 纯函数
│   │       ├── settings.py        # ai_config/oss_config + json/时间 helper(store 内核)
│   │       └── draft_images.py    # draft_images 写入路径(store 内核)
│   │
│   └── ozon_api/                  # name = ozon-api；原 ozon_api/，Ozon Seller API 客户端 + 选品定价流
│       ├── pyproject.toml
│       └── src/ozon_api/          # client.py / copy_flow.py / camo_pricing.py / ... + tests/
│
└── apps/
    ├── webui/                     # name = ozon-webui；依赖：fastapi,uvicorn,pydantic,python-multipart,openpyxl,pillow,ozon-common,ozon-api
    │   ├── pyproject.toml
    │   ├── src/webui/             # ← 原 backend/，全部 from backend → from webui
    │   │   ├── main.py app_service.py store.py(大业务层，改为依赖 ozon_common 内核) …
    │   │   ├── server.py          # ← 原 run_api.py 端口选择启动器(console_script: webui.server:main)
    │   │   └── assets/ *.json seeds
    │   ├── scripts/               # 原 scripts/ + 收纳根目录游离脚本(fetch_*/compare_*/grab_*)
    │   ├── tests/                 # from backend → from webui
    │   ├── frontend/              # 原样不动(JS)
    │   ├── deploy/  data/
    │   └── 启动后端.bat            # 改为 uv run ozon-webui
    │
    └── image_worker/              # name = ozon-image-worker；依赖：ozon-common
        ├── pyproject.toml
        ├── src/image_worker/
        │   ├── __init__.py
        │   └── worker.py          # from ozon_common.*(原 6 个复制模块全删)
        └── Dockerfile             # 重写：uv + 构建上下文 = 仓库根
```

### 依赖图(单向无环)

```
ozon_common ◄──── webui ────► ozon_api
     ▲
     └──────────── image_worker
```

- worker 不再依赖 fastapi/uvicorn，Docker 镜像可精简。
- 改 db/oss/gen_image 等基础设施只改 `ozon_common` 一处，webui 与 worker 同时生效——彻底消除复制粘贴。

## 4. 共享内核边界(ozon_common)

| 来源模块 | 进 ozon_common | 说明 |
|---|---|---|
| db.py | ✅ 全量 | 以 backend 版(479 行)为准，worker 用到的为子集 |
| oss.py | ✅ 全量 | backend 版为准 |
| mq.py | ✅ 全量 | 含 publish(webui 投递)与 consume(worker 消费) |
| gen_image.py | ✅ 全量 | 纯逻辑，确认两版 prompt/config 无 worker 专属差异后以 backend 为准 |
| image_plan.py | ✅ 全量 | `build_image_plan` 纯函数 |
| store.py | ⚠️ 只抽内核 | 抽出：`utc_now_iso` / `dumps_json` / `loads_json` / `ai_config` / `oss_config` / `draft_images` 写入路径 → `ozon_common.settings` + `ozon_common.draft_images`。webui 的大 `store.py` 改为 import 这些内核；worker 也 import 同一份 |

**漂移核对(实现阶段逐模块执行)**：对 5 个基础设施模块逐一 `diff` backend↔worker 版本，以 backend 为 canonical 超集，确认 worker 当前用到的每个符号在 backend 版中存在且行为一致；若发现 worker 有专属行为差异，单独记录并在共享版中以参数/开关兼容，不静默丢弃。

## 5. 入口与命令

| 包 | console_script | 指向 | 开发跑法 |
|---|---|---|---|
| webui | `ozon-webui` | `webui.server:main`(原 run_api.py 的 main，已存在) | `uv run ozon-webui [port]` |
| image_worker | `ozon-worker` | `image_worker.worker:main`(已存在) | `uv run ozon-worker` |

- `启动后端.bat` 改为 `uv run ozon-webui`。
- `webui.server:main` 保留原有「WEBUI_HOST 设了就固定监听、否则自动挑端口」逻辑，仅把 `uvicorn.run("backend.main:app", ...)` 改为 `"webui.main:app"`。

## 6. 开发环境

- uv workspace 默认单一根 venv：根目录 `uv sync` → 生成一个 `.venv`，四包全部 editable 链接，改共享包即时生效。
- 现有为两个 app 各建的 `apps/*/.venv` 在切换到根 venv 后删除，避免两套环境混淆。
- 根 `.gitignore` 已忽略 `.venv/`；`scratch/`、`data/`、`products.db` 等保持忽略。

## 7. 部署 / Docker

两个镜像的构建上下文都改为**仓库根**(需要带上 `packages/`)。

**worker 镜像**（`apps/image_worker/Dockerfile`）：
- 多阶段 + uv；`uv sync --package ozon-image-worker --no-dev --frozen`，只解析 ozon_common+worker 这条依赖线，fastapi/uvicorn 等一律不进。
- `CMD ["uv", "run", "--package", "ozon-image-worker", "ozon-worker"]`。

**webui 镜像**（根 `Dockerfile`）：
- 改 uv；`uv sync --package ozon-webui`（含 ozon_api 与 ozon_common）。
- `ozon_api` 不再靠 `PYTHONPATH` 注入，变为正式 workspace 依赖。
- `CMD` 改为 `uv run --package ozon-webui ozon-webui`（保留 `WEBUI_HOST=0.0.0.0 WEBUI_PORT=8585`）。

**国内加速**：根 `pyproject.toml` 的 `[tool.uv]` 配置阿里云镜像 index，本地与 Docker 共用。

## 8. 迁移步骤（分步、每步可验证、各自成 commit）

0. **先提交当前 WIP**：分支 `feat/auto-listing-ai-pipeline` 有一批未提交改动(ai_card/app_service/store/db/gen_image/main 等)，先提交留干净基线，便于回滚。
1. **搭骨架**：根 `pyproject.toml`(workspace + [tool.uv] 镜像 + ruff)，空 `packages/`、`apps/` 目录。
2. **建 ozon_common**：迁 5 个基础设施模块 + 抽 store 内核(settings/draft_images)；逐一 diff backend↔worker，确认符号覆盖。
3. **建 ozon_api**：`git mv ozon_api → packages/ozon_api/src/ozon_api` + 加 pyproject + README。
4. **搬 webui**：`backend → apps/webui/src/webui`，批量 `backend.` → `webui.`，共享导入指向 `ozon_common`/`ozon_api`，ruff 校验；run_api.py → server.py。
5. **搬 worker**：删 6 个复制模块，导入指向 `ozon_common`，`worker.py → apps/image_worker/src/image_worker`。
6. **搬资产 & 配置**：frontend/deploy/data/scripts 迁入 apps/webui，收纳游离脚本；重写两个 Dockerfile、改 .bat；根 `uv sync`。

## 9. 验证闸门（每步后）

- 现有 `pytest`(webui/tests、ozon_api/tests)全绿。
- `uv run python -c "import webui.main; import image_worker.worker"` 通过。
- 冒烟：`uv run ozon-webui` 能起；`uv run ozon-worker` 能连(或 dry import)。
- `ruff check --select I packages apps` 干净。
- 两个 Docker 镜像能 build（worker 镜像确认不含 fastapi）。

## 10. 风险与回滚

- **大范围 git mv + import 重命名**：靠分步 commit + 每步 pytest/ruff 闸门控制；任一步失败可回退到上一步基线。
- **backend↔worker 漂移**：第 2 步逐模块 diff 核对，避免静默丢失 worker 专属行为。
- **路径引用遗漏**（vite/deploy/Docker/.bat 里的硬编码路径）：第 6 步集中排查并冒烟验证。
- **WIP 冲突**：第 0 步先提交现有改动作为基线。

## 11. 非目标（YAGNI）

- 不引入 poetry/pdm；不拆 CI（仓库当前无 CI 配置）。
- 不重构业务逻辑、不动 Vue 前端源码（仅可能调整其所在目录路径）。
- 不强行把 webui 的大 store.py 进一步拆分（只抽共享内核，其余留待后续按需重构）。
