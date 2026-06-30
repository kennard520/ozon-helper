# F1d-3b 图片 tab AI 出图（图集计划）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。逐任务 TDD。

**Goal:** 图片 tab AI 出图：AI 设计图集方案 → 按槽生成图（生成图直接进图集，F1d-3a 图集区自动显示）。无候选阶段。

**Architecture:** `useImagePlan` composable（plan + design/load/generateSlot/generateAll）+ `AiImagePanel.vue`（设计/刷新/一键出全部 + 槽位列表）接入 ImagesTab 顶部。零后端改动，复用 designImagePlan/imagePlan/generatePlanSlot。

**Tech Stack:** Vue 3.5、Element Plus、Vitest。命令在 `apps/webui/frontend/` 跑 `npm run test`。

> 关键：generatePlanSlot 同步阻塞(AI 生图 10-30s)、生成图直接进图集；plan slot 形状 `{slot_id,role,label,action,source_idx,heading,bullets,scene_hint,prompt,status('todo'|'applied'),candidate_url}`。

---

### Task 1: useImagePlan composable

**Files:**
- Create: `apps/webui/frontend/src/composables/useImagePlan.js`
- Test: `apps/webui/frontend/src/composables/useImagePlan.test.js`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/composables/useImagePlan.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
vi.mock('../api.js', () => ({ api: {
  imagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [
    { slot_id: 's0', label: '白底主图', action: 'white', status: 'todo' },
    { slot_id: 's1', label: '场景图', action: 'scene', status: 'applied', candidate_url: 'http://g/s1.jpg' },
  ] }),
  designImagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [
    { slot_id: 's0', label: '白底主图', action: 'white' },
  ], count: 1, fallback: false }),
  generatePlanSlot: vi.fn().mockResolvedValue({ ok: true, slot_id: 's0', candidate: 'http://g/s0.jpg', draft: { id: 7 } }),
} }))
import { api } from '../api.js'
import { useImagePlan } from './useImagePlan.js'

beforeEach(() => { vi.clearAllMocks() })
const draft = () => ref({ id: 7 })

describe('useImagePlan', () => {
  it('loadPlan 调 imagePlan 填 plan + 派生计数', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    await p.loadPlan()
    expect(api.imagePlan).toHaveBeenCalledWith(7, false)
    expect(p.plan.value.length).toBe(2)
    expect(p.todoCount.value).toBe(1)
    expect(p.appliedCount.value).toBe(1)
  })

  it('designPlan 调 designImagePlan 后 loadPlan(true)', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    await p.designPlan(8)
    expect(api.designImagePlan).toHaveBeenCalledWith(7, 8)
    expect(api.imagePlan).toHaveBeenCalledWith(7, true)
  })

  it('generateSlot 调 generatePlanSlot + onChange + 重 loadPlan', async () => {
    const onChange = vi.fn()
    const p = useImagePlan(draft(), { onChange })
    await p.generateSlot('s0')
    expect(api.generatePlanSlot).toHaveBeenCalledWith(7, 's0')
    expect(onChange).toHaveBeenCalled()
    expect(api.imagePlan).toHaveBeenCalled()
  })

  it('generateAll 仅对 todo 槽串行生成', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    await p.loadPlan()            // plan: s0 todo, s1 applied
    await p.generateAll()
    expect(api.generatePlanSlot).toHaveBeenCalledTimes(1)
    expect(api.generatePlanSlot).toHaveBeenCalledWith(7, 's0')
  })

  it('genState 标记生成中', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    const pr = p.generateSlot('s0')
    expect(p.genState.s0).toBe(true)
    await pr
    expect(p.genState.s0).toBe(false)
  })
})
```

- [ ] **Step 2: 跑红** `npm run test -- useImagePlan` → FAIL

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/composables/useImagePlan.js`:
```js
import { ref, reactive, computed } from 'vue'
import { api } from '../api.js'

export function useImagePlan(draftRef, { onChange } = {}) {
  const plan = ref([])
  const loading = ref(false)
  const genState = reactive({})        // slot_id -> bool 生成中
  const fire = () => { if (typeof onChange === 'function') return onChange() }
  const did = () => { const d = draftRef.value || {}; return d.id }

  const todoCount = computed(() => plan.value.filter((s) => s.status !== 'applied').length)
  const appliedCount = computed(() => plan.value.filter((s) => s.status === 'applied').length)

  async function loadPlan(force = false) {
    const id = did(); if (id == null) return
    loading.value = true
    try {
      const r = await api.imagePlan(id, force)
      plan.value = (r && r.plan) || []
    } finally { loading.value = false }
  }

  async function designPlan(target = 10) {
    const id = did(); if (id == null) return
    loading.value = true
    try {
      const r = await api.designImagePlan(id, target)
      await loadPlan(true)
      return r
    } finally { loading.value = false }
  }

  async function generateSlot(slotId) {
    const id = did(); if (id == null) return
    genState[slotId] = true
    try {
      await api.generatePlanSlot(id, slotId)
      await fire()
      await loadPlan()
    } finally { genState[slotId] = false }
  }

  async function generateAll() {
    const todo = plan.value.filter((s) => s.status !== 'applied').map((s) => s.slot_id)
    for (const sid of todo) { await generateSlot(sid) }   // 串行,避免并发打爆生图接口
  }

  return { plan, loading, genState, todoCount, appliedCount, loadPlan, designPlan, generateSlot, generateAll }
}
```

