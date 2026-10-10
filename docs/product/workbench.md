# 变体工作台（Workbench）

> 核心页面：商品草稿 + 变体 + AI 上架工作台。挂在路由 `/`（`views/Workbench.vue`）。
> 这是前端重建的主战场。旧 `DraftDetail.vue`（2992 行 god-component）+ `Collect.vue` + `/drafts-classic` 路由 **已于 2026-06-27 F1 收口删除**（能力全迁入本工作台，提交 a35f824）。
> 本文档随功能改动持续更新（交互/数据/规则三块）。

## 1. 交互（页面结构与操作流程）

**左栏草稿列表 + 右侧工作区纵向三段**布局（`views/Workbench.vue`，2026-06-28 重构，从旧三栏改来）。容器类名：`.wb-grid`（CSS grid，左 `320px` + 右 `1fr`）/ `.wb-left` / `.wb-main`；右侧三段自上而下 `.wb-group` / `.wb-flow` / `.wb-detail`。

| 区域 | 组件 | 职责 |
|---|---|---|
| 左栏 `.wb-left` | `components/workbench/DraftListPane.vue` | 草稿列表（替代旧 DraftTable），**sticky 320px**，STabs 分状态 + SBadge 计数，点选一条草稿 |
| 右·顶 `.wb-group` | `components/workbench/VariantGroupBar.vue` | **变体组横排条**：横向排列的变体胶囊，点选/删除当前变体（详见 §变体组横排条） |
| 右·中 `.wb-flow` | 来源条 + 发布条 + `components/workbench/PipelinePanel.vue` | AI 流水线 7 步（**只对当前变体单跑**，详见 §3 规则） |
| 右·下 `.wb-detail` | `components/workbench/DetailTabs.vue` | 当前变体详情多 tab |

**主流程**：左栏选草稿 → 右·顶变体组横排条出该草稿所属**变体组**的全部变体胶囊 → 点胶囊选定「当前变体」→ 右·中流水线**对当前变体逐个**跑 AI 步骤 → 右·下 DetailTabs 展示/编辑「当前变体」明细。**无批量**：一次只操作一个当前变体（见 §3「只能逐个变体跑」）。

**§变体组横排条（VariantGroupBar）**（`components/workbench/VariantGroupBar.vue`，右侧工作区顶段 `.wb-group`）：
- 标题：**「🔗 变体组 共 N 个变体（同组合并成一张 Ozon 多变体卡）」**，点明同组变体最终合并发布为一张 Ozon 多变体卡片。
- 主体：**横向排列的变体胶囊**，每个胶囊含 缩略图 + 颜色点（取色策略见 §3 变体组规则）+ spec 文本 + 完成度 **N/7**（当前变体在 7 步流水线已完成步数）。
- **当前变体高亮**：紫描边 + 浅紫底；点胶囊调 `wb.setCurrentVariant(id)` 切换当前变体（驱动右·中流水线上下文 + 右·下详情）。
- **胶囊删除**：hover 时右上角出 `×`，点击弹确认弹窗 → `api.deleteDraft(id)` → `emit('variant-deleted')` → 父级 `Workbench.vue` 接住后 `store.loadDrafts()` 刷新。

**§来源小区块**（`Workbench.vue`，选中草稿后置于右·中工作区发布条上方）：显示「来源商品标题（`source_title`）+ 打开来源链接 ↗」。链接 `sourceLink(d)`：优先 `purchase_url`，否则 `source_url`（1688 等）；新窗口打开（`rel=noopener`）。让用户在工作台直接回看来源，不必依赖左栏草稿卡。

