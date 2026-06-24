# 变体组工作台（Variant Group Workspace）设计

日期：2026-06-24
分支：feat/auto-listing-ai-pipeline

## 背景与目标

1688 多变体商品（如油桶：多容量/材质/款式）采集后，每个 SKU 变体存成**一张独立草稿**（靠 `source_raw.variant_group` 归一，靠 `#sku=` 唯一化 source_url）。现状痛点：

- 列表里 N 个变体 = N 行，列表被撑长、找货难。
- 同一商品的 23 个变体，**每个都要手点一遍**「识别类目 → AI 填特征 → 文案 → 图集 → 上架」= 23 倍重复操作。
- 变体功能半成品（变体条已加，但无批量、无组管理）。

**关键约束（用户确认）**：变体之间**不共享**。每个变体有自己的图片（图上印了各自的重量/尺寸）、克重、尺寸、价格、属性。因此不能做「主信息编一次同步全组」。

**目标**：把同组变体当「一个商品」来组织和**按步骤一键批量处理**，但每个变体仍完全独立编辑。把「23 遍手点同一步」压成「每步点 1 次批量」。

## 设计决策（来自头脑风暴）

- 列表：每个 `variant_group` **折叠成一条代表记录**（一商品一卡）。
- 详情：**变体表格**，每行一个变体，显示各步骤完成状态徽标 + 基础信息；点行进**该变体的完整编辑器**（所有字段独立，不共享）。
- 批量动作（勾选子集或全选）：批量识别类目 / 批量填特征 / 批量生成文案 / 批量出图 / 全部上架 / 上架选中 / 删除选中。
- **出图批量**因较贵（23×10 张），**默认不进「全批量自动」**，单独按需触发。
- 上架语义：单个 = 发该变体草稿（Ozon 按型号名 9048 自动并到同组卡）；多/全 = `publish_variant_group`（扩展为可传选中子集）。
- 删除：**只删本地草稿，不碰 Ozon**（已发布的留在 Ozon，用户自行后台处理）。
- **变体重新分组（双向拖拽）**：1688 常把不该算变体的塞成 SKU，也可能漏并。支持「拖出去=脱离组独立成卡」「拖进来=并入某组」。非破坏，数据全留。

## 架构与组件

### 数据层（store / db）

1. **`variant_group` 提升为 drafts 列**（当前埋在 `source_raw_json`，无法在 SQL 里按组折叠分页）。
   - 加列 `variant_group VARCHAR(191) NOT NULL DEFAULT ''`（复用 `_ensure_mysql_column` / SQLite `_ensure_column` 既有加列模式）。
   - 建索引 `idx_drafts_variant_group (user_id, variant_group)`。
   - `insert_draft` / `update_draft` 时从 `source_raw.variant_group` 同步写该列。
   - 启动迁移：回填存量草稿的该列（从 source_raw_json 解析）。

2. **列表折叠**（`list_drafts_page`）：每个非空 `variant_group` 只返回**代表行**（组内 `MIN(id)`），无组的草稿照常返回。代表行附 `variant_count`（组内草稿数）。
   - 实现：`WHERE ... AND (variant_group = '' OR id = (SELECT MIN(d2.id) FROM drafts d2 WHERE d2.variant_group = drafts.variant_group AND <相同 user/store/status 过滤>))`，再套 LIMIT/OFFSET。
   - 代表行的 `variant_count` 用子查询 COUNT。
   - 注意：status 过滤下，代表行取「该 status 过滤后组内 MIN(id)」，count 也按同过滤。

3. **`count_by_status`** 同步：一组算一条（按 variant_group 去重计数；无组的逐条）。

### 服务层（app_service）

- `variant_group_workspace(group, store?)` → 返回组内全部变体 + **每变体每步完成状态**（均为本地字段轻量推导，不跑网络校验）：
  - `category`：`category_id` 且 `type_id` 非空。
  - `attrs`：草稿 `attributes` 里**有效属性数 > 写死默认项数**（默认项=型号名 9048 / 品牌 85 / 标签 23171），即「除了自动塞的，还填了别的」。
  - `copy`：`ozon_title` 且 `description` 非空。
  - `images`：图片张数（徽标显示数字；≥3 视为基本就绪，仅用于徽标颜色，不阻断）。
  - `published`：`status == 'published'` 或有 `publish_response`。
  - 另含：id、spec（区别规格）、price、weight_g、尺寸、首图、status。
- `publish_variant_group(group, store?, model_name?, ids?)`：**扩展可选 `ids`**——只发选中子集（默认全组）。
- `set_variant_group(draft_id, target_group)`：**重新分组原子操作**（拖拽底层）。
  - `target_group=''`（拖出/独立）→ 清空该草稿 `variant_group`（列+source_raw），把型号名 9048 重置为新随机 `M-xxxx`（不再被 Ozon 并回组）。
  - `target_group=X`（拖入某组）→ 设 `variant_group=X`，型号名 9048 设为 `X`（组内一致→Ozon 合并）。
  - 把两个独立草稿并成新组：生成一个新 `variant_group` id（如 `grp-<8位>`），两者都设过去。
  - 非破坏：图/价/属性原样保留。
- 批量删除：**前端循环复用现有 `DELETE /api/drafts/{id}`**，不新增批量端点（简单、逐个可控）。

