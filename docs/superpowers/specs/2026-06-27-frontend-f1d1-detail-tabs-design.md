# 前端重建 F1d-1:详情 tab 壳 + 简单 tab — 设计

- 日期:2026-06-27
- 所属:前端重建 F1(拆 `DraftDetail.vue` god-component)最后一块 F1d 的第一子块。F1d 拆为 F1d-1(壳+简单tab)→ F1d-2(特征)→ F1d-3(图片,接素材/图集后端)→ F1d-4(AI提案审阅)。本 spec 仅 F1d-1。
- 前置:F0 ✓、F1a(工作台地基,`stores/workbench.js` 有 `currentVariantId`)✓、F1c(中栏 PipelinePanel)✓。
- 原型:`变体工作台.dc.html` 中栏 PipelinePanel 下方的详情 tab 区。

## 范围与模型
中栏 PipelinePanel **下方**加"当前变体详情编辑区"。**模型**:流水线=批量(选中变体),详情=**当前变体(`workbench.currentVariantId` 那一个)**。F1d-1 做:tab 容器 + 拉当前变体完整草稿 + 4 个简单 tab(商品信息/采购/视频/富文本)。**特征/图片 tab 先占位**(F1d-2/F1d-3 填)。**不动 legacy `DraftDetail.vue`/`Collect.vue`**(F1d 全做完才删 god-component + 下线 legacy)。

## 复用(直接用,不重建)
现有独立子组件可原样复用:`CategorySelect.vue`、`BrandSelect.vue`、`MediaManager.vue`、`RichContentPreview.vue`、`AiVideoDialog.vue`。只重建 god-component 的内联表单 + tab 逻辑。

## 数据:拉单草稿(端点已存在)
- 后端 `GET /api/drafts/{draft_id}`(main.py:199)已存在 → api.js 加 `getDraft: (id) => req('GET', \`/api/drafts/${id}\`)`。
- 保存:`api.patchDraft(id, patch)`(已有)。

## ① `composables/useDraftForm.js`
从 god-component 抽 `initFromDraft`/`collectPatch`/`save`:
- 入参:`draftIdRef`(响应式,= `workbench.currentVariantId`)。
- `draft`(ref,完整草稿)、`form`(reactive,可编辑字段)、`loading`、`dirty`。
- `load()`:`api.getDraft(id)` → 灌 `draft` + `initFromDraft(d)` 填 `form`。watch `draftIdRef` 变 → `load()`(immediate)。
- `collectPatch()`:从 `form` 收集 patch(字段:`ozon_title/category_id/type_id/brand_id/brand_name/stock/price/old_price/weight_g/length_mm/width_mm/height_mm/description/cost_cny/purchase_url/purchase_note/supplier`;`source_raw`/`images`/`offer_id` 按需)——逻辑搬 god-component `collectPatch`(1353)。
- `save()`:`api.patchDraft(id, collectPatch())` → 更新 `draft`,`store.upsertDraft` 同步列表 + `workbench.reload()`(刷新变体步骤进度)。
- 返回 `{ draft, form, loading, load, save, collectPatch }`。

## ② `components/workbench/DetailTabs.vue`
- `import { useWorkbenchStore }`、`useDraftForm`、`src/ui` STabs、4 个简单 tab 组件。
- `const wb = useWorkbenchStore(); const fm = useDraftForm(computed(() => wb.currentVariantId))`。
- 顶 STabs(items:商品信息`info`/特征`attrs`/图片`images`/视频`video`/富文本`richtext`/采购信息`purchase`;activeKey 本地 ref;@change 切)。
- 内容区按 activeKey 渲染:`InfoTab`/`PurchaseTab`/`VideoTab`/`RichTextTab`(传 `:form="fm.form"` `:draft="fm.draft"` `@save="fm.save"`);`attrs`/`images` 渲染占位 div("特征/图片 tab 将在 F1d-2/F1d-3 实现")。
- `wb.currentVariantId` 为空 → 不渲染(空态)。

## ③ 简单 tab 组件(`components/workbench/tabs/`)
每个接 `props: { form, draft }` + `emit('save')`(失焦/改动后保存,或显式保存按钮——见决策),tokens 样式:
- `InfoTab.vue`:Ozon 标题(ElInput)/类目(`<CategorySelect v-model>`)/品牌(`<BrandSelect>`)/库存/售价/划线价/克重/尺寸长宽高(ElInputNumber)。
- `PurchaseTab.vue`:采购链接/供应商/成本价(¥)。
- `VideoTab.vue`:`<MediaManager>`(video 模式)+ `<AiVideoDialog>` 触发(复用现有 onVideoChange/openAiVideo 逻辑搬一份)。
- `RichTextTab.vue`:`<RichContentPreview :rich-json>` + "生成富文本"按钮(`api.makeRichContent`)。
- **保存策略**:简单起见 **显式"保存"按钮**(每 tab 底部 SButton "保存" → `emit('save')`),不做自动保存(YAGNI,避免每次输入打 PATCH)。

## ④ 接进 Workbench 中栏
`views/Workbench.vue` 中栏 `v-else` 分支:PipelinePanel **下面**加 `<DetailTabs />`(同一滚动容器,对照原型)。保留 empty 态。

## 测试(Vitest)
- `useDraftForm`:mock `api.getDraft`/`patchDraft`,watch draftId 变 → load 填 form;save 调 patchDraft(collectPatch)+ upsertDraft。
- `DetailTabs`:渲染 6 tab 头、切 tab、currentVariantId 变触发 load;attrs/images 显占位。
- 各简单 tab:渲染字段、改 form、点保存 emit save。
- gating:前端新测试过 + 失败数 ≤ 32(历史基线)+ `npm run build`。

## 非目标
- F1d-2 特征 tab(属性映射/AI填)、F1d-3 图片 tab(素材/图集后端)、F1d-4 AI 提案审阅。
- 不动 legacy DraftDetail/Collect。
- 不改后端(getDraft/patchDraft 已存在)。
- 不做自动保存。
