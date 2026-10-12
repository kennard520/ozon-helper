# Ozon 本地精简模式实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个本机服务完成 WB/Ozon 采集、草稿编辑及手动发布。

**Architecture:** 复用现有 WebUI 和插件，用运行时开关控制本地模式。SQLite、网页和插件共享现有用户体系，普通模式保持兼容。

**Tech Stack:** Python、FastAPI、SQLAlchemy、SQLite、Vue 3、Pinia、Chromium MV3。

**Spec:** `docs/superpowers/specs/2026-10-10-local-lite-design.md`

## 执行结果（2026-10-10）

四项功能任务已实现。用户选择由主代理直接执行，最终独立只读审查发现的 3 个问题均已修复并增加回归测试。

- 基线完整后端测试：876 通过、7 失败。其中 6 个 AI 类目失败在 `main` 基线同样复现；另一个静态目录失败因测试与前端首次构建同时运行，构建完成后单项复测通过。
- 排除上述 3 个已有 AI 测试文件后，864 项后端回归通过；最终改动后本地/WB/媒体测试 36 项、发布相关 42 项通过。
- 最终前端 255 项、扩展 165 项通过；生产构建和 PowerShell 语法检查通过。
- 隔离 HTTP 验证通过登录、模式状态、采集后不自动发布、编辑保存；一键精简启动在 8585 成功托管页面。
- 真实 WB/Ozon 官网会话采集、卖家图片上传和实际上架未验证，需要用户的浏览器卖家登录与店铺 API 凭证。

Ruling: 使用明确的本地/远程插件选项，保留未选择模式时的远程默认值，以免改变已有用户连接；本地选择不远程回退。

Ruling: 本地不发布视频和富文本，将源内容保存在 collected_video_url / collected_rich_content_json，避免隐藏的媒体造成无 OSS 发布阻断。

Ruling: 保留现有登录体系及 admin/admin 首次账号；不新增免登录接口。Git 基线采用现有目录初始化，未创建额外 worktree，符合用户保留基线并切分支的授权。

以下为原始任务清单，步骤级勾选不作为验证证据；实际验证以本节结果和测试日志为准。

## Global Constraints

- 开发分支 `feat/local-lite`，`main` 保留基线 `76dad9e`。
- `OZON_LOCAL_LITE=1`；核心流程不调用 MCP、RabbitMQ、图片 worker 或 AI 服务。
- 默认监听 `127.0.0.1:8585`；沿用现有候选端口处理端口冲突。
- 本地精简版使用独立 SQLite 数据文件，不读取原 `.env.local`。
- 沿用 JWT，零发布费用，关闭采集后自动发布。
- 图片必须是 Ozon 可读取的地址；提交成功不等于上架成功。
- 使用 `python -m uv`，默认测试排除 `*_live.py`；不提交秘密或实际采集数据。
- 功能文档随改动更新；真实店铺发布不作为自动测试的一部分。

## Review Focus

1. 继承 MySQL、WEBUI_HOST 环境变量时仍只使用本地库与回环监听（任务 1）。
2. 插件配置本地但服务未启动时不连接远程服务器（任务 2）。
3. 已保存 auto_publish 和发布费用时，本地模式仍不能自动发布或扣费（任务 3）。
4. 采集创建的草稿不在当前分页时，编辑器仍能定位（任务 2、4）。
5. 编辑未保存或媒体上传失败时，不能误显示发布成功（任务 3、4）。

## Task 1：模式、隔离数据与启动

**Files:** 新增 `packages/ozon_common/src/ozon_common/runtime.py`、`start-lite.ps1`、`start-lite.bat`；修改 `packages/ozon_common/src/ozon_common/dal/engine.py`、`apps/webui/src/webui/server.py`、`apps/webui/src/webui/services/_settings.py`；新增 `apps/webui/tests/test_local_lite.py`。

**Interfaces:** `ozon_common.runtime.is_local_lite() -> bool` 动态读取环境变量；`/api/state` 增加 `runtime: {local_lite: bool}`；使用已有 `OZON_WEBUI_DB` 设置独立数据路径。

- [ ] 编写失败测试：`test_local_lite_forces_sqlite`（有 MySQL env 时 URL 仍以 sqlite 开头）、`test_normal_mode_preserves_mysql`、`test_local_lite_runtime_state`、`test_local_lite_binds_loopback`（继承 WEBUI_HOST 时仍绑定 127.0.0.1）。
- [ ] 运行 `python -m uv run python -m pytest apps/webui/tests/test_local_lite.py -q`，确认新增行为尚未实现。
- [ ] 实现动态模式函数及数据库选择，不在模块导入时固化开关；状态响应返回模式字段。
- [ ] 实现精简启动入口，只加载 `.env.lite.local`，设置独立库路径、模式和回环监听；原生命令非零退出立即终止。打开浏览器的时机放在端口确定且服务健康检查通过后；超时显示启动错误。
- [ ] 重跑新增测试；解析 PowerShell 语法，使用临时配置验证失败退出，不读取真实凭证。
- [ ] 更新 `docs/local-run.md`，提交 `feat(app): add isolated local lite startup`。

## Task 2：插件本地连接与采集定位

**Files:** 修改 `ozon-seller-helper-ext/background.js`、`common/bridge.js`、`popup/popup.html`、`popup/popup.js`、`common/collect-flow.js`；新增 `tests/local-backend.test.js`；修改现有连接与采集测试。