**§特征 tab（AttributesTab）**：按当前变体所选 Ozon 类目展示/填写属性，三组布局：
- **区别特征（变体维度）** 置顶，说明「合并成一张卡时各变体靠它区分」。
- **必填** 组（标题带计数；尾注「品牌在『商品信息』tab 填」）。
- **可选** 组默认收起，按钮展开。
- 字段控件（`AttrField.vue`）：字典属性 → `ElSelect`（单/多选按 `is_collection`，多选上限 `max_value_count`，filterable+clearable；大字典 `oversized` 切远程搜，输入 ≥2 字调搜索）；自由文本属性 → `ElInput`。必填未填项标红框。
- 顶部「AI 填充特征」按钮（直接调 `aiFillAttributes` 写回）+「保存」按钮。缺必填时顶部 `SAlert` 提示「还缺 N 项」。
- 类目未选时显空态「先在『商品信息』tab 选好类目，再填特征」。

**详情 tab（DetailTabs，6 个）**：
1. 商品信息 InfoTab — 标题/类目/品牌/价/尺寸
2. 特征 AttributesTab — Ozon 类目属性填充（详见 §特征 tab）
3. 图片 ImagesTab — 顶部出图区**只两个按钮**:✨ AI 生图(直接 `designImagePlan(id,10)`+`imagePlan(id,false)` 一键出全套图,带 loading,完成 toast+`emit('saved')` 刷新两池)、复制到别的变体(把当前图集的图 push 给选中的同组兄弟变体,见 §复制到别的变体) + **图集合规自查徽章带** + 两段:图集(排序/移出/删除/上传)+ 素材库(加入图集/批量/删除);**所有图卡 hover 右下 🔍 可全屏放大查看**;对接两池后端,详见 [material-gallery.md](material-gallery.md)
4. 视频 VideoTab — 复用 `MediaManager(only=video)` + `AiVideoDialog`
5. 富文本 RichTextTab — 复用 `RichContentPreview`，数据 `source_raw.rich_content_json`；点「生成富文本」后 `emit('saved')` → 父级 `fm.load` 刷新草稿，预览即时出现。
6. 采购信息 PurchaseTab — 采购链接/备注/供应商/offer_id

**§tab「数据就绪」绿点**（DetailTabs）：tab 标签旁据 `fm.draft`（getDraft 派生）实时点亮小绿点（`STabs` 的可选 `item.ready` → `.s-tabs__dot`，`--c-success` 6px 圆点），只读不改 store：
- **特征**：`draft.attributes` 里存在**排除系统/默认项 9048/23171/85** 后仍有非空 `values` 的属性。
- **图片**：`draft.materials` 里有 `in_gallery` 图（即图集非空）。
- **视频**：`draft.video_url` 有值。
- **富文本**：`draft.source_raw.rich_content_json` 有值。
- 商品信息/采购信息无绿点（始终可填，非「就绪」语义）。

**§详情无焦点空态**（DetailTabs）：`currentVariantId == null`（未选变体）时，不再整块隐藏，改显 🎯 引导空态「选择至少一个变体查看详情」+ 副文案「在上方变体组横排条点选一个变体…」（`.dt--empty`）。有焦点才渲 tab。
> 注：DetailTabs **已移除内嵌的「AI 文案（生成并应用 / 快速文案）」区**（与流水线 copy 步重复，避免双入口）；`ProposalPanel.vue` + `composables/useProposal.js` 已随之删除。AI 文案统一走右·中流水线的 copy 步。

**§出图区两按钮**（ImagesTab `.images-tab__actions`，取代旧 AiImagePanel 那套「设计图集/刷新计划/按槽生成/一键出全部」UI）：
- **✨ AI 生图**（`doAiGenerate`）：点了直接走生图链路最简方式——`api.designImagePlan(id, 10)`（按看图理解设计 10 张图集方案）→ `api.imagePlan(id, false)`（据方案出图，与流水线「图集/出图」步一致）。期间 `aiLoading` 置 loading；成功 `ElMessage.success('AI 出图完成')` + `emit('saved')`（父层 reload → 新图进图集/素材两池刷新）；失败 toast warning。不再暴露槽位/重出/计划状态等中间态。
- **复制到别的变体**（仅当存在同组兄弟变体时显示，`siblings = wb.variants.filter(id≠当前)`）：点击展开内联小面板 `.copy-panel`——`ElSelect multiple` 选目标变体（label 取 `v.spec`）+ 一组当前图集图卡（默认全选 `copyUrls=galleryItems.map(url)`，可点图卡增减）；确认调 `api.copyImagesTo(当前id, copyUrls, copyTargets)`（**从当前变体 push 到目标变体**，方向与旧「来自变体借图」相反，承接其跨变体能力），成功 toast「已复制 N 张到 M 个变体」+ `emit('saved')`。目标或图为空时确认按钮 disabled。