### 批量执行（前端编排，复用现有单步端点）

各步骤已有**单草稿端点**（recognize-category / ai-fill-attributes / ai-copy / generate-plan-slot 等）。批量 = **前端按勾选的变体 id 循环调用，带并发池 + 组级进度**（参照已实现的 `runAutoImages` 并发池）：

- 并发上限（如 3-4），避免打爆 AI 网关。
- 单个变体某步失败 → 标记该变体失败、继续其余，最后汇报「成功 N/总数」。
- 进度展示在工作台顶部（如「批量填特征 7/23…」）。
- 利用已实现的「loading 按草稿持久化」：切走再回进度不丢。
- （未来增强：移到后端后台任务 + 轮询，更抗页面刷新；本期先前端编排，复用已测端点。）

### 前端组件

- **列表（Collect.vue / 列表项）**：代表行显示「🔗 ×N 变体」徽标；点开进入工作台（或仍进 DraftDetail，但顶部是工作台视图）。
- **`VariantWorkspace.vue`（新）**：变体表格
  - 行：勾选框 + 变体名(spec) + 首图 + 价格 + 克重 + 尺寸 + 状态徽标(类目/特征/文案/图集/上架) + 行操作(编辑/上架/删除)。
  - 表头：全选；批量按钮（识别类目/填特征/文案/出图/全部上架/上架选中/删除选中）；进度条。
  - 点「编辑」或行 → 进该变体的 `DraftDetail`（完整编辑，独立）。
  - 数据来自 `variant_group_workspace` 接口（不受列表折叠分页影响）。

### 路由（main）

- **升级已有** `GET /api/drafts/{id}/variant-group` → 返回带每步状态的工作台数据（`variant_group_workspace`）。
- `POST /api/ext/publish-group` 扩展 body 接受可选 `ids`（选中子集）。
- 批量删除：前端循环复用 `DELETE /api/drafts/{id}`（不新增批量端点）。
- **新增** `POST /api/drafts/{id}/variant-group` body `{ target_group }` → `set_variant_group`（拖出=空、拖入=目标组 id）。

### 变体重新分组（双向拖拽）

底层就一个原子操作 `set_variant_group`，UI 用拖拽触发：

- **拖出（detach）**：在工作台把某变体行拖到「独立区」/拖出组，或点行内「踢出组」→ `set_variant_group(id, '')` → 它在列表里单独成卡。
- **拖入（attach/merge）**：在左侧列表把一个独立商品卡**拖到某变体组卡上** → `set_variant_group(独立id, 目标组)` → 并入该组。
  - 拖到的目标本身是独立卡（无组）→ 生成新 `variant_group` 把两者并成一组。
- **组间移动**：从 A 组工作台把变体拖到 B 组 = 直接 `set_variant_group(id, B)`（=先脱 A 再入 B，一步到位）。
- 交互：用 HTML5 DnD 或轻量拖拽；**每个拖拽都有按钮兜底**（「踢出组」行操作 / 「并入组…」选择目标），避免纯拖拽在长列表里难操作。
- 拖完刷新列表折叠 + 工作台。

## 数据流

1. 采集 → N 变体草稿（variant_group 同步进列）。
2. 列表 → 折叠查询 → 一组一卡（带 count + 徽标）。
3. 点卡 → 工作台拉 `variant_group_workspace` → 表格 + 状态。
4. 勾选 + 批量按钮 → 前端并发池循环单步端点 → 进度 → 刷新状态。
5. 点行 → DraftDetail 编辑单个变体。
6. 上架：单个=发该变体；多/全=publish_variant_group(ids)。
7. 删除：逐个 delete_draft → 刷新（删光则列表那卡消失）。

## 边界与错误处理

- 代表行被删 → 列表下次查询自动用新的 MIN(id) 代表。
- 删到组内剩 1 个 → 仍按组展示（或退化单品；variant_group 保留，列表仍一卡 ×1）。
- 批量步骤部分失败 → 不中断，逐项标记，最后汇总。
- variant_group 列与 source_raw 不一致（历史数据）→ 以迁移回填为准，update 时持续同步。
- status 过滤（如只看「待发布」）与折叠：代表行/计数都按过滤后的组内成员算。

## 测试

- store：variant_group 列回填、insert/update 同步、折叠查询（混合 有组/无组、跨状态过滤）、count_by_status 按组去重。
- app_service：variant_group_workspace 状态推导（各步齐全/缺失）、publish_variant_group 子集 ids、set_variant_group（拖出清组+9048重置随机、拖入设组+9048=组、两独立并新组）。
- 前端：工作台表格渲染、批量并发池（部分失败汇总）、勾选/全选、删除后刷新。
- 回归：现有 505 用例全过。

## 分期（可选）

- **一期**：列表折叠 + 工作台表格（状态总览）+ 全部/批量上架 + 批量删除 + 批量识别类目/填特征/文案。
- **二期**：批量出图（带费用提示）+ 工作台行内精细编辑（价格/库存直接改）。

## 不做（YAGNI）

- 不做「主信息共享同步」（用户明确变体不共享）。
- 不做从 Ozon 下架（删除只动本地草稿）。
- 不做变体在卡内的拖拽**排序**（只做分组归属，不做组内顺序）。