**Interfaces:** 插件保存 `ozon_backend_mode`（`local` 或 `remote`）。本地模式只访问候选回环端口；明确的自定义地址沿用现有 `ozon_backend_base`。`openEditor` 携带草稿 ID，由任务 4 的页面定位。

- [ ] 编写失败测试：`local mode never probes PROD_BASE`、`unreachable explicit override does not fall back`、`local collect opens editor with created draft id`；原远程连接用例保留。
- [ ] 在扩展目录运行 `npm test -- --run`，确认新行为对应测试失败。
- [ ] 增加可见本地/远程连接选项；地址或模式改变时清理发现缓存与旧登录状态，避免携带远程 JWT 操作本地用户。
- [ ] 收口发现逻辑，选本地后绝不自动远程回退；采集错误保留实际响应内容，仍允许 WB 缺价格后人工填写。
- [ ] 验证采集和草稿 ID 传递，媒体沿用现有卖家上传；失败反馈区分后端、登录、汇率、源站和媒体问题。
- [ ] 重跑扩展测试，更新扩展 README 的安装路径、连接和卖家登录说明，提交 `feat(ext): support explicit local collection mode`。

## Task 3：手动发布与媒体就绪

**Files:** 修改 `apps/webui/src/webui/services/_auth.py`、`_ext.py`、`_publish.py`；扩展 `apps/webui/tests/test_local_lite.py` 和已有 `test_auto_publish.py`、`test_publish_media_url.py`。

**Interfaces:** 本地 `publish_fee() -> float` 返回 0；自动发布入口在精简模式直接跳过；采集响应 `auto_publish` 始终为 false。沿用现有发布响应，保留 task_id 和平台结果。

- [ ] 编写失败测试：`test_local_lite_publish_fee_is_zero`（保存费用大于 0 仍返回 0）、`test_local_lite_collect_never_auto_publishes`（配置 auto_publish=true 仍不调发布）、`test_local_lite_media_callback_never_auto_publishes`、`test_local_lite_rejects_local_media`。
- [ ] 运行本地模式与上述已有测试，确认新增行为尚未实现。
- [ ] 在采集、媒体回调和发布扣费入口统一使用任务 1 的模式函数；普通模式仍采用原设置。
- [ ] 沿用现有媒体验证；原生 Ozon 图直用，WB 图片通过已有卖家媒体库或 OSS；上传未完成时展示错误并拦截发布。
- [ ] 对异步发布响应确认任务结果映射，区分提交与最终成功；以模拟 Seller API 覆盖处理中和失败，不实发商品。
- [ ] 重跑相关后端测试，更新工作台与素材库产品文档，提交 `feat(app): enforce manual free publishing in local mode`。

## Task 4：精简工作台与首次使用

**Files:** 修改 `apps/webui/frontend/src/stores/app.js`、`router/index.js`、`layouts/AppLayout.vue`、`AppSidebar.vue`、`AppTopBar.vue`、`views/Workbench.vue`、`views/Settings.vue` 和工作台编辑组件；扩展 `views/workbench.test.js`，新增 `src/local-lite.test.js`。

**Interfaces:** Pinia `runtime.local_lite` 默认为 false，由 `/api/state` 写入；`localLite` getter 供组件和路由使用。采集定位通过编辑器 URL 的草稿 ID 加载数据，兼容原链接。

- [ ] 编写失败测试：本地导航只有草稿/店铺/设置、直接访问未开放路由回到工作台、无 PipelinePanel 与 AI/钱包入口；普通模式维持现有入口。
- [ ] 编写分页定位测试：新采集 ID 不在列表页仍能加载并选中；发布测试覆盖处理中不显示已发布、媒体错误可见、当前编辑保存后才提交。
- [ ] 前端目录执行 `npm run test -- --run`，确认新增行为未实现。
- [ ] 实现运行时模式状态与路由检查，避免首次加载模式尚未确定便放行受限路由。
- [ ] 精简工作台保留必需编辑项与明确的当前商品手动发布按钮；保留变体选择，不强制先跑 AI。发布结果使用任务 3 的状态语义。
- [ ] 设置页隐藏无关服务配置，保留店铺 API、汇率、可选 OSS；显示浏览器扩展安装及 WebUI/插件登录指引，不引入免登录接口。
- [ ] 运行前端测试和 `npm run build`；使用可用浏览器检查草稿空态、编辑和发布提示，更新 `docs/product/workbench.md`、`stores.md` 与本地使用文档。
- [ ] 提交 `feat(app): add minimal local listing workbench`。

## 最终验证

- [ ] 运行后端 `python -m uv run python -m pytest apps/webui/tests packages --ignore-glob='*_live.py' -q`；失败先分辨基线与本次改动，不把未通过称为通过。
- [ ] 运行前端、采集扩展测试及前端构建；已通过检查只有新增改动时才重复。
- [ ] 启动独立 SQLite 精简实例，检查首页、state、采集、草稿保存及模拟发布，确认只需一个服务。
- [ ] 核查 Git diff、提交列表和敏感文件排除，保留 `main` 基线；不推送、不合并、不向真实店铺自动发布。
- [ ] 报告可用入口、测试结果，以及真实网站采集/店铺发布尚未验证的部分。