- [ ] **Step 4: 跑绿** `npm run test -- useImagePlan` → PASS（5 用例）

- [ ] **Step 5: 提交**

```bash
git add apps/webui/frontend/src/composables/useImagePlan.js apps/webui/frontend/src/composables/useImagePlan.test.js
git commit -m "feat(images): useImagePlan composable(AI设计图集+按槽生成直进图集+一键出全部)"
```

---

### Task 2: AiImagePanel.vue + 接入 ImagesTab

**Files:**
- Create: `apps/webui/frontend/src/components/workbench/AiImagePanel.vue`
- Test: `apps/webui/frontend/src/components/workbench/AiImagePanel.test.js`
- Modify: `apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/components/workbench/AiImagePanel.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
vi.mock('../../../api.js', () => ({ api: {
  imagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [
    { slot_id: 's0', label: '白底主图', action: 'white', status: 'todo' },
    { slot_id: 's1', label: '场景图', action: 'scene', status: 'applied', candidate_url: 'http://g/s1.jpg' },
  ] }),
  designImagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [], count: 0 }),
  generatePlanSlot: vi.fn().mockResolvedValue({ ok: true, draft: { id: 7 } }),
} }))
import { api } from '../../../api.js'
import AiImagePanel from './AiImagePanel.vue'

beforeEach(() => { vi.clearAllMocks() })
function factory() {
  return mount(AiImagePanel, { props: { draft: { id: 7 } } })
}

describe('AiImagePanel', () => {
  it('挂载自动 loadPlan 渲槽位', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await nextTick()
    expect(api.imagePlan).toHaveBeenCalled()
    expect(w.text()).toContain('白底主图'); expect(w.text()).toContain('场景图')
  })
  it('「AI 设计图集」触发 designImagePlan', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve()
    const btn = w.findAll('button').find((b) => b.text().includes('设计'))
    await btn.trigger('click')
    expect(api.designImagePlan).toHaveBeenCalledWith(7, expect.any(Number))
  })
  it('槽位「生成」触发 generatePlanSlot', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await nextTick()
    const btn = w.findAll('button').find((b) => b.text().includes('生成'))
    await btn.trigger('click')
    expect(api.generatePlanSlot).toHaveBeenCalledWith(7, 's0')
  })
})
```

- [ ] **Step 2: 跑红** `npm run test -- AiImagePanel` → FAIL

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/components/workbench/AiImagePanel.vue`:
```vue
<script setup>
import { toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useImagePlan } from '../../composables/useImagePlan.js'
import { SButton, SBadge } from '../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['changed'])
const draftRef = toRef(props, 'draft')
const p = useImagePlan(draftRef, { onChange: () => emit('changed') })

onMounted(() => { p.loadPlan() })

async function doDesign() {
  try { await p.designPlan(10); ElMessage.success('已生成图集方案') }
  catch (e) { ElMessage.warning(`设计失败：${e && e.message ? e.message : e}`) }
}
async function doGen(slotId) {
  try { await p.generateSlot(slotId) }
  catch (e) { ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`) }
}
async function doGenAll() {
  try { await p.generateAll(); ElMessage.success('已出全部') }
  catch (e) { ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`) }
}
const ACTION_LABEL = { white: '白底', localize: '俄化', scene: '场景', infographic: '信息图' }
</script>

