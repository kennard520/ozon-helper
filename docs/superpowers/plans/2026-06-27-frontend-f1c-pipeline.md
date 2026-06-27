# 前端重建 F1c:AI 上架工作台流水线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。Steps 用 checkbox。

**Goal:** 中栏建 AI 流水线面板——7 步 + 每变体进度(后端 step_flags)+ 批量跑选中变体 + 一键跑完,接现有 AI 动作 endpoint。

**Architecture:** approach A:后端 `step_flags(draft)` 派生 7 步完成标志 + enrich `variant_group_siblings`(每变体 steps/done),前端无 N+1。前端 `usePipeline` 状态机(依赖门控 + runConcurrent 批量跑)+ `PipelinePanel`(中栏)读 workbench 聚合进度。不动 legacy `DraftDetail.vue`/`Collect.vue`。

**Tech Stack:** 后端 SQLAlchemy/pytest;前端 Vue3 `<script setup>`/Pinia/Vitest。

**全局约定:** 后端在仓库根 `/e/personal/ozon-helper`,`python -m uv run pytest ...`,**≥673 不下降**;前端在 `apps/webui/frontend`,`npm test`(失败数 ≤ **32** 历史基线,不新增)+ `npm run build` 成功。中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。视觉对照原型 `变体工作台.dc.html` 中栏。参考 spec `docs/superpowers/specs/2026-06-27-frontend-f1c-pipeline-design.md`;源逻辑 `DraftDetail.vue`(`wfRun` ~1801、`wfDone` ~1813、`runConcurrent` ~1860)。

**7 步 + 每步 backend 调用序列(runOne)**(从 `wfRun` 追得,已确认 endpoint):
| step | runOne(id) 序列 | step_flags 判定 |
|---|---|---|
| understand | `api.understand(id)` | `source_raw.understanding` 是非空 dict |
| category | `api.recognizeCategory(id)` | `category_id && type_id` |
| copy | `api.aiGenerate(id)` → `api.aiProposalApply(id)` | `ozon_title && description` |
| attrs | `api.autoMap(id)` | `attributes` 有 id∉{9048,23171,85} 且 values 非空 |
| images | `api.designImagePlan(id,10)` → `api.imagePlan(id,false)` | `images` 非空 或 `source_raw.image_types` 非空 |
| rich | `api.makeRichContent(id,{})` | 富文本字段非空(确认前端 `richContentJson` 源键) |
| publish | 走 F1a `useDraftBatchOps.doBatchPublish`(带确认,不可逆) | `ozon_product_id` 或 `status=='published'` |

---

## File Structure
| 文件 | 职责 |
|---|---|
| `apps/webui/src/webui/app_service.py` | `step_flags(draft)` + enrich `variant_group_siblings` |
| `apps/webui/tests/test_step_flags.py` | step_flags 真值表 + enrich 测试 |
| `frontend/src/stores/workbench.js` | `stepProgress(stepId)` getter |
| `frontend/src/utils/runConcurrent.js` | 并发跑工具(从 god-component 抽) |
| `frontend/src/composables/usePipeline.js` | 流水线状态机 + runOne/runStep/runAll |
| `frontend/src/components/workbench/PipelinePanel.vue` | 中栏流水线 UI |
| `frontend/src/components/workbench/VariantCardsPane.vue` | 加 N/7 进度 |
| `frontend/src/views/Workbench.vue` | 中栏接 PipelinePanel |

---

## Task 1:后端 step_flags + enrich variant_group_siblings

**Files:**
- Modify: `apps/webui/src/webui/app_service.py`(加 `step_flags` 模块函数 + `variant_group_siblings` ~3507 enrich)
- Test: `apps/webui/tests/test_step_flags.py`

- [ ] **Step 1: 确认富文本字段** —— grep 前端 `richContentJson` 定义(`frontend/src/components/DraftDetail.vue`)看它读草稿哪个键(很可能 `source_raw.rich_content` / `rich_content_json` / 或 `description` 含 html)。记下实际键名用于 `rich` 判定。

