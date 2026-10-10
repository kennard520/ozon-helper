# 备货发货（Fulfillment / FBS）

> FBS 订单的「采购 → 打单 → 发货」工作台。路由挂载于 `views/Fulfillment.vue`。
> 数据流：拉取 Ozon 待处理订单（postings）→ 按商品展开成采购行（procurement）→ 标采购状态 → 打面单 → 发货。
> 本文档随功能改动持续更新（交互 / 数据 / 规则三块）。

## 1. 交互（页面结构与操作流程）

页面自上而下四块（`views/Fulfillment.vue`）：

| 区域 | 组件 | 说明 |
|---|---|---|
| 页头 | `ui/SSectionHeader` | 标题「备货发货（FBS）」+ 副标题「FBS 订单：采购 → 打单 → 发货」；右侧 actions 槽放「拉取 Ozon 订单」按钮 |
| KPI 区 | `ui/SStatCard` ×4 | 待采购 / 待发货 / 今日截单 / 今日已发，四列等宽网格 |
| 分阶段 tab | `ui/STabs` | 待采购 / 待发货 / 已发货，带计数；点击切换表格过滤，active 下划线高亮 |
| 表格 | `el-table` | 按当前 tab 过滤后的采购行；空态显示 📭 图标 + 文案 |

**主流程**：
1. 点「拉取 Ozon 订单」→ 调 `fbsPull('awaiting_packaging', 14, store)` 同步近 14 天待打包订单，后端展开成采购行并刷新表格，页头下方提示「已同步 N 个订单，备货板 M 条」。
2. 在「待采购」tab 逐行下单采购，改「采购状态」下拉（待采购 / 已下单 / 已到货 / 已发货）。状态变为非「待采购」的行自动归入「待发货」tab。
3. 在「待发货」tab 对已备货的行点「发货」→ 二次确认弹窗（不可逆）→ 成功后该 posting 进入「已发货」tab，操作列变为「已发货」标签。
4. 「面单」按钮在任意阶段可用，新窗口打开真实 PDF 面单（`/api/fbs/label`）。

**KPI 计数口径**（前端 computed，基于当前店全量采购行）：
- **待采购** = 采购状态为「待采购」且未发货的行数（= 待采购 tab 计数）。
- **待发货** = 已采购（状态非「待采购」）且未发货的行数（= 待发货 tab 计数）。
- **今日截单** = 未发货且 `ship_by` 落在「今天」（本地时区按日期判定）的行数；> 0 时数字标红（`SStatCard :danger`）。
- **今日已发** = 本会话内点「发货」成功的累计次数（刷新页面归零，仅作当日参考；后端无逐日发货流水，不持久化）。

**分阶段判定**（`stageOf(row)`，优先级从高到低）：
- `shipped`（已发货）：本会话点过发货的 posting，或 `posting_status` 含 `deliver`/`shipped`/`sent`。
- `toBuy`（待采购）：`purchase_state === '待采购'`。
- `toShip`（待发货）：其余。

**ship_by 紧急度**（`shipByUrgency`）：
- `overdue`（已逾期，`ship_by < now`）：行底色浅红（`.row-overdue`），截止 tag 红色（danger）。
- `soon`（48h 内）：行底色浅橙（`.row-soon`），tag 橙色（warning）。
- `normal`：tag 灰色（info）。
- 无 `ship_by`：显示「—」。

**已发货留存**：后端 `pull_fbs` 默认只拉 `awaiting_packaging` 状态订单，采购行常驻不消失，但「已发货」这一事实由前端按会话标记（`shippedPostings` Set + doShip 成功后加入）。若后端将来也拉已发状态订单，`posting_status` 含 `deliver`/`shipped` 的行也会自动归入「已发货」tab（两条来源取并集）。

## 2. 数据（实体 / 接口 / 字段）

### 接口（`api.js` 前缀 `/api/fbs`，均带 `store_client_id` 查询参数）
| 方法 | 请求 | 响应 |
|---|---|---|
| `fbsPull(status, days, store)` | POST `/api/fbs/pull` `{status, days}` | `{synced, procurement[]}` |
| `fbsProcurement(store)` | GET `/api/fbs/procurement` | `{procurement[]}` |
| `fbsSetState(id, state, note, store)` | POST `/api/fbs/procurement/{id}/state` `{purchase_state, note}` | `{procurement[]}` |
| `fbsShip(posting, store)` | POST `/api/fbs/ship` `{posting_number}` | `{result[], shipped, response}` |
| `fbsLabelUrl(posting, store)` | GET `/api/fbs/label?posting=…` | `application/pdf`（真实面单，新窗口打开） |

### 采购行（procurement row）字段形状
后端 `OrderRepo.list_procurement`（`packages/ozon_common/.../repositories/order_repo.py`）返回，每行：

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` | procurement.id | 采购行主键，改状态用 |
| `posting_number` | procurement | Ozon 发货单号 |
| `offer_id` | procurement | 商品 offer_id |
| `qty` | procurement | 数量（前端显示 `×N`） |
| `purchase_state` | procurement | 待采购 / 已下单 / 已到货 / 已发货 |
| `supplier` / `purchase_url` / `cost_cny` / `note` | procurement（建行时从 drafts 带入） | 供应商 / 采购链接 / 成本¥ / 备注 |
| `ship_by` | LEFT JOIN postings | 截止发货时间（空串表示无） |
| `posting_status` | LEFT JOIN postings | 订单状态，前端分阶段用 |
| `title` | LEFT JOIN drafts（同 offer_id + 同店） | 商品标题：`ozon_title` 优先，空回退 `source_title`，查不到草稿则空串 |

**N+1 防护**：`list_procurement` 用单条 `PR outerjoin postings outerjoin drafts` 查询补齐 ship_by/status/title，不逐行查库。`offer_id` 在 drafts 是 Ozon 商品唯一标识，与采购行基本一对一；偶有同 offer_id 多草稿时按采购行主键 `id` 去重保第一条，避免 JOIN 放大行数。

### 采购行重建（`rebuild_procurement`）
`pull_fbs` 同步 postings 后调用：遍历本店 postings 的 `products_json`，按 `offer_id` 在本店 drafts 查 supplier/purchase_url/cost_cny 建/更新采购行；按 `(posting_number, offer_id)` UNIQUE 冲突 upsert，**保留已有行的 `purchase_state`/`note`**。

## 3. 规则与边界

- **发货不可逆**：`doShip` 必经二次确认（`confirmFn`，默认 `ElMessageBox.confirm`，取消则静默返回）。后端 `ship_posting` 用 `offer_id` 反查真实 `product_id`（绝不拿 sku 顶替），解析失败/无可发商品则抛错不发货。
- **采购状态下拉为受控单向绑定**：`row.purchase_state` 是唯一真相，仅服务端成功后才更新；失败时用新数组引用强制重渲染，下拉视觉回弹到旧值（无需手动回滚）。
- **切店重载**：`watch(store.currentStore)` 变化时重新拉当前店备货板；KPI / tab 计数随之重算。
- **设计系统**：用 `tokens.css` 变量 + `ui/` S-组件（SSectionHeader / SStatCard / STabs），不硬编码颜色；行底色用 rgba 高亮（el-table row 在 shadow DOM 外，故用非 scoped 样式）。
- **后端无数据不伪造**：
  - 配送方式的「中国发货仓地址 / 联系人 / 电话」后端无字段无数据源 → 不展示。
  - 商品缩略图：主图存于 `draft_images` 表（drafts 主表 `images_json` 实际为空），JOIN 成本高且性价比低 → 当前只补标题，**不展示缩略图**（符合「没有就省略，别伪造」）。
