# 前端重建 F1c:AI 上架工作台流水线(中栏)— 设计

- 日期:2026-06-27
- 所属:前端重建 F1(拆 `DraftDetail.vue` god-component)第二块。F1a(地基)✓。本块填中栏占位:7 步 AI 流水线 + 每变体进度 + 批量跑。F1d(详情 tab)随后。
- 前置:F0 设计系统 ✓、F1a 工作台地基 ✓(`stores/workbench.js`、`Workbench.vue`、变体卡)。
- 原型:`变体工作台.dc.html` 中栏"AI 智能上架工作台"。

## 范围边界
F1c 只做**流水线编排 + 批量跑 + 进度展示**。交互式提案/计划/特征逐项编辑(applyProposal、plan 管理)= 当前变体详情,属 **F1d**。F1c 的 runStep 批量模式只"调 endpoint + finalize"。**不动 legacy `DraftDetail.vue`/`Collect.vue`**(它们保留自己那份工作流给 `/drafts-classic`,F1 完工随之删;期间临时重复一份工作流逻辑,可接受的绞杀过渡)。

## 7 步模型(沿用现有 WF,labels 对齐原型)
| id | label | dep | 完成判定 step_flags(draft) |
|---|---|---|---|
| understand 图文理解 | — | `isinstance(sr.get("understanding"), dict) and bool(...)` |
| category AI类型识别 | — | `category_id and type_id` |
| copy AI文案 | — | `ozon_title and description` |
| attrs 特征 | category | `attributes` 里有 `id ∉ {9048,23171,85}` 且 `values` 非空的项 |
| images 图集/出图 | understand | 图集有图(`images` 非空,因 images=in_gallery=1)或 `source_raw.image_types` 非空 |
| rich 富文本 | images | 草稿富文本字段非空(确认:前端 `richContentJson` 的源键名,实现时核对 `_row_to_draft`/`source_raw` 实际键) |
| publish 发布 | copy,images,rich | `ozon_product_id` 或 `status=='published'` |

> sr = draft 的 `source_raw`(dict)。判定逻辑是把现有前端 `DraftDetail.vue:wfDone` 搬到后端一份(approach A:派生状态在源头算)。

## 后端(approach A,additive,不动 legacy)
- 新增纯函数 `step_flags(draft: dict) -> dict[str,bool]`(7 键),放 `app_service.py` 或 helper 模块。逐步按上表判定。
- 扩 `App.variant_group_siblings`:每个变体条目加 `steps`(7 布尔 dict)+ `done`(完成步数 0-7)。`variant_group_siblings` 已 `get_draft` 每个 sibling → 直接喂 `step_flags`,零额外查询。
- (可选)`get_draft` 也带 `steps`(当前变体详情用)——F1c 可不做,前端从 variant 数据取当前变体的 steps。
- 测试:`step_flags` 各步真值表(unittest);`variant_group_siblings` 返回带 steps/done。

## 前端 `stores/workbench.js` 小改
- `variants` 每条现在带 `steps`/`done`(后端给)。getter `selectedVariants` 已有。新增 getter:
  - `stepProgress`:`(stepId) => { done: 选中变体里该步完成数, total: selectedVariantIds.size }`(聚合进度 N/M)。
  - 测试补充。

## 前端 `composables/usePipeline.js`(工作流状态机,从 god-component 抽新版)
- `WF`:7 步定义(id/label/eta/dep[])。`wfDepOk(step, variant)`:该变体的 dep 步是否都 done(读 variant.steps)。
- `stepStatus`(reactive `{stepId: 'idle'|'running'}`)、`batchRunningOp`(当前批量跑的步,或 'all')。
- `STEP_ACTION`:stepId → `api` 调用(understand→`api.understand`、category→`api.recognizeCategory`、copy→`api.aiGenerate`(+auto apply)、attrs→`api.autoMap`/`aiFillAttributes`、images→出图 endpoint、rich→富文本 endpoint、publish→`api.publish`)。**逐项从 god-component 的 `STEP_ACTIONS`(DraftDetail ~1802)+ workerFn 搬**,批量模式只调用 + finalize(不弹交互)。
- `runStep(stepId)`:对 `workbench.selectedVariantIds` 用 `runConcurrent(ids, 4, worker, onProgress)` 跑(worker=对单变体调 STEP_ACTION);进度写 `batchRunningOp` + 局部 `${done}/${total}`;完成后 `workbench.reload()` 刷新 steps/进度。
- `runAll()`(一键跑完):按 dep 拓扑顺序对选中变体串跑每步(跳过已 done)。
- `runConcurrent` 工具从 god-component 搬(或抽 `utils/runConcurrent.js`)。
- 接受 `workbench` 实例 + `store`(刷新草稿列表);测试 mock api + workbench。

## 前端 `components/workbench/PipelinePanel.vue`(中栏,替占位)
对照原型中栏:
- 头:"AI 智能上架工作台" + 副"选择变体 → 跑流水线 → 合并发布" + 右"⚡ 一键跑完已选 ({{ selectedCount }})"(SButton primary,`@click="pipe.runAll()"`,`:loading="!!pipe.batchRunningOp"`)。
- "{{ selectedCount }} 个变体已选中"提示条。
- 7 步行(v-for WF):序号/状态点 + label + eta + **聚合进度徽标**(`workbench.stepProgress(step.id)` → "已完成 N/N" 全绿 / "部分 M/N")+ 运行/重跑 SButton(`@click="pipe.runStep(step.id)"`,`:loading="pipe.stepStatus[step.id]==='running' || pipe.batchRunningOp===step.id"`,依赖未满足 disabled)。
- 样式 tokens,对照原型。
- 接进 `Workbench.vue` 中栏非空分支(替换"将在 F1c/F1d 实现"占位)。empty 态保留。

## 前端 `VariantCardsPane.vue` 小改(N/7 进度)
- 变体卡加进度条:`v.done`/`v.total`(7)→ 小进度条 + "{{ v.done }}/7" 文本(对齐原型卡上的 5/7)。
- 测试补充(mock variant 带 done)。

## 发布(组发布)
- 头部"发布"或 publish 步 → `api.publishGroup(groupKey, store)` 或对选中变体批量 publish(沿用 F1a `useDraftBatchOps` 的发布流 / `publish_variant_group`)。F1c 接入即可。

## 测试(Vitest + pytest)
- 后端:`step_flags` 真值表(各步 done/not done)+ `variant_group_siblings` 带 steps/done。前端全量回归 ≥ 现基线、后端 pytest 不下降。
- 前端:`usePipeline`(runStep mock api 调 N 个变体 + 进度 + reload;wfDepOk 门控;runAll 顺序)、`PipelinePanel`(渲染 7 步 + 聚合进度 + 运行按钮门控)、`workbench.stepProgress`、`VariantCardsPane` N/7。
- gating:前端新测试过 + 失败数 ≤ 32(历史基线)+ `npm run build`;后端 pytest 全绿(≥673)。

## 非目标(后续/不碰)
- F1d:详情多 tab + 交互式提案/计划/特征逐项编辑 + 图片 tab(接素材/图集后端)。
- 不动 legacy `DraftDetail.vue`/`Collect.vue`(保留兜底)。
- 不重构后端 AI 动作本身(只加 step_flags 派生 + enrich)。
- 不做单步的交互式参数面板(批量只调默认 + finalize)。