- [ ] **Step 2: 写测试(先红)** `apps/webui/tests/test_step_flags.py`:
```python
from webui.app_service import step_flags

def _d(**kw):
    base = {"source_raw": {}, "attributes": [], "category_id": "", "type_id": "",
            "ozon_title": "", "description": "", "images": [], "ozon_product_id": "", "status": "draft"}
    base.update(kw); return base

def test_understand():
    assert step_flags(_d(source_raw={"understanding": {"x": 1}}))["understand"] is True
    assert step_flags(_d())["understand"] is False

def test_category_copy_publish():
    assert step_flags(_d(category_id="1", type_id="2"))["category"] is True
    assert step_flags(_d(ozon_title="T", description="D"))["copy"] is True
    assert step_flags(_d(status="published"))["publish"] is True
    assert step_flags(_d(ozon_product_id="999"))["publish"] is True

def test_attrs_excludes_placeholders():
    # 只有 9048(型号名)→ 不算已填
    assert step_flags(_d(attributes=[{"id": 9048, "values": [{"value": "x"}]}]))["attrs"] is False
    # 有真类目属性 → 已填
    assert step_flags(_d(attributes=[{"id": 1234, "values": [{"value": "x"}]}]))["attrs"] is True

def test_images():
    assert step_flags(_d(images=["a.jpg"]))["images"] is True
    assert step_flags(_d(source_raw={"image_types": {"a": "主图"}}))["images"] is True
    assert step_flags(_d())["images"] is False
```

- [ ] **Step 3: 跑确认红** `cd /e/personal/ozon-helper && python -m uv run python -m pytest apps/webui/tests/test_step_flags.py -q -p no:cacheprovider 2>&1 | tail -6` → FAIL。

- [ ] **Step 4: 实现 `step_flags`**(`app_service.py` 模块级函数,放 App 类前):
```python
_ATTR_EXCL = {9048, 23171, 85}

def step_flags(draft: dict) -> dict:
    """从草稿字段派生 7 步完成标志(等价前端 DraftDetail.wfDone,移到源头算)。"""
    d = draft or {}
    sr = d.get("source_raw") or {}
    if isinstance(sr, str):
        from webui.drafts import loads_json  # noqa: PLC0415
        sr = loads_json(sr, {}) or {}
    und = sr.get("understanding")
    attrs = d.get("attributes") if isinstance(d.get("attributes"), list) else []
    def _attr_done(a):
        try:
            return (a and a.get("id") is not None and int(a["id"]) not in _ATTR_EXCL
                    and isinstance(a.get("values"), list) and len(a["values"]) > 0)
        except (TypeError, ValueError):
            return False
    rich = bool(sr.get("rich_content") or sr.get("rich_content_json"))  # ← 用 Step1 确认的实际键
    return {
        "understand": isinstance(und, dict) and bool(und),
        "category": bool(d.get("category_id") and d.get("type_id")),
        "copy": bool(d.get("ozon_title") and d.get("description")),
        "attrs": any(_attr_done(a) for a in attrs),
        "images": bool(d.get("images")) or bool(sr.get("image_types")),
        "rich": rich,
        "publish": bool(d.get("ozon_product_id")) or d.get("status") == "published",
    }
```
(若 Step1 发现 rich 在别的字段,改 `rich` 那行。)

- [ ] **Step 5: enrich variant_group_siblings**(`app_service.py` ~3507)——它已对每个 sibling `d`(full draft)循环。在 append 的 dict 里加 `"steps": step_flags(d)` + `"done": sum(step_flags(d).values())`(算一次复用):
```python
            flags = step_flags(d)
            out.append({"id": d.get("id"),
                        "spec": ...,  # 原有
                        "price": d.get("price"), "status": d.get("status"),
                        "image": ...,  # 原有
                        "current": d.get("id") == draft_id,
                        "steps": flags, "done": sum(1 for v in flags.values() if v)})
```
(保留原有字段,只加 steps/done。)在 test 里加一条:`variant_group_siblings` 返回的 variant 带 `steps`(7 键)+ `done` int。

- [ ] **Step 6: 跑测试 + 全量回归 + 提交**
```bash
python -m uv run python -m pytest apps/webui/tests/test_step_flags.py -q -p no:cacheprovider 2>&1 | tail -5   # PASS
python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider 2>&1 | tail -3  # ≥673
python -m ruff check --select I --fix apps/webui/src/webui/app_service.py apps/webui/tests/test_step_flags.py 2>&1 | tail -2
git add apps/webui/src/webui/app_service.py apps/webui/tests/test_step_flags.py
git commit -m "feat(pipeline): 后端 step_flags 派生7步完成标志 + variant-group 每变体 steps/done(approach A)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2:workbench store stepProgress getter

**Files:**
- Modify: `frontend/src/stores/workbench.js`(加 getter)
- Test: `frontend/src/stores/workbench.test.js`(追加)

- [ ] **Step 1: 追加测试(先红)** 在 workbench.test.js 末尾:
```js
it('stepProgress 聚合选中变体某步完成数', async () => {
  api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2, variants: [
    { id: 1, steps: { copy: true, images: false }, done: 1 },
    { id: 2, steps: { copy: true, images: true }, done: 2 }] })
  const wb = useWorkbenchStore(); await wb.loadForDraft(1)
  expect(wb.stepProgress('copy')).toEqual({ done: 2, total: 2 })
  expect(wb.stepProgress('images')).toEqual({ done: 1, total: 2 })
  wb.clearSelection(); wb.toggleVariant(1)
  expect(wb.stepProgress('images')).toEqual({ done: 0, total: 1 })
})
```

- [ ] **Step 2: 跑确认红** → FAIL。

- [ ] **Step 3: 加 getter**(workbench.js getters 里):
```js
    stepProgress: (s) => (stepId) => {
      const sel = s.variants.filter(v => s.selectedVariantIds.has(v.id))
      return { done: sel.filter(v => v.steps && v.steps[stepId]).length, total: sel.length }
    },