<template>
  <section class="ai-panel">
    <div class="ai-panel__bar">
      <span class="ai-panel__title">AI 出图</span>
      <SButton size="sm" variant="primary" :loading="p.loading.value" @click="doDesign">AI 设计图集</SButton>
      <SButton size="sm" @click="p.loadPlan(true)">刷新计划</SButton>
      <SButton v-if="p.todoCount.value" size="sm" @click="doGenAll">一键出全部（{{ p.todoCount.value }}）</SButton>
    </div>

    <div v-if="p.plan.value.length" class="ai-panel__slots">
      <div v-for="s in p.plan.value" :key="s.slot_id" class="ai-slot">
        <span class="ai-slot__label">{{ s.label || s.slot_id }}</span>
        <SBadge variant="info">{{ ACTION_LABEL[s.action] || s.action }}</SBadge>
        <SBadge :variant="s.status === 'applied' ? 'success' : 'neutral'">
          {{ s.status === 'applied' ? '已出图' : '待做' }}
        </SBadge>
        <SButton size="sm" :loading="!!p.genState[s.slot_id]" @click="doGen(s.slot_id)">
          {{ s.status === 'applied' ? '重出' : '生成' }}
        </SButton>
      </div>
    </div>
    <div v-else class="ai-panel__empty">点「AI 设计图集」据看图理解设计槽位方案。</div>
  </section>
</template>

<style scoped>
.ai-panel{margin-bottom:var(--sp-5,20px);padding:var(--sp-3,12px);border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);background:var(--c-primary-50,#faf7ff)}
.ai-panel__bar{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-2,8px)}
.ai-panel__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.ai-panel__slots{display:flex;flex-direction:column;gap:6px}
.ai-slot{display:flex;align-items:center;gap:var(--sp-2,8px);font-size:var(--fs-sm,13px)}
.ai-slot__label{min-width:120px}
.ai-panel__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888)}
</style>
```
> 注：核对 `SBadge` 是否支持 `variant` prop（F0 建的）。若 SBadge 无 variant，则状态用文字/类名表达，去掉 variant 绑定。测试只断言文本「白底主图/场景图」、设计/生成按钮触发，不依赖 SBadge 内部。

- [ ] **Step 4: 跑绿** `npm run test -- AiImagePanel` → PASS（3 用例）

- [ ] **Step 5: 接入 ImagesTab**

`apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue`：
- 顶部 import 加 `import AiImagePanel from '../AiImagePanel.vue'`
- 模板最上面（`<div class="images-tab">` 内、图集段之前）插：
  `<AiImagePanel :draft="draft" @changed="emit('saved')" />`

- [ ] **Step 6: 全量 + 提交**

Run: `npm run test`（≤32 基线不新增）
```bash
git add apps/webui/frontend/src/components/workbench/AiImagePanel.vue apps/webui/frontend/src/components/workbench/AiImagePanel.test.js apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue
git commit -m "feat(images): AiImagePanel(AI设计图集+按槽生成+一键出全部)接入 ImagesTab 顶部"
```

---

### Task 3: 产品文档同步 + 收尾

**Files:**
- Modify: `docs/product/material-gallery.md`（§4 F1d-3b 改已完成）
- Modify: `docs/product/workbench.md`（图片 tab 行 + 变更历史）

- [ ] **Step 1: 更新文档**

`material-gallery.md` §4「F1d-3b AI 出图 — 待建」改为已完成：useImagePlan + AiImagePanel；流程 designImagePlan→槽位→generatePlanSlot(直进图集)；纠正「无候选阶段」。`workbench.md` 图片 tab 行补 AI 出图、变更历史加一行。

- [ ] **Step 2: 提交**

```bash
git add docs/product/material-gallery.md docs/product/workbench.md
git commit -m "docs(product): 图片 tab AI 出图(F1d-3b)同步"
```

---

## Controller 复核（每任务后 + 全部后）
- 每任务：读 diff、跑该任务测试、TDD 红→绿。
- 全部后：`npm run test`(≤32) + `npm run build`；起本地后端**端到端验**（种带 understanding+图集图的草稿，curl design-image-plan→image-plan 确认返槽位+status、generate-plan-slot 后图进 images；前端浏览器看 AiImagePanel 槽位渲染+状态）。生图真调 AI 需 key——无 key 时验到「设计方案返回槽位 + 生成按钮触发端点（报错 toast）」即可，记录未真出图。验完清理环境。