**§图片放大 lightbox**（ImagesTab + ImageCard）：点击 `@zoom` 抛 src → ImagesTab 渲一个全屏遮罩 `.lightbox`（`position:fixed` z-index 3000，`rgba(15,18,28,.82)` 底 + `--sh-pop` 阴影，右上 ✕ 关闭，点遮罩任意处也关闭，点图片本身不关）。轻量自实现，无新依赖。触发方式两类：
- **图集区**：点图片本身即可全屏放大（图集图卡无「选中」语义，整图即放大热区）。
- **素材库 / 复制面板**：点图是**选中**（加入图集 / 增减复制集合），放大走图卡 hover 右下角 🔍 按钮。

**§图集「Ozon 要求」合规自查徽章带**（ImagesTab 图集区顶部 `.compliance`）：实时据图集数据算合规，达标绿(`is-ok`)/注意琥珀(`is-warn`)/不达标红(`is-bad`)/未知灰(`is-unknown`)：
- **张数 ≥ 10**：以 `galleryItems.length` 算（≥10 达标；1~9 注意；0 不达标）。
- **格式 jpg/png**：从图 url 后缀判定，全部命中 jpg/jpeg/png 达标；有非法后缀不达标；部分图判不出后缀标「注意」；空图集未知。
- **比例 3:4 / 长边 / 单张 ≤10MB**：**前端无法获取真实像素与文件大小，统一标「未知」（灰、cursor:help，hover 提示「仅作建议」）**——不伪造达标。真实校验由后端发布前体检承担。

## 2. 数据（状态与接口）

### 状态脊柱 `stores/workbench.js`
选草稿 → 拉变体组 → 当前变体，是整个工作台的状态来源：
- `selectedDraftId` → 调 `api.variantGroup(draftId)` → `variantGroup`（含每个 sibling 的 `steps`/`done` 派生字段）
- `currentVariantId` → 当前操作/展示的变体（VariantGroupBar 高亮 + 流水线作用对象 + DetailTabs 展示对象）；`setCurrentVariant(id)` 切换。
- getter `currentStepDone(stepId)` → **当前变体**某步是否已完成（布尔，基于 `currentVariant.steps`）。流水线进度位与运行按钮文案据此判定（详见 §3）。
- > 现状：`selectedVariantIds`（多选）及相关 action **仍保留在 store（未删，无害）**，但**工作台 UI 不再用它驱动批量**——重构后改为逐个变体操作，所有 AI 步骤只对 `currentVariantId` 单跑。旧 getter `stepProgress(stepId)`（聚合选中变体 N/M）已不在 UI 使用。

### 关键接口
| 用途 | api.js 方法 | 后端 path |
|---|---|---|
| 拉变体组（带派生 steps/done） | `api.variantGroup(id)` | `GET /api/drafts/{id}/variant-group` |
| 拉单草稿详情 | `api.getDraft(id)` | `GET /api/drafts/{id}` → **返回 `{draft:{...}}`（包一层！）** |
| 部分更新草稿 | `api.patchDraft(id, patch)` | `PATCH /api/drafts/{id}`（merge 语义，只发改动字段） |
| 删除变体（草稿） | `api.deleteDraft(id)` | `DELETE /api/drafts/{id}`（VariantGroupBar 胶囊 × 调用，确认后删该变体） |