```

- [ ] **Step 4: 跑确认绿 + 提交**
```bash
cd /e/personal/ozon-helper/apps/webui/frontend && npm test src/stores/workbench.test.js 2>&1 | tail -5
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/stores/workbench.js apps/webui/frontend/src/stores/workbench.test.js
git commit -m "feat(pipeline): workbench stepProgress 聚合每步进度

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3:usePipeline 状态机 + runConcurrent

**Files:**
- Create: `frontend/src/utils/runConcurrent.js`、`frontend/src/composables/usePipeline.js`、`frontend/src/composables/pipeline.test.js`

- [ ] **Step 1: `runConcurrent.js`** —— 从 `DraftDetail.vue` 的 `runConcurrent`(~1860)搬成独立工具:
```js
export async function runConcurrent(tasks, concurrency, workerFn, onProgress) {
  const queue = [...tasks]; const results = []; let completed = 0; const total = tasks.length
  const worker = async () => {
    while (queue.length > 0) {
      const task = queue.shift()
      try { results.push({ task, success: true, result: await workerFn(task) }) }
      catch (err) { results.push({ task, success: false, error: err }) }
      finally { completed++; if (onProgress) onProgress(completed, total) }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, total) }, worker))
  return results
}
```

- [ ] **Step 2: 写测试(先红)** `frontend/src/composables/pipeline.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: 'G', count: 2,
    variants: [{ id: 1, steps: {}, done: 0 }, { id: 2, steps: {}, done: 0 }] }),
  understand: vi.fn().mockResolvedValue({}), recognizeCategory: vi.fn().mockResolvedValue({}),
  aiGenerate: vi.fn().mockResolvedValue({}), aiProposalApply: vi.fn().mockResolvedValue({}),
  autoMap: vi.fn().mockResolvedValue({}), designImagePlan: vi.fn().mockResolvedValue({}),
  imagePlan: vi.fn().mockResolvedValue({}), makeRichContent: vi.fn().mockResolvedValue({}),
} }))
import { api } from '../api.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import { usePipeline } from './usePipeline.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('usePipeline', () => {
  it('runStep(understand) 对选中变体各调一次 + reload', async () => {
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    const reload = vi.spyOn(wb, 'reload')
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('understand')
    expect(api.understand).toHaveBeenCalledTimes(2)  // 2 选中变体
    expect(reload).toHaveBeenCalled()
    expect(pipe.stepStatus.understand).toBe('idle')
  })
  it('runStep(copy) 每变体 aiGenerate + aiProposalApply', async () => {
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('copy')
    expect(api.aiGenerate).toHaveBeenCalledTimes(2)
    expect(api.aiProposalApply).toHaveBeenCalledTimes(2)
  })
  it('wfDepOk:attrs 依赖 category', () => {
    const wb = useWorkbenchStore()
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    expect(pipe.wfDepOk('attrs', { steps: { category: false } })).toBe(false)
    expect(pipe.wfDepOk('attrs', { steps: { category: true } })).toBe(true)
    expect(pipe.wfDepOk('understand', { steps: {} })).toBe(true)  // 无依赖
  })
})
```

- [ ] **Step 3: 跑确认红** → FAIL。

