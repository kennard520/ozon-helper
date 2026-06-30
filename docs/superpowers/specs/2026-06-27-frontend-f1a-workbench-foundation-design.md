# 前端重建 F1a:变体工作台地基(外壳 + 状态脊柱 + 草稿列表 + 变体卡)— 设计

- 日期:2026-06-27
- 所属:前端重建 F1(变体工作台,拆 `DraftDetail.vue` 2992 行 god-component)的第一块。F1 拆为 F1a(地基)→ F1c(AI 流水线)→ F1d(详情 tab)。本 spec 仅 F1a。
- 前置:F0 已完成(设计系统 `src/ui/`、外壳、vue-router、tokens)。
- 原型:`C:\Users\42918\Desktop\右侧变体卡片展示设计\变体工作台.dc.html`(本地 server 渲染对照)。

## 为什么 F1a 是"地基"而非"骨架+列表"
F1 的本质是换交互模型:从"单草稿编辑器"换成"**变体组工作台**"——左列表选中 → 定位变体组 → 右栏变体卡多选 → (后续)中栏流水线对选中变体批量跑 → 详情 tab 显示当前变体。这条**状态脊柱**串起三栏,是 F1 的架构核心,设计错了上面全错。要验证它对,左栏列表 + 右栏变体卡**都得是真的**。故 F1a = 外壳 + 状态脊柱 + 列表 + 变体卡(中栏先占位)。**不**把旧 DraftDetail 钉进中栏(它带的是错的单草稿状态模型 + 自带一套变体,会冗余割裂)。

## 不丢功能:旧编辑器挪 legacy 路由
旧 `Collect.vue`(含 DraftDetail)整体挪到 `/drafts-classic` 路由暂留兜底(F1 完工删除)。新工作台在 `/` 长出来。互不污染、可回退。

## 数据源(全部已存在,F1a 零后端改动)
- 草稿列表:Pinia `useAppStore`(`drafts`/`serverCounts`/`filter`/`selectedId`/`selected`(多选 Set)/`page`/`pageSize`/`total`,`setFilter`/`setPage`/`setPageSize`/`loadDrafts`/`upsertDraft`/`removeDraft`,`pendingOps`/`setOp`/`isOp`)。
- 变体组:`api.variantGroup(draftId)` → `{ok, group, variants:[{id, spec, price, status, image, current}], count}`(`spec`=变体维度文本如"雾灰·600ml",来自 spec_attrs/variant_label)。
- 批量动作:`api.batchUpdateDrafts`/`batchPublish`/`deleteDraft`(沿用 Collect 现逻辑)。

## ① 工作台状态模型 — 新 Pinia 模块 `src/stores/workbench.js`(脊柱)
独立于 app.js(app.js 管全局草稿列表/店铺;workbench 管"当前编辑的变体组 + 选择")。
- **state**:`groupKey`(当前变体组,空=单草稿)、`variants`(组内变体 `[{id,spec,price,status,image,current}]`)、`selectedVariantIds`(右栏多选,Set/数组)、`currentVariantId`(详情 tab 显示哪个)、`loading`。
- **actions**:
  - `loadForDraft(draftId)`:调 `api.variantGroup(draftId)` 填 `variants`/`groupKey`;`currentVariantId=draftId`;`selectedVariantIds` 默认全选或选当前(见决策);单草稿无组 → `variants=[该草稿轻量]`、`groupKey=''`。
  - `setCurrentVariant(id)`、`toggleVariant(id)`、`selectAll()`/`invertSelection()`/`clearSelection()`。
  - `reload()`(变体增删后重拉)。
- **getters**:`currentVariant`、`selectedVariants`、`variantCount`、`allSelected`。
- **默认多选**:`loadForDraft` 后 `selectedVariantIds` = 全部变体 id(对齐原型"已选 N",批量跑默认全跑;用户可改)。
- 与 app.js 联动:`app.selectedId` 变化 → Workbench.vue watch → `workbench.loadForDraft(selectedId)`。

## ② 三栏外壳 — `src/views/Workbench.vue`(挂 `/` 路由)
- CSS grid 三栏:左 `DraftListPane`(固定宽~360)｜ 中 `占位区`｜ 右 `VariantCardsPane`(固定宽~360),中间自适应。用 F0 设计系统(SCard/SSectionHeader 等)。
- watch `store.selectedId` → `workbench.loadForDraft`。
- 中栏占位:`<div class="wb-center-placeholder">` 显示"选中变体后在此进入 AI 工作台 / 编辑"(F1c/F1d 填)。若 `store.selectedDraft` 为空显示空态(同原型"选中左侧草稿")。
- 顶部右侧操作(店铺选择 + 发布到 Ozon)沿用 Collect 现有发布流(`doPublish`),F1a 保留可用。

