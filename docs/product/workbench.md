# 变体工作台（Workbench）

> 核心页面：商品草稿 + 变体 + AI 上架工作台。挂在路由 `/`（`views/Workbench.vue`）。
> 这是前端重建的主战场，绞杀旧 `DraftDetail.vue`（2992 行 god-component，临时挂 `/drafts-classic` 兜底，F1 完成后删）。
> 本文档随功能改动持续更新（交互/数据/规则三块）。

## 1. 交互（页面结构与操作流程）

三栏布局（`views/Workbench.vue`）：

| 栏 | 组件 | 职责 |
|---|---|---|
| 左 | `components/workbench/DraftListPane.vue` | 草稿列表（替代旧 DraftTable），STabs 分状态 + SBadge 计数，点选一条草稿 |
| 中 | `components/workbench/PipelinePanel.vue` + `DetailTabs.vue` | 上半：AI 流水线 7 步；下半：当前变体详情多 tab |
| 右 | `components/workbench/VariantCardsPane.vue` | 变体卡片（颜色芯片/容量/价/状态/单变体 N/7 进度），多选驱动 |

**主流程**：左栏选草稿 → 右栏出该草稿所属**变体组**的全部变体卡（默认全选）→ 中栏流水线对「选中的变体」批量跑 AI 步骤 → 中栏下半 DetailTabs 展示/编辑「当前变体」明细。

**详情 tab（DetailTabs，6 个）**：
1. 商品信息 InfoTab — 标题/类目/品牌/价/尺寸
2. 特征 AttributesTab — Ozon 类目属性填充（F1d-2，详见 §交互-特征）
3. 图片 ImagesTab — 图集 + 素材库（F1d-3，对接两池后端，详见 [material-gallery.md](material-gallery.md)）
4. 视频 VideoTab — 复用 `MediaManager(only=video)` + `AiVideoDialog`
5. 富文本 RichTextTab — 复用 `RichContentPreview`，数据 `source_raw.rich_content_json`
6. 采购信息 PurchaseTab — 采购链接/备注/供应商/offer_id

## 2. 数据（状态与接口）

### 状态脊柱 `stores/workbench.js`
选草稿 → 拉变体组 → 多选 → 当前变体，是整个工作台的状态来源：
- `selectedDraftId` → 调 `api.variantGroup(draftId)` → `variantGroup`（含每个 sibling 的 `steps`/`done` 派生字段）
- `selectedVariantIds`（多选，默认全选）→ 流水线批量作用对象
- `currentVariantId` → DetailTabs 展示对象
- getter `stepProgress(stepId)` → 聚合「选中变体在某步的完成数 N/M」

### 关键接口
| 用途 | api.js 方法 | 后端 path |
|---|---|---|
| 拉变体组（带派生 steps/done） | `api.variantGroup(id)` | `GET /api/drafts/{id}/variant-group` |
| 拉单草稿详情 | `api.getDraft(id)` | `GET /api/drafts/{id}` → **返回 `{draft:{...}}`（包一层！）** |
| 部分更新草稿 | `api.patchDraft(id, patch)` | `PATCH /api/drafts/{id}`（merge 语义，只发改动字段） |

> ⚠️ **坑（已修，必记）**：`getDraft` 返回 `{draft:{...}}` 包了一层。前端 composable 必须解包 `r.draft || r`。单测 mock 也要返回 `{draft:{...}}` 对齐真实端点，否则掩盖 bug（见 `useDraftForm.js` + `draftform.test.js`）。

### 表单 composable `composables/useDraftForm.js`
`useDraftForm(draftIdRef)` → `{draft, form, loading, load, save, collectPatch}`。
- `load()`：拉 getDraft + 解包 + `initFromDraft` 填 reactive form
- `collectPatch()`：只收简单标量字段（标题/类目/品牌/价/尺寸/采购），因 patchDraft 是 merge
- `save()`：patchDraft(collectPatch()) → 回写 draft + `store.upsertDraft` + `wb.reload()`

InfoTab 内：`categoryModel` computed（form.category_id+type_id ↔ CategorySelect 的 `{cat,type}`）、`brandModel`（form.brand_id+brand_name ↔ BrandSelect 的 `{brand_id,brand_name}`）。

## 3. 规则

### AI 流水线 7 步（`composables/usePipeline.js`，approach A：完成判定后端算）
顺序与依赖门控（`wfDepOk`）：
1. **understand** 图文理解 — 判定：`source_raw.understanding` 有值
2. **category** 类型识别 — 判定：`category_id` + `type_id` 有值
3. **copy** AI 文案 — 判定：`ozon_title` + `description` 有值；RUN_ONE = aiGenerate + aiProposalApply
4. **attrs** 特征 — 判定：有真实属性（**排除 attribute_id 9048/23171/85** 这几个系统/默认项）
5. **images** 图片 — 判定：有图或有 image_types；RUN_ONE = designImagePlan + imagePlan
6. **rich** 富文本 — 判定：`source_raw.rich_content_json` 有值
7. **publish** 发布 — 判定：`ozon_product_id` 有 或 `status=published`；**不在 RUN_ONE**，走 `useDraftBatchOps` 带二次确认

- 完成判定在后端 `app_service.step_flags(draft)` 算，经 `variant_group_siblings` 给每个变体附 `steps`+`done` → 前端零 N+1、不重复逻辑。
- `runStep(stepId)`：对 `selectedVariantIds` 用 `utils/runConcurrent.js` 并发 4 跑该步 RUN_ONE 序列。
- `runAll()`：按依赖顺序串起整条。
- 进度展示：中栏聚合 N/M、右栏变体卡 N/7 条。

### 变体组规则
- 同组变体共享：图集（见 material-gallery）、可跨变体借图。
- 默认全选当前组所有变体，批量操作作用于选中集合。

## 4. 设计系统
紫罗兰 SaaS 风。设计令牌 `src/styles/tokens.css` + EP 主题映射 `element-theme.css`；自建基础组件 `src/ui/`（SButton/SBadge/SChip/SSectionHeader/SCard/SStatCard/SAlert/SAvatar/STabs）。重控件用 Element Plus 改主题，轻外壳/卡片自建。

## 5. 测试与验收
- 单测：Vitest + @vue/test-utils。**前端有 32 个历史失败基线**（`tests/*.spec.js` 组件 rot，与重建无关）；gating 用「失败数 ≤32 不新增」。
- 视觉验收范式：`OZON_WEBUI_DB=<临时库> python -m uv run uvicorn webui.main:app --port 8586`（自动建 admin/admin）→ 临时改 `vite.config.js` proxy 指本地 → `npm run dev` → 浏览器登录验 → **验完 `git checkout vite.config.js` + 删临时库 + 杀端口**。

## 变更历史
- 2026-06-27 建基线（F0 设计系统 / F1a 三栏地基 / F1c AI 流水线 / F1d-1 详情 tab 壳 + 简单 tab）。