- [ ] **Step 4: 实现 `usePipeline.js`**
```js
import { reactive, ref } from 'vue'
import { api } from '../api.js'
import { runConcurrent } from '../utils/runConcurrent.js'

export const WF = [
  { id: 'understand', label: '图文理解', eta: '~40s', dep: [] },
  { id: 'category', label: 'AI类型识别', eta: '~20s', dep: [] },
  { id: 'copy', label: 'AI文案', eta: '~90s', dep: [] },
  { id: 'attrs', label: '特征', eta: '~10s', dep: ['category'] },
  { id: 'images', label: '图集/出图', eta: '~2-3min', dep: ['understand'] },
  { id: 'rich', label: '富文本', eta: '即时', dep: ['images'] },
  { id: 'publish', label: '发布', eta: '~30s', dep: ['copy', 'images', 'rich'] },
]
// 单变体单步的 backend 调用序列(批量模式:只调 endpoint + finalize,不弹交互)
const RUN_ONE = {
  understand: (id) => api.understand(id),
  category: (id) => api.recognizeCategory(id),
  copy: async (id) => { await api.aiGenerate(id); await api.aiProposalApply(id) },
  attrs: (id) => api.autoMap(id),
  images: async (id) => { await api.designImagePlan(id, 10); await api.imagePlan(id, false) },
  rich: (id) => api.makeRichContent(id, {}),
}

export function usePipeline(workbench, store) {
  const stepStatus = reactive(Object.fromEntries(WF.map(s => [s.id, 'idle'])))
  const batchRunningOp = ref('')

  function wfDepOk(stepId, variant) {
    const step = WF.find(s => s.id === stepId); if (!step) return false
    const flags = (variant && variant.steps) || {}
    return step.dep.every(d => flags[d])
  }
  async function runStep(stepId) {
    if (stepId === 'publish') return  // 发布走 useDraftBatchOps(带确认),由 PipelinePanel 接
    const ids = [...workbench.selectedVariantIds]
    if (!ids.length || !RUN_ONE[stepId]) return
    stepStatus[stepId] = 'running'; batchRunningOp.value = stepId
    try {
      await runConcurrent(ids, 4, (id) => RUN_ONE[stepId](id), () => {})
      await workbench.reload()
      if (store && store.loadDrafts) store.loadDrafts()
    } finally { stepStatus[stepId] = 'idle'; batchRunningOp.value = '' }
  }
  async function runAll() {
    batchRunningOp.value = 'all'
    try {
      for (const step of WF) {
        if (step.id === 'publish' || !RUN_ONE[step.id]) continue
        await runStep(step.id)
      }
    } finally { batchRunningOp.value = '' }
  }
  return { WF, stepStatus, batchRunningOp, wfDepOk, runStep, runAll }
}
```
> 注:`copy` 的 `aiGenerate`+`aiProposalApply`、`images` 的 `designImagePlan`+`imagePlan` 序列已从 god-component `doAiGenerate/applyProposal`、`doAutoImagesFor` 追得。若某 endpoint 名在 api.js 不存在,grep api.js 找等价名修正。

- [ ] **Step 5: 跑确认绿 + 提交**
```bash
cd /e/personal/ozon-helper/apps/webui/frontend && npm test src/composables/pipeline.test.js 2>&1 | tail -6
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/utils/runConcurrent.js apps/webui/frontend/src/composables/usePipeline.js apps/webui/frontend/src/composables/pipeline.test.js
git commit -m "feat(pipeline): usePipeline 状态机(依赖门控 + runConcurrent 批量跑选中变体 + runAll)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4:PipelinePanel.vue(中栏)+ 接 Workbench

**Files:**
- Create: `frontend/src/components/workbench/PipelinePanel.vue`、`.../pipeline-panel.test.js`
- Modify: `frontend/src/views/Workbench.vue`(中栏非空分支接 PipelinePanel)

- [ ] **Step 1: 写测试(先红)** `pipeline-panel.test.js`:mock pinia + workbench(variants 带 steps),mount PipelinePanel,断言:渲染 7 步 label、某步聚合进度文本(如 copy 全完成显 "2/2")、点"运行"调 `usePipeline.runStep`(可 spy)。(参照 variantcards.test.js 的 setup 骨架。)

- [ ] **Step 2: 跑确认红** → FAIL。

- [ ] **Step 3: 实现 `PipelinePanel.vue`**(对照原型中栏):
  - `import { usePipeline, WF } from '../../composables/usePipeline.js'`、`useWorkbenchStore`、`useAppStore`、`src/ui` 组件。
  - `const wb = useWorkbenchStore(); const store = useAppStore(); const pipe = usePipeline(wb, store)`。
  - 头:"AI 智能上架工作台" + 副标 + "⚡ 一键跑完已选 ({{ wb.selectedVariantIds.size }})" SButton(`@click="pipe.runAll()"` `:loading="!!pipe.batchRunningOp"`)。
  - "{{ wb.selectedVariantIds.size }} 个变体已选中"条。
  - v-for WF as step:序号/状态 + label + eta + 进度徽标(`const p = wb.stepProgress(step.id)` → `p.done===p.total && p.total>0 ? 已完成 p.done/p.total (success) : 部分 p.done/p.total`)+ 运行/重跑 SButton(`@click="pipe.runStep(step.id)"` `:loading="pipe.stepStatus[step.id]==='running'"` `:disabled="!!pipe.batchRunningOp"`)。publish 步的按钮 → emit `publish-group`(父接 useDraftBatchOps 发布)。
  - 样式 tokens 对照原型。

- [ ] **Step 4: 接 Workbench.vue** —— 中栏 `v-else`(store.selectedDraft 非空)分支:把"将在 F1c/F1d 实现"占位换成 `<PipelinePanel @publish-group="ops.doBatchPublish([...wb.selectedVariantIds])" />`(import PipelinePanel;wb=useWorkbenchStore;ops 是 F1a 的 useDraftBatchOps)。保留 empty 态。

- [ ] **Step 5: 跑测试 + 构建 + 提交**
```bash
cd /e/personal/ozon-helper/apps/webui/frontend
npm test src/components/workbench/pipeline-panel.test.js 2>&1 | tail -6
npm run build 2>&1 | tail -3
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/PipelinePanel.vue apps/webui/frontend/src/components/workbench/pipeline-panel.test.js apps/webui/frontend/src/views/Workbench.vue
git commit -m "feat(pipeline): PipelinePanel 中栏(7步+聚合进度+运行/重跑/一键跑完)接入工作台

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5:VariantCardsPane N/7 进度

