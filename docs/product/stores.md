# 店铺管理（Stores）

> 视图文件：`apps/webui/frontend/src/views/Stores.vue`
> 状态来源：Pinia `apps/webui/frontend/src/stores/app.js`
> 后端店铺形状：`apps/webui/src/webui/services/_settings.py:68-72`
> 相关 API：`apps/webui/frontend/src/api.js`

「店铺管理」用于接入/维护多个 Ozon 店铺的凭证、查看连接状态、切换「当前操作店铺」，以及按店同步仓库。

---

## 一、交互

### 页头
- 标题「店铺管理」。
- 副标题明确：**切换当前操作店铺会与顶栏及各页面（草稿/仓库/订单）全局同步**。
- 右侧「+ 添加店铺」按钮 → 打开添加弹窗。

### 统计卡行（3 张 `SStatCard`）
- **已连接**：`connectedCount / 总数`（`api_key_saved` 为 true 的店数 / 全部店数）。
- **商品总数**：占位 `—`（后端暂无店铺级商品统计端点，**不伪造**）。
- **需处理**：`failedCount`（凭证未配置/失效的店数），>0 时红色高亮。

### 凭证失效告警条（`SAlert`，仅当存在失效店时）
- 文案提示 N 个店铺 API Key 未配置或失效。
- 「重新授权」按钮 → 取第一个失效店打开编辑弹窗。

### 店铺卡网格（每店一张 `SCard`）
卡头：头像 + 店名 + `Client ID` + 连接徽标（已连接 / 凭证失效）。

卡体三栏统计：
- **余额**：占位 `—`（后端无字段/端点，**不伪造**）。
- **商品**：占位 `—`（同上）。
- **仓库**：真值。已连接的店懒加载拉取 `GET /api/warehouses?store_client_id=<cid>`，取 `warehouses.length`；未连接或拉取失败保持 `—`。

卡体元信息：
- **API Key**：已连接显示脱敏 `••••••••` + `client_id` 后 4 位（**注意**：脱敏用的是 client_id 末 4 位，非真实 key 后 4 位——后端不回传 key，前端无法显示真实尾号）；未配置显示「未配置」。
- **状态**：默认店铺 / 普通店铺徽标。

卡底操作按钮：
- **当前店铺 / 设为当前**：当前操作店显示禁用态「当前店铺」；其余店显示「设为当前」→ 调 `store.setCurrentStore(client_id)` 全局切店。
- **同步**：拉取该店仓库 + 配送方式。`api_key_saved` 为 false 时禁用；点击后进入 loading，成功 toast「同步完成：N 个仓库」并刷新该店仓库数，失败 toast 报错。
- **编辑凭证**：打开编辑弹窗。
- **移除**：二次确认后从店铺列表删除（保留现状的二次确认）。

末尾「添加 Ozon 店铺」虚线卡 → 等价于「+ 添加店铺」。

### 添加 / 编辑弹窗（`ElDialog`）
字段：
- **店铺名称**（必填）。
- **Client ID**（必填；编辑态禁用，不可改主键）。
- **API Key**（密码框）：添加态必填；编辑态留空 = 不修改。下方安全提示「**凭证仅保存在本机，不上传服务器。**」。
- **接入后切换为当前操作店铺**（`ElCheckbox`，**仅添加态显示**，默认勾选）：勾选则添加成功后调 `store.setCurrentStore(新 client_id)`，把新店设为当前操作店。

底部：取消 / 添加（或保存）。保存中按钮 loading。

---

## 二、数据

### 后端店铺对象（`/api/state`、`/api/settings` 返回的 `settings.ozon_stores[]`）
仅含 4 个字段（`_settings.py:68-72`）：
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 店铺名 |
| `client_id` | string | Ozon Client ID（主键） |
| `is_default` | bool | 是否默认店 |
| `api_key_saved` | bool | 是否已存 API Key（**key 本身不回传**） |

> 后端 store 对象**没有** 余额 / 商品数 / 地区 / 接入日期 字段，也无对应端点 → 前端对这些一律渲染 `—`，不造数据。

### 持久化（保存设置）
- `persistStores(list)` → `POST /api/settings { ozon_stores: list }`（`api.saveSettings`），回写 `store.settings/status/paths`。
- 新增/编辑时，未改动的店只回传脱敏字段 `{ name, client_id, is_default }`（不带 key，避免覆盖）；新增店或改 key 的店才带 `api_key`。

### 仓库数 / 同步
- `GET /api/warehouses?store_client_id=<cid>`（`api.listWarehouses`）→ `{ warehouses: [...] }`，取 `.length`。
  - 前端缓存：`warehouseCounts[client_id]`；店铺列表变化（首次/增删/同步）触发 `watch` 批量并发拉取，已缓存的跳过。
- `POST /api/warehouses/sync?store_client_id=<cid>`（`api.syncWarehouses`）→ `{ synced, delivery_methods, warehouses }`，用 `warehouses.length` 刷新该店仓库数。

### 当前操作店（全局状态，`stores/app.js`）
- `currentStore`（client_id 字符串）：店铺级操作（草稿过滤、仓库、订单、发布默认目标）的上下文。
- `setCurrentStore(cid)`：写入 + 持久化到 `localStorage('current_store')`、清空草稿选中、重置分页、重新拉草稿。
- `ensureCurrentStore()`：登录加载后选定当前店（已选且仍在列表保留；否则取 localStorage；再否则默认店/列表首个）。

---

## 三、规则

- **多店凭证仅存本机**：API Key 仅保存在本地后端的 settings，不上传到任何远端服务器（弹窗安全提示对应此事实）。
- **第一个接入的店自动成为默认店**（`is_default = 列表为空`）。
- **编辑时 Client ID 不可改**（主键，禁用输入）；API Key 留空表示保留原值。
- **同步前置**：店未配置/失效（`api_key_saved=false`）时「同步」按钮禁用，点击编辑/重新授权先补凭证。
- **占位即真相缺失**：余额/商品/地区/接入日期、以及 API Key 真实尾号——后端无数据，一律占位，禁止伪造。
- **切店全局生效**：「设为当前」与「接入后切换」均通过 `setCurrentStore` 触发，顶栏与各页面（草稿/仓库/订单）随之同步。
