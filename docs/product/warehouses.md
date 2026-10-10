# 仓库管理（Warehouses）

> 「仓库」页：展示**当前店铺**从 Ozon 同步下来的 FBS / realFBS 仓库及其配送方式，并允许设置默认仓库。
> 卡片式面板（`apps/webui/frontend/src/views/Warehouses.vue`）。仓库数据只读，唯一可写操作是「设为默认仓库」。

## 1. 交互

### 页面结构（自上而下）
1. **页头**（`SSectionHeader`）：
   - 标题「仓库」；副标题「仅本店铺 · 从 Ozon 同步的 FBS / realFBS 仓库与配送方式」。
   - 右上角操作：**从 Ozon 同步仓库** 按钮（`SButton`，同步中 loading）。
2. **汇总条**（两张 `SStatCard`，最多 2 列）：
   - **启用仓库** = `状态为 created 的仓库数 / 仓库总数`。
   - **realFBS 仓库** = `is_rfbs=true` 的仓库数。
   - ⚠️ **不渲染库存合计 / 缺货 SKU**——后端无对应字段，绝不伪造。
3. **仓库卡网格**（`SCard`，2 列富卡片，`auto-fill minmax(420px, 1fr)`）。每仓一张卡。
4. **空态**：当前店铺无仓库时显示虚线占位卡，提示点击「从 Ozon 同步仓库」。

### 每张仓库卡
- **卡头**：仓库图标（🏬）+ 名称 + 仓库 ID + 两个徽章：
  - **类型徽章**（`SBadge`）：`realFBS`（warn 配色）/ `FBS`（info 配色）。
  - **状态徽章**（`SBadge`）：胶囊 + 圆点 + 颜色——`启用`（绿点 + success）/ `停用`（灰点 + neutral）。
- **卡体**：
  - **默认仓单选**：`<input type=radio>`，选中即调 `set_default_warehouse`。选中态卡片高亮 + 显示「默认」徽章；文案在「设为默认仓库 / 默认仓库」间切换。
  - **上次同步**：`fetched_at` 格式化为 `MM-DD HH:mm`（无则显示 `—`）。
  - **配送方式折叠区**：默认收起，标题显示「配送方式（N）」+ 折叠箭头；展开后逐条列出技术字段（见 §2）。
- **停用仓卡片**：整卡 `opacity: 0.6` 半透明。

### 行为约定
- **切店**：监听 `store.currentStore`，切换即重新拉取当前店仓库（`immediate`）。
- **同步**：调 `api.syncWarehouses(currentStore)`，成功提示「同步成功，共 N 个仓库 / M 个配送方式」，并用返回结果刷新列表。
- **设默认**：调 `api.setDefaultWarehouse(warehouse_id, currentStore)`，用返回结果刷新列表（单选语义，后端保证全店唯一默认）。
- 折叠区开合是**纯前端 UI 状态**（`expanded` map by `warehouse_id`），不持久化。

## 2. 数据

### 接口
| 操作 | 方法 | 返回 |
| --- | --- | --- |
| 列出仓库 | `api.listWarehouses(store_client_id)` | `{ warehouses: [...] }` |
| 从 Ozon 同步 | `api.syncWarehouses(store_client_id)` | `{ synced, delivery_methods, warehouses: [...] }` |
| 设默认仓 | `api.setDefaultWarehouse(warehouse_id, store_client_id)` | `{ warehouses: [...] }` |

### 仓库实体字段（后端真有）
`warehouse_id` / `name` / `is_rfbs`(bool) / `status`(如 `created`) / `is_default`(bool) / `fetched_at`(时间戳) / `store_client_id` / `delivery_methods[]`。

### 配送方式 `delivery_methods[]` 字段（折叠区渲染，按需显示，空则跳过）
`name` / `is_express`(bool→express 徽章) / `status` / `tpl_integration_type`(集成类型) / `cutoff`(截单) / `provider_id`(承运商) / `dropoff_name`(自提点) / `dropoff_code`(编码) / `dropoff_address`(地址) / `dropoff_lat` + `dropoff_lng`(坐标)。

## 3. 规则 / 边界

- **数据只读**：仓库与配送方式均由 Ozon 同步而来，本页不可编辑，唯一写操作是设默认仓。
- **状态判定**：`status === 'created'` 视为启用（绿点）；其余值或缺失视为停用（灰点）/未知。
- **默认仓单选**：同一店铺仅一个默认仓，由后端 `set_default_warehouse` 保证；前端按 `is_default` 渲染选中态。
- **类型徽章**：`is_rfbs` 决定 realFBS / FBS，配色区分（warn / info）。
- **后端无数据的字段一律不渲染（不编造）**：地区(region)/在架商品数(sku)/库存(stock)/缺货(low)/中国仓地址/联系人/电话——均无对应后端字段，本页**不展示也不占位伪造**。汇总条同理只统计真有的「启用数 / 总数」与「realFBS 数」。

## 4. 设计系统

- 沿用 `apps/webui/frontend/src/styles/tokens.css` + `src/ui/` S-组件：`SSectionHeader` / `SStatCard` / `SCard` / `SBadge` / `SButton`。
- 颜色、间距、圆角、字号全部走 CSS 变量（`--c-*` / `--sp-*` / `--r-*` / `--fs-*`），无硬编码色值。
- 卡网格布局与 [店铺管理](../../apps/webui/frontend/src/views/Stores.vue)（`Stores.vue`）保持一致风格。