> ⚠️ **坑（已修，必记）**：`getDraft` 返回 `{draft:{...}}` 包了一层。前端 composable 必须解包 `r.draft || r`。单测 mock 也要返回 `{draft:{...}}` 对齐真实端点，否则掩盖 bug（见 `useDraftForm.js` + `draftform.test.js`）。

### 表单 composable `composables/useDraftForm.js`
`useDraftForm(draftIdRef)` → `{draft, form, loading, load, save, collectPatch}`。
- `load()`：拉 getDraft + 解包 + `initFromDraft` 填 reactive form
- `collectPatch()`：只收简单标量字段（标题/类目/品牌/价/尺寸/采购），因 patchDraft 是 merge
- `save()`：patchDraft(collectPatch()) → 回写 draft + `store.upsertDraft` + `wb.reload()`

InfoTab 内：`categoryModel` computed（form.category_id+type_id ↔ CategorySelect 的 `{cat,type}`）、`brandModel`（form.brand_id+brand_name ↔ BrandSelect 的 `{brand_id,brand_name}`）。

### 特征 composable `composables/useAttributes.js`
`useAttributes(draftRef)` → `{groups, values, missingIds, errors, loading, optionsOf, loadingOf, oversizedOf, ensureOptions, search, setValue, aiFill, save, reloadDefs}`。
- **单一真相** `values` reactive map：`attrId → Array<{dictionary_value_id?, value}>`（Ozon 上架结构的单属性 values）。从 `draft.attributes` 构建。
- defs 分组按类目拉一次（`api.requiredCheck(id,lang)` → `{aspects, required, optional, missing, errors}`，后端**已排除**品牌(85)/原产国/「类型」）；`category_id|type_id` 变才重拉。
- 选项：懒加载 `api.attributeOptions(cat,type,attr,lang)`（`oversized` → 远程搜 `api.attributeValues(...,q,...)`）。
- 保存：`api.patchDraft(id, {attributes:[{id,values}]})`（merge，store 落 attributes_json），值变 300ms 防抖；保存后 `emit('saved')` → DetailTabs `fm.load` 刷新草稿派生字段/流水线 attrs 步进度。
- AI 填充：`api.aiFillAttributes(id)` 直接写 attributes_json（**非** ai_proposal），返回 draft 重建 values。

| 用途 | api.js 方法 | 后端 path |
|---|---|---|
| 类目属性分组+缺失 | `api.requiredCheck(id,lang)` | `GET /api/drafts/{id}/required-check` |
| 全量字典选项 | `api.attributeOptions(cat,type,attr,lang)` | `GET /api/attribute/values` |
| 大字典实时搜 | `api.attributeValues(cat,type,attr,q,lang)` | `GET /api/attribute/values/search` |
| AI 直填属性 | `api.aiFillAttributes(id)` | `POST /api/drafts/{id}/ai-fill-attributes` |

## 3. 规则

### AI 流水线（`composables/usePipeline.js`，approach A：完成判定后端算）

#### AI 生成内容（2026-06-29）
原 `understand / category / copy / attrs` 在工作台主流水线里合并为单步 **content / AI 生成内容**：
- 点击「运行」调用 `POST /api/drafts/{id}/generate-all`，只创建 `text_jobs` 记录并发布 RabbitMQ `ozon_text_jobs` 消息，HTTP 立即返回 `{job_id,status}`。
- 后台由独立 `ozon-text-worker` 消费，串行执行 `understand → category → copy → attrs`，每完成一步写 `text_jobs.current_step/steps_done`，最终写 `done` 或 `failed+error`。
- 同一变体已有 `queued/running` 文本任务时拒绝重复提交，避免重复烧 token。
- 前端**不轮询**。提交后显示「生成中（已提交，刷新查看）」；用户点工作台刷新按钮或刷新页面后，读取最新 draft 和 latest text job。`content` 完成判定 = `category_id && type_id && ozon_title && description && attributes` 就绪。
- `images` 依赖 `content`；`publish` 依赖 `content/images/rich`。