**Files:**
- Modify: `frontend/src/components/workbench/VariantCardsPane.vue`(卡加进度)
- Test: `.../variantcards.test.js`(追加)

- [ ] **Step 1: 追加测试(先红)** variant 加 `done:3`,断言卡上出现 "3/7" 文本。
- [ ] **Step 2: 跑确认红** → FAIL。
- [ ] **Step 3: 卡里加** `<div class="vcard__prog">{{ v.done ?? 0 }}/7</div>` + 小进度条(`width: (v.done/7*100)%`),tokens 样式。
- [ ] **Step 4: 跑测试 + 构建 + 提交**
```bash
cd /e/personal/ozon-helper/apps/webui/frontend && npm test src/components/workbench/variantcards.test.js 2>&1 | tail -5 && npm run build 2>&1 | tail -3
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/VariantCardsPane.vue apps/webui/frontend/src/components/workbench/variantcards.test.js
git commit -m "feat(pipeline): 变体卡 N/7 进度条

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6:收尾 + 视觉验收

- [ ] **Step 1: 全量** 后端 `pytest`(≥673)+ 前端 `npm test`(失败数 ≤ 32)+ `npm run build`。
- [ ] **Step 2: controller 视觉验收**:本地后端(灌同组变体 + 给某些变体填 title/category 制造不同步骤完成度)+ 临时代理 + dev + 登录 → 确认:① 中栏 7 步面板渲染;② 选中变体 → 各步聚合进度(N/M)正确;③ 变体卡 N/7;④ 点"运行某步"→ 调用 + 进度刷新(可对 mock/真实 AI 视情况;至少 understand 这类轻动作);⑤ 一键跑完 loading。验完还原 vite.config + 清理。
- [ ] **Step 3: 有收尾改动则提交**。

---

## Self-Review
- **Spec 覆盖**:① step_flags+enrich→T1;② stepProgress→T2;③ usePipeline(状态机/依赖/runStep/runAll)→T3;④ PipelinePanel→T4;⑤ 变体卡N/7→T5;⑥ 发布走 useDraftBatchOps→T4(publish-group emit)。全覆盖。
- **占位符**:rich 字段名 T1 Step1 明确要求 grep 确认(给了候选键);runOne 序列已从 god-component 追得真实 endpoint(copy/images 两段)。非空泛。
- **契约一致**:`step_flags(draft)->{7 bool}`、variant `.steps`/`.done`、`stepProgress(id)->{done,total}`、`usePipeline(wb,store)->{WF,stepStatus,batchRunningOp,wfDepOk,runStep,runAll}` 前后一致;publish 走 F1a useDraftBatchOps(不在 RUN_ONE)。
- **风险**:① 真实 AI endpoint 调用慢/要 key——视觉验收对重 AI 步可只验调用发起;② publish 不可逆——只走带确认的 doBatchPublish,RUN_ONE 不含 publish,runAll 跳过 publish;③ 某 image/rich endpoint 名若 api.js 不符,T3 Step4 注已要求 grep 修正。