## ③ 左栏 — `src/components/workbench/DraftListPane.vue`(替 DraftTable)
原型样草稿卡列表:
- 头:标题"商品草稿" + count + 刷新;`STabs`(全部/待完善/待发布/失败/已发布 + 各 count,key 映射 `all/invalid/ready/failed/published` → `store.setFilter`)。
- 过滤框(本页内文字过滤,即时)+ 全选 checkbox(多选 `store.selected`)。
- 草稿卡(SCard 风,点选 `store.selectedId=id` + 高亮 active):缩略图(`d.images[0]`,可空占位)+ 标题(`d.source_title||d.ozon_title`)+ `1688/Ozon` SBadge(`d.source_platform`)+ ID(`d.id`)+ 价(¥`d.cost_cny` 或 ₽`d.price`)+ 状态 SBadge(`d.status`→待发布/待完善/已发布/失败,颜色映射)。
- 分页(ElPagination,接 `store.page/pageSize/total`/`setPage`/`setPageSize`)。
- 多选批量工具条(选中 >0 时显示):批量设仓库/库存、批量发布、删除——逻辑沿用 Collect 的 `doBatchUpdate`/`doBatchPublish`/`doDelete`(F1a 把这些从 Collect 迁到 Workbench.vue 或一个 composable `useDraftBatchOps`)。

## ④ 右栏 — `src/components/workbench/VariantCardsPane.vue`
- 头:"变体 N 个 · 已选 M" + "+ 新增"(F1a 可先占位禁用或接现有新增变体)。
- 操作行:全选/反选/清空(SButton ghost)+ 搜索框(按 spec 过滤)。
- 变体卡网格(每张 = 一个变体草稿):颜色芯片/spec 文本(`v.spec`)+ 价(`v.price` ₽)+ 状态 SBadge(`v.status`)+ 缩略图(`v.image`)+ 多选 checkbox(`workbench.toggleVariant`)+ 当前高亮(`v.id===currentVariantId`,点卡 `setCurrentVariant`)+ × 删除(接 `api.deleteDraft` + `workbench.reload`,二次确认)。
- **单变体进度(原型的 5/7)F1a 不做**(那是 F1c 流水线派生量)——F1a 卡片先到状态徽标为止。
- 多选写入 `workbench.selectedVariantIds`(为 F1c 流水线"对选中变体批量跑"铺路)。

## ⑤ 路由变更(`src/router/index.js`)
- `/`(name drafts)→ 组件从 `Collect.vue` 改为 `Workbench.vue`。
- 新增 `/drafts-classic`(name drafts-classic)→ `Collect.vue`(legacy 兜底)。
- 其余路由不变。

## 绞杀进度
- 退役:`DraftTable.vue`(被 DraftListPane 替)、`VariantList.vue`(源变体格,工作台不再用;若 DraftDetail-classic 仍引则暂留)。
- 暂留:`Collect.vue`+`DraftDetail.vue` 在 `/drafts-classic`(F1 完工删)。

## 测试(Vitest)
- `workbench.js`:`loadForDraft` mock `api.variantGroup` → variants/groupKey/currentVariantId/默认全选;toggle/selectAll/clear/invert;单草稿无组退化。
- `DraftListPane`:渲染草稿卡、STabs 切 filter 调 `setFilter`、点卡设 selectedId、分页、多选全选。
- `VariantCardsPane`:渲染变体卡(spec/价/状态)、多选写 selectedVariantIds、点卡 setCurrentVariant、删除二次确认。
- 路由:`/` 渲 Workbench、`/drafts-classic` 渲 Collect。
- gating:新测试过 + 全量失败数 ≤ 32(F0 留下的历史失败基线,与本块无关)+ `npm run build` 成功。

## 非目标(后续块)
- **F1c**:AI 上架工作台流水线(7 步 + 每变体 N/7 进度 + 运行/重跑/一键跑完)。中栏占位由它替换。
- **F1d**:详情多 tab(商品信息/特征/图片[接素材库/图集后端]/视频/富文本/采购信息)+ AI 提案审阅。
- 不改后端(变体组 N/7 进度若需后端字段,留 F1c 评估)。
- 不做源商品变体格(VariantList 的旧概念)迁移。
- 不重绘 legacy 路由内的旧编辑器(只是搬家)。