旧三步 flags（`understand/category/copy/attrs`）仍由后端保留，供详情、测试或兼容入口使用；主流水线只展示 `content/images/rich/publish`。

### 兼容旧 7 步说明
顺序与依赖门控（`wfDepOk` / `stepLocked`，**均只看当前变体**）：
1. **understand** 图文理解 — 判定：`source_raw.understanding` 有值
2. **category** 类型识别 — 判定：`category_id` + `type_id` 有值
3. **copy** AI 文案 — 判定：`ozon_title` + `description` 有值；RUN_ONE = aiGenerate + aiProposalApply
4. **attrs** 特征 — 判定：有真实属性（**排除 attribute_id 9048/23171/85** 这几个系统/默认项）
5. **images** 图片 — 判定：有图或有 image_types；RUN_ONE = designImagePlan + imagePlan
6. **rich** 富文本 — 判定：`source_raw.rich_content_json` 有值
7. **publish** 发布 — 判定：`ozon_product_id` 有 或 `status=published`；**不在 RUN_ONE**，emit `publish-one` 由父级单变体发布（见下）

- 完成判定在后端 `app_service.step_flags(draft)` 算，经 `variant_group_siblings` 给每个变体附 `steps`+`done` → 前端零 N+1、不重复逻辑。

#### 只能逐个变体跑，无批量（2026-06-28 重构核心规则）
重构前流水线对「已选的一组变体」批量并发跑；现改为**一次只对当前查看的变体单跑**：
- **已删除**：「⚡一键跑完已选(N)」按钮、「批量运行 N 个变体」上下文文案、「每步对所有已选变体并发跑」的 `runConcurrent` 用法、`runAll()`。
- `runStep(stepId)`：现在**只对当前变体 `currentVariantId` 单跑**一次该步的 RUN_ONE 序列（不再并发遍历选中集合）。
- `stepLocked(stepId)`：只看**当前变体** `currentVariant.steps` 是否满足该步依赖——无依赖步骤永不锁；当前变体的某个前置步骤未完成则锁定。`runStep` 内部也对 `stepLocked` 提前 return，门控不可绕过。无当前变体时不触发运行。
- **为什么这么改（理由）**：① 避免一次性对整组所有变体跑 AI、把 token/钱烧爆；② 避免半成品被误批量发布；③ 出错时易定位是哪个变体哪一步坏的——逐个变体补完更可控。

#### 流水线 UI（PipelinePanel.vue）
- **上下文条**改为显示**当前变体**：颜色点 + spec，文案「正在操作：{spec}」；无当前变体时显灰禁用样式「请在上方选择一个变体」。**不再显示「已选 N」**。
- **每步进度位**基于**当前变体单步布尔** `wb.currentStepDone(stepId)`：已完成显 ✓、未开始显「未开始」；该步锁定时显「待前置步骤」。
- **运行按钮文案**：已完成 → 「重跑」；未完成 → 「运行」；锁定 → 「锁定」（disabled）。
- **序号状态化视觉**（`stepState`，优先级 running>locked>done>idle）：done→✓(绿)、running→脉冲动画(实心紫)、locked→🔒(灰)、idle→数字。

#### 发布（单变体）
- 流水线发布按钮 emit `publish-one` → 父级 `Workbench.vue` 接 `ops.doPublish(store.selectedDraft)` **单变体发布**（不再 `doBatchPublish([...selectedVariantIds])`）。
- 右·中工作区 `.wb-publish-bar` 的「🚀 发布到 Ozon」同样是单草稿 `ops.doPublish`，带二次确认（`useDraftBatchOps`）。

