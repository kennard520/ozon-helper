# 设计：Admin 用户管理 + 店铺配额

- 日期：2026-06-19
- 状态：已实现并上线（2026-06-19）
- 影响范围：`ozon-listing-webui` 后端（FastAPI）+ 前端（Vue），部署在服务器（MySQL）

## 背景 / 问题

当前 `POST /api/auth/register` **完全开放、无鉴权**：任何人都能自助注册账号（`role=user`），8585 端口对公网开放后会被陌生人注册并共用本店的 OSS 等资源。需求：

1. **关闭开放注册**，账号只能由 **admin** 创建。
2. admin 能在网页管理用户：列出 / 创建 / 改最大店铺数 / 重置密码 / 禁用启用。
3. admin 给每个用户设 **最大店铺数（max_stores）** 配额，用户加店不能超过上限。

## 目标

- 普通访客无法再自助注册。
- admin 在网页"用户管理"完成全部账号操作。
- 每用户独立的店铺数上限，超限时**后端**拒绝加店。

## 非目标

- 不做邮箱验证 / 找回密码 / 邀请码等注册流程。
- 不改动现有店铺隔离（user_id / store_client_id）机制本身。

> 实现后调整（2026-06-19）：原定"只禁用不删除"已按用户要求改为**同时支持硬删除**（级联删该用户全部数据，前端危险二次确认）；用户管理也从"设置页卡片"改为**独立页面**。下文已同步。

## 安全原则（重点）

**所有权限控制在后端强制，前端隐藏只是 UX。**
- 每个用户管理接口都要求 admin 登录（`require_admin` 依赖，校验 JWT 对应用户 `role == 'admin'`）。非 admin 调用一律 `403`。
- 店铺配额在后端保存设置时强制校验，前端绕过也无效。
- 删除公开注册路由，前端入口同步去掉。

## 数据模型

`users` 表新增一列：

| 列 | 类型 | 说明 |
|---|---|---|
| `max_stores` | `INT NOT NULL DEFAULT 1` | 该用户最大店铺数；admin 豁免 |

复用已有列：`role`（`admin`/`user`）、`status`（`active`/`disabled`）。

**迁移（关键）**：MySQL 的 `init_mysql` 用 `CREATE TABLE IF NOT EXISTS`，不会给已存在表加列，需要单独"确保列存在"逻辑（查 `information_schema.COLUMNS`，缺则 `ALTER TABLE users ADD COLUMN max_stores INT NOT NULL DEFAULT 1`）。SQLite 沿用现有 `_ensure_column`。现有用户：`admin`(role=admin) 豁免；`admin_screenshot`(role=user) 用默认值 1。

## 配额规则

- **店铺数口径**：用户 `settings.ozon_stores`（经 `normalize_stores` 后的全部店，含主店）的数量。
- **校验点**：保存设置处理 `ozon_stores` 的地方（`app_service.py` 约 339 行的设置保存逻辑）。当 `role != 'admin'` 且新的 `ozon_stores` 数量 > 该用户 `max_stores` 时，抛错 → `400`，文案："最多 N 个店铺，请联系管理员调整上限"。
- **admin 豁免**：`role == 'admin'` 不校验店铺数。
- 仅在"增加到超过上限"时拒绝；不影响已有超额数据的读取（理论上不会出现，因创建受控）。

## 后端接口

新增 `require_admin` 依赖（基于现有 `get_current_user` + `role == 'admin'`，否则 403）。

| 方法 | 路径 | 鉴权 | 行为 |
|---|---|---|---|
| `GET` | `/api/admin/users` | admin | 列出用户：`id, username, role, status, max_stores, store_count`（store_count = 该用户 ozon_stores 数量）|
| `POST` | `/api/admin/users` | admin | 创建用户：入参 `username, password, max_stores`；用户名≥3、密码≥6、查重；`role=user, status=active` |
| `PATCH` | `/api/admin/users/{id}` | admin | 按传入字段更新：`max_stores` / `status`(active/disabled) / `password`(重置)；至少传一项 |
| `DELETE` | `/api/admin/users/{id}` | admin | 硬删除：级联删该用户 user_id 关联数据（草稿/钱包/流水/设置）+ 其店铺的仓库/订单/采购/快照。防自锁：不能删自己、不能删管理员 |

其它后端改动：
- **删除** 公开的 `POST /api/auth/register` 路由，并删除 `App.register` 方法（建用户统一走 `POST /api/admin/users`，不再有任何匿名注册入口）。
- **登录** `App.login` 增加 `status == 'active'` 校验；非 active 报"账号已禁用"。
- `store` 层新增/调整方法：`list_users()`、`create_user(..., max_stores)`、`set_max_stores(id, n)`、`set_status(id, s)`、`set_password_hash(id, h)`、`delete_user(id)`（级联）。
- admin 不能把自己禁用 / 不能禁用最后一个 admin；不能删除自己 / 不能删除管理员（防自锁）。

## 前端

- **独立的「用户管理」页**（`views/Users.vue`），入口在右上角账号下拉菜单（⚙️设置 旁），**仅 admin 可见**；普通用户看不到、后端也 403 挡住。
  - 用户表格：用户名、角色、状态、最大店铺数、当前店数、操作按钮。
  - 创建表单：用户名 + 初始密码 + 最大店铺数。
  - 行内操作：改最大店铺数、重置密码（Element 弹窗）、禁用/启用、**删除（危险二次确认；admin 行不显示删除）**。
- `api.js`：移除 `register`，新增 `adminListUsers / adminCreateUser / adminUpdateUser / adminDeleteUser`。
- 去掉登录页的注册入口。
- 加店保存设置时，后端返回的配额错误（400）在前端弹出可读提示。

## 默认决策（已与用户确认）

- 新用户 `max_stores` 默认 **1**（admin 建号时可改）。
- admin **豁免**店铺配额。
- 删除：支持**硬删除**（连同该用户全部数据，不可逆，前端危险二次确认），同时保留"禁用"作为可恢复的软停用；不能删自己/管理员。

## 测试

后端：
- 非 admin（或无 token）访问 `/api/admin/*` → 403。
- admin 创建用户成功；用户名重复 → 400；密码<6 → 400。
- `PATCH` 改 max_stores / 重置密码 / 禁用，分别生效。
- 禁用的用户登录 → 失败。
- 普通用户保存 `ozon_stores` 超过 max_stores → 400；admin 不限。
- admin 不能禁用自己 / 最后一个 admin。
- 硬删除用户级联删其草稿等数据；不能删自己 / 不能删管理员。

前端：
- 非 admin 看不到"用户管理"入口（即使手动调接口也被后端 403 挡住）。

## 部署 / 迁移

- 改前后端 → 本地构建前端 dist → 重建镜像 → 重启 `ozon-webui` 容器。
- 容器启动时 `users` 表自动补 `max_stores` 列（MySQL ALTER 探测 / SQLite _ensure_column）。