### 特征 tab 规则（消灭 legacy 双真相源）
- legacy `DraftDetail.vue` 用 `attributesText`(JSON 字符串) + 多个并行 `attrInputs/attrOptions/...` map 当真相源、每次 pick 都 PATCH + 服务端 `requiredCheck` 往返算 missing。新版**单一真相 `values` map + missing 客户端算**（沿用 F1c approach A 哲学）：免每次往返。
- **missing 客户端实时算**：`missingIds` = 所有 `is_required` 的 def 里 `values` 为空者。填了即移除红标。
- 值变 **300ms 防抖保存**；canonical 单属性值形状 `[{dictionary_value_id?, value}]`（字典型带 id、自由文本只 value）。
- 品牌(85)/原产国/「类型」属性后端 `required_check` 已排除，不在此 tab 渲染（品牌走 InfoTab，原产国/类型发布时强制填）。
- 「AI 填充特征」= 直接写 attributes_json；与流水线 **copy 步**（aiGenerate + 自动 apply）是两条不同链路（前者只填属性、后者生成文案）。
- 类目变更会经 InfoTab 保存 → `fm.draft` 更新 → useAttributes 监听重拉 defs。

### 变体组规则
- 同组变体共享：图集（见 material-gallery）、可跨变体复制图（ImagesTab「复制到别的变体」按钮，从当前变体 push 到选中兄弟）。
- 同组变体在 VariantGroupBar 横排展示，**逐个选定当前变体操作**（无批量选择）；同组最终合并成一张 Ozon 多变体卡发布。
- **变体颜色点取色策略**（`VariantGroupBar.vue` `variantColor(v)` / `variantColorName(v)`，原属 VariantCardsPane，2026-06-28 随删卡迁入，策略本身不变）：① 优先从变体数据取颜色词——显式 `v.color` > `v.aspects` 里名为 颜色/цвет/color 的属性值 > 回退 `v.spec` 文本；② 命中常见 **中/俄/英** 颜色名（红/黑/白/蓝/绿/黄…、Красный/Чёрный…、red/black/white…）→ 固定 hex 小映射；③ 取不到 → 按变体 `id` 稳定哈希出 HSL 色相（`hsl(hash%360,62%,56%)`），保证各变体色块互相可区分、不再全紫，也不假装精确商品色。色点加 `inset` 描边保证白/浅色仍可见。
- 「+新增变体」按钮已移除（无后端逻辑，用户明确不需要）。

## 4. 设计系统
紫罗兰 SaaS 风。设计令牌 `src/styles/tokens.css` + EP 主题映射 `element-theme.css`；自建基础组件 `src/ui/`（SButton/SBadge/SChip/SSectionHeader/SCard/SStatCard/SAlert/SAvatar/STabs）。重控件用 Element Plus 改主题，轻外壳/卡片自建。

## 5. 测试与验收
- 单测：Vitest + @vue/test-utils。**前端有 32 个历史失败基线**（`tests/*.spec.js` 组件 rot，与重建无关）；gating 用「失败数 ≤32 不新增」。
- 视觉验收范式：`OZON_WEBUI_DB=<临时库> python -m uv run uvicorn webui.main:app --port 8586`（自动建 admin/admin）→ 临时改 `vite.config.js` proxy 指本地 → `npm run dev` → 浏览器登录验 → **验完 `git checkout vite.config.js` + 删临时库 + 杀端口**。

## 变更历史
- 2026-06-27 建基线（F0 设计系统 / F1a 三栏地基 / F1c AI 流水线 / F1d-1 详情 tab 壳 + 简单 tab）。
- 2026-06-27 F1d-2 特征 tab（AttributesTab + AttrField + useAttributes）：三组布局、字典/文本字段、AI 填充、missing 提示；单一真相值模型 + 客户端算 missing + 防抖存。
- 2026-06-27 F1d-3a 图片 tab（ImagesTab + ImageCard + useGallery）：两池(图集/素材)管理、↑↓排序、加入/移出图集、删除、来自变体借图、上传;接两池后端。
- 2026-06-28 流水线中栏 + 变体卡右栏缺口修复：① 依赖门控接入 UI（`stepLocked` 聚合 + 运行按钮 disabled/锁定态/🔒，`runStep` 内部门控）；② 序号状态化视觉（done✓/running 脉冲/partial 描边/locked 灰）；③ 上下文条大号已选数字 + 语义文案；④ 变体卡颜色芯片去硬编码紫，改取色策略（数据色词→中俄英 hex 映射→id 哈希色相）；⑤ 删「+新增变体」无逻辑按钮；⑥ 变体搜索拓宽至 spec+颜色。
- 2026-06-27 F1d-3b AI 出图（AiImagePanel + useImagePlan）：AI 设计图集方案 + 按槽生成(直进图集)+ 一键出全部 + 槽位状态。
- 2026-06-28 图片 tab 出图区重设计：**删 AiImagePanel + useImagePlan 整套计划 UI（含两测试文件，无其它引用）**，ImagesTab 顶部改为两按钮——「✨ AI 生图」(designImagePlan+imagePlan 一键直出) 与「复制到别的变体」(copyImagesTo 反向 push,承接原「来自变体借图」段并收掉该段)。图集/素材两段、合规徽章带、🔍 lightbox 保留。
- 2026-06-27 F1d-4 AI 提案审阅（ProposalPanel + useProposal）：DetailTabs 顶部条件面板,生成草案→逐项审(标题/简介/标签/AI属性/缺失必填)→应用合并/放弃/重生成。前端重建 F1d 全部完成。
- 2026-06-27 F1 收口（a35f824）：删 DraftDetail.vue(2992行)+Collect.vue god-component、退役 /drafts-classic;净删 4019 行;历史失败测试 32→5(剩 Settings.vue AI 配置既有 rot)。**前端重建闭环**。
- 2026-06-28 变体详情 + 图片 tab 缺口修复：① DetailTabs tab 旁「数据就绪」绿点（特征/图片/视频/富文本，据 `fm.draft` 派生，`STabs.item.ready`）；② 详情无焦点 🎯 引导空态（替换原整块隐藏）；③ 图卡 🔍 全屏 lightbox（ImageCard `@zoom` → ImagesTab `.lightbox` 自实现遮罩，无新依赖）；④ 图集「Ozon 要求」合规自查徽章带（张数≥10/格式 jpg-png 前端可算，比例 3:4/长边/单张≤10MB 因前端无真实像素与文件大小标「未知/建议」不伪造）；⑤ 中栏来源标题 + 打开来源链接小区块。新增单测：detailtabs 绿点 2 例、ImagesTab 合规带 + lightbox 2 例（211 passed）。
- 2026-06-28 工作台重构（单列三段 + 单变体逐个跑）：① 布局从「三栏 + 批量跑变体」改为**左栏草稿列表(sticky 320px) + 右侧工作区纵向三段**（顶 VariantGroupBar / 中 流程 / 下 DetailTabs，`.wb-grid/.wb-left/.wb-main/.wb-group/.wb-flow/.wb-detail`）；② 新建 **`VariantGroupBar.vue`** 变体组横排条（变体胶囊：缩略图+颜色点+spec+N/7，点选 `setCurrentVariant`、hover × 删除 → `deleteDraft` + `variant-deleted` → `loadDrafts`），颜色取色策略与 N/7 自删除的 **VariantCardsPane** 迁入；③ **删 `VariantCardsPane.vue`**；④ 流水线**只对当前变体单跑**——删「一键跑完已选/批量 N 个/runConcurrent/runAll」，`runStep` 仅作用 `currentVariantId`、`stepLocked` 只看当前变体；进度改 `currentStepDone` 单步布尔，上下文条显当前变体；理由：避免整组烧 token、误批量发布、错难定位；⑤ 发布改单变体（流水线 emit `publish-one` → 父级 `ops.doPublish(selectedDraft)`，发布条同）；⑥ **删 `ProposalPanel.vue` + `useProposal.js`** 及 DetailTabs 内嵌「AI 文案」区（与流水线 copy 步重复）。`store.selectedVariantIds` 保留但 UI 不再驱动批量。
