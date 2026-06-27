# F1d-4 AI 提案审阅（ai_proposal）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。逐任务 TDD。

**Goal:** DetailTabs 顶部 AI 文案草案审阅面板：生成草案 → 逐项审(标题/简介/标签/AI属性/缺失必填)→ 应用到正式字段 或 放弃。补全 legacy 漏渲 attributes。

**Architecture:** `useProposal` composable（proposal 派生 + patch/apply/discard/generate）+ `ProposalPanel.vue`（空态生成 / 审阅态编辑）接 DetailTabs 顶部，`@applied→fm.load+wb.reload`。零后端改动，复用 aiGenerate/aiCopy/aiProposalPatch/aiProposalApply。

**Tech Stack:** Vue 3.5、Element Plus、Vitest。命令在 `apps/webui/frontend/` 跑 `npm run test`。

> 形状：`draft.ai_proposal = {fields:{ozon_title,description,...}, attributes:[{id,name,value,source('ai'|'missing'),required?}], ...}` 或 null。标签=attr id 23171。patch op ∈ edit_field/delete_field/edit_attr/delete_attr/discard。

---

### Task 1: useProposal composable

**Files:**
- Create: `apps/webui/frontend/src/composables/useProposal.js`
- Test: `apps/webui/frontend/src/composables/useProposal.test.js`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/composables/useProposal.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
vi.mock('../api.js', () => ({ api: {
  aiProposalPatch: vi.fn().mockResolvedValue({ ok: true, proposal: { fields: { ozon_title: '改后' }, attributes: [] } }),
  aiProposalApply: vi.fn().mockResolvedValue({ ok: true, draft: { id: 7, ai_proposal: null }, unmapped: [] }),
  aiGenerate: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
  aiCopy: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
} }))
import { api } from '../api.js'
import { useProposal } from './useProposal.js'

beforeEach(() => { vi.clearAllMocks() })
function mkDraft(prop) { return ref({ id: 7, ai_proposal: prop }) }
const PROP = {
  fields: { ozon_title: 'T', description: 'D' },
  attributes: [
    { id: 100, name: '材料', value: '棉', source: 'ai' },
    { id: 23171, name: '标签', value: '#a #b', source: 'ai' },
    { id: 200, name: '颜色', value: '', source: 'missing', required: true },
  ],
}

describe('useProposal', () => {
  it('hasProposal + 派生 aiAttrs/missingAttrs/tags', () => {
    const p = useProposal(mkDraft(PROP), { onApplied: vi.fn() })
    expect(p.hasProposal.value).toBe(true)
    expect(p.aiAttrs.value.map(a => a.id)).toEqual([100])   // 排除 23171
    expect(p.missingAttrs.value.map(a => a.id)).toEqual([200])
    expect(p.tags.value).toBe('#a #b')
  })

  it('无草案 hasProposal=false', () => {
    const p = useProposal(mkDraft(null), { onApplied: vi.fn() })
    expect(p.hasProposal.value).toBe(false)
  })

  it('editField 调 patch(edit_field) 并用返回更新', async () => {
    const p = useProposal(mkDraft(PROP), { onApplied: vi.fn() })
    await p.editField('ozon_title', '改后')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'edit_field', key: 'ozon_title', value: '改后' })
    expect(p.proposal.value.fields.ozon_title).toBe('改后')
  })

  it('editAttr / deleteAttr / editTags', async () => {
    const p = useProposal(mkDraft(PROP), { onApplied: vi.fn() })
    await p.editAttr(100, '涤纶')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'edit_attr', id: 100, value: '涤纶' })
    await p.deleteAttr(100)
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'delete_attr', id: 100 })
    await p.editTags('#x')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'edit_attr', id: 23171, value: '#x' })
  })

  it('apply 调 aiProposalApply + onApplied', async () => {
    const onApplied = vi.fn()
    const p = useProposal(mkDraft(PROP), { onApplied })
    const r = await p.apply()
    expect(api.aiProposalApply).toHaveBeenCalledWith(7)
    expect(onApplied).toHaveBeenCalled()
    expect(r.unmapped).toEqual([])
  })

  it('discard 调 patch(discard) + onApplied', async () => {
    const onApplied = vi.fn()
    const p = useProposal(mkDraft(PROP), { onApplied })
    await p.discard()
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'discard' })
    expect(onApplied).toHaveBeenCalled()
  })

  it('generate(full/copy) 调对应 api + onApplied', async () => {
    const onApplied = vi.fn()
    const p = useProposal(mkDraft(null), { onApplied })
    await p.generate('full')
    expect(api.aiGenerate).toHaveBeenCalledWith(7)
    await p.generate('copy')
    expect(api.aiCopy).toHaveBeenCalledWith(7)
    expect(onApplied).toHaveBeenCalledTimes(2)
  })
})
```

- [ ] **Step 2: 跑红** `npm run test -- useProposal` → FAIL

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/composables/useProposal.js`:
```js
import { ref, computed, watch } from 'vue'
import { api } from '../api.js'

const TAG_ATTR = 23171

export function useProposal(draftRef, { onApplied } = {}) {
  const proposal = ref(null)
  const loading = ref(false)
  const fireApplied = (r) => { if (typeof onApplied === 'function') return onApplied(r) }
  const did = () => { const d = draftRef.value || {}; return d.id }

  function initFromDraft(d) {
    const p = d && d.ai_proposal
    proposal.value = p ? JSON.parse(JSON.stringify(p)) : null
  }
  watch(draftRef, (d) => initFromDraft(d), { immediate: true })

  const hasProposal = computed(() => !!proposal.value)
  const attrs = computed(() => (proposal.value && proposal.value.attributes) || [])
  const aiAttrs = computed(() => attrs.value.filter((a) => a.source === 'ai' && Number(a.id) !== TAG_ATTR))
  const missingAttrs = computed(() => attrs.value.filter((a) => a.source === 'missing'))
  const tags = computed(() => {
    const a = attrs.value.find((x) => Number(x.id) === TAG_ATTR)
    return a ? (a.value || '') : ''
  })

  async function patch(body) {
    const id = did(); if (id == null) return
    const r = await api.aiProposalPatch(id, body)
    if (r) proposal.value = r.proposal || null
    return r
  }
  const editField = (key, value) => patch({ op: 'edit_field', key, value })
  const deleteField = (key) => patch({ op: 'delete_field', key })
  const editAttr = (id, value) => patch({ op: 'edit_attr', id, value })
  const deleteAttr = (id) => patch({ op: 'delete_attr', id })
  const editTags = (value) => patch({ op: 'edit_attr', id: TAG_ATTR, value })

  async function apply() {
    const id = did(); if (id == null) return
    loading.value = true
    try {
      const r = await api.aiProposalApply(id)
      await fireApplied(r)
      return r || {}
    } finally { loading.value = false }
  }

  async function discard() {
    await patch({ op: 'discard' })
    return fireApplied()
  }

  async function generate(mode = 'full') {
    const id = did(); if (id == null) return
    loading.value = true
    try {
      const r = mode === 'copy' ? await api.aiCopy(id) : await api.aiGenerate(id)
      await fireApplied(r)
      return r || {}
    } finally { loading.value = false }
  }

  return {
    proposal, loading, hasProposal, aiAttrs, missingAttrs, tags,
    editField, deleteField, editAttr, deleteAttr, editTags,
    apply, discard, generate,
  }
}
```

- [ ] **Step 4: 跑绿** `npm run test -- useProposal` → PASS（7 用例）

- [ ] **Step 5: 提交**

```bash
git add apps/webui/frontend/src/composables/useProposal.js apps/webui/frontend/src/composables/useProposal.test.js
git commit -m "feat(detail): useProposal composable(ai_proposal 派生+逐项patch+apply/discard/generate)"
```

---

### Task 2: ProposalPanel.vue + 接入 DetailTabs

**Files:**
- Create: `apps/webui/frontend/src/components/workbench/ProposalPanel.vue`
- Test: `apps/webui/frontend/src/components/workbench/ProposalPanel.test.js`
- Modify: `apps/webui/frontend/src/components/workbench/DetailTabs.vue`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/components/workbench/ProposalPanel.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
vi.mock('../../../api.js', () => ({ api: {
  aiProposalPatch: vi.fn().mockResolvedValue({ ok: true, proposal: null }),
  aiProposalApply: vi.fn().mockResolvedValue({ ok: true, draft: { id: 7 }, unmapped: [] }),
  aiGenerate: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
  aiCopy: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
} }))
import { api } from '../../../api.js'
import ProposalPanel from './ProposalPanel.vue'

beforeEach(() => { vi.clearAllMocks() })
const PROP = {
  fields: { ozon_title: 'T俄', description: 'D俄' },
  attributes: [
    { id: 100, name: '材料', value: '棉', source: 'ai' },
    { id: 200, name: '颜色', value: '', source: 'missing', required: true },
  ],
}
function factory(ai_proposal) {
  return mount(ProposalPanel, { props: { draft: { id: 7, ai_proposal } } })
}

describe('ProposalPanel', () => {
  it('无草案：渲生成按钮，点触发 aiGenerate', async () => {
    const w = factory(null)
    const btn = w.findAll('button').find((b) => b.text().includes('生成草案'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    expect(api.aiGenerate).toHaveBeenCalledWith(7)
  })
  it('有草案：渲标题/AI属性/缺失项', () => {
    const w = factory(PROP)
    expect(w.text()).toContain('待确认')
    expect(w.text()).toContain('材料')
    expect(w.text()).toContain('颜色')
  })
  it('应用按钮触发 aiProposalApply', async () => {
    const w = factory(PROP)
    const btn = w.findAll('button').find((b) => b.text().includes('应用'))
    await btn.trigger('click')
    expect(api.aiProposalApply).toHaveBeenCalledWith(7)
  })
  it('放弃按钮触发 discard patch', async () => {
    const w = factory(PROP)
    const btn = w.findAll('button').find((b) => b.text().includes('放弃'))
    await btn.trigger('click')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'discard' })
  })
})
```

- [ ] **Step 2: 跑红** `npm run test -- ProposalPanel` → FAIL

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/components/workbench/ProposalPanel.vue`:
```vue
<script setup>
import { toRef } from 'vue'
import { ElInput, ElMessage } from 'element-plus'
import { useProposal } from '../../composables/useProposal.js'
import { SButton, SBadge } from '../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['applied'])
const draftRef = toRef(props, 'draft')
const p = useProposal(draftRef, { onApplied: (r) => emit('applied', r) })

async function doGen(mode) {
  try { await p.generate(mode); ElMessage.success('已生成草案') }
  catch (e) { ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`) }
}
async function doApply() {
  try {
    const r = await p.apply()
    if (r && r.unmapped && r.unmapped.length) ElMessage.warning(`${r.unmapped.length} 项未匹配字典，请在特征 tab 手动确认`)
    else ElMessage.success('已应用到商品')
  } catch (e) { ElMessage.warning(`应用失败：${e && e.message ? e.message : e}`) }
}
async function doDiscard() {
  try { await p.discard(); ElMessage.success('已放弃草案') }
  catch (e) { ElMessage.warning(`放弃失败：${e && e.message ? e.message : e}`) }
}
</script>

<template>
  <section class="prop">
    <!-- 空态 -->
    <div v-if="!p.hasProposal.value" class="prop__empty">
      <span class="prop__title">AI 文案草案</span>
      <SButton size="sm" variant="primary" :loading="p.loading.value" @click="doGen('full')">生成草案</SButton>
      <SButton size="sm" :loading="p.loading.value" @click="doGen('copy')">快速文案</SButton>
    </div>

    <!-- 审阅态 -->
    <div v-else class="prop__body">
      <div class="prop__head">
        <span class="prop__title">AI 待确认草案</span>
        <SButton size="sm" variant="primary" :loading="p.loading.value" @click="doApply">应用到商品</SButton>
        <SButton size="sm" @click="doDiscard">放弃</SButton>
        <SButton size="sm" @click="doGen('full')">重新生成</SButton>
      </div>

      <div class="prop__field">
        <label>俄语标题</label>
        <ElInput :model-value="(p.proposal.value.fields || {}).ozon_title || ''" @change="(v) => p.editField('ozon_title', v)" />
      </div>
      <div class="prop__field">
        <label>简介</label>
        <ElInput type="textarea" :autosize="{ minRows: 3, maxRows: 12 }"
          :model-value="(p.proposal.value.fields || {}).description || ''" @change="(v) => p.editField('description', v)" />
      </div>
      <div class="prop__field">
        <label>标签 #Хештеги</label>
        <ElInput :model-value="p.tags.value" @change="(v) => p.editTags(v)" />
      </div>

      <div v-if="p.aiAttrs.value.length" class="prop__attrs">
        <div class="prop__sub">AI 属性</div>
        <div v-for="a in p.aiAttrs.value" :key="a.id" class="prop__attr">
          <span class="prop__attr-name">{{ a.name }}</span>
          <ElInput :model-value="a.value" size="small" @change="(v) => p.editAttr(a.id, v)" />
          <SButton size="sm" @click="p.deleteAttr(a.id)">删</SButton>
        </div>
      </div>

      <div v-if="p.missingAttrs.value.length" class="prop__attrs">
        <div class="prop__sub">缺失必填（请补）</div>
        <div v-for="a in p.missingAttrs.value" :key="a.id" class="prop__attr">
          <span class="prop__attr-name"><SBadge variant="warn">必填</SBadge>{{ a.name }}</span>
          <ElInput :model-value="a.value" size="small" placeholder="补填" @change="(v) => p.editAttr(a.id, v)" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.prop{border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);background:var(--c-primary-50,#faf7ff);padding:var(--sp-3,12px);margin-bottom:var(--sp-4,16px)}
.prop__empty,.prop__head{display:flex;align-items:center;gap:var(--sp-2,8px)}
.prop__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.prop__field{margin-top:var(--sp-3,12px)}
.prop__field label{display:block;font-size:var(--fs-sm,13px);color:var(--c-text-2,#555);margin-bottom:4px}
.prop__attrs{margin-top:var(--sp-3,12px)}
.prop__sub{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555);margin-bottom:6px}
.prop__attr{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:6px}
.prop__attr-name{min-width:120px;font-size:var(--fs-sm,13px);display:flex;align-items:center;gap:4px}
</style>
```
> 注：SBadge variant 用 warn（已确认存在）。测试只断言文本/按钮触发，不依赖 ElInput 内部。若 ElInput 在 jsdom 挂载报错，测试 `global.stubs` 里 stub ElInput（保留按钮触发断言）。

- [ ] **Step 4: 跑绿** `npm run test -- ProposalPanel` → PASS（4 用例）

- [ ] **Step 5: 接入 DetailTabs**

`apps/webui/frontend/src/components/workbench/DetailTabs.vue`：
- import 加 `import ProposalPanel from './ProposalPanel.vue'`；并引入 workbench store 用于 reload（若未引入：`import { useWorkbenchStore } from '../../stores/workbench.js'` + `const wb = useWorkbenchStore()` —— 注意 DetailTabs 已 `import { useWorkbenchStore }`，复用现有 `wb`）。
- script 加 `function onProposalApplied() { fm.load(); wb.reload() }`。
- 模板：在 `<STabs .../>` **之前**插 `<ProposalPanel :draft="fm.draft.value" @applied="onProposalApplied" />`（即 `<div v-if="wb.currentVariantId != null" class="dt">` 内、STabs 上方）。

- [ ] **Step 6: 全量 + 提交**

Run: `npm run test`（≤32 基线不新增）
```bash
git add apps/webui/frontend/src/components/workbench/ProposalPanel.vue apps/webui/frontend/src/components/workbench/ProposalPanel.test.js apps/webui/frontend/src/components/workbench/DetailTabs.vue
git commit -m "feat(detail): ProposalPanel(AI草案审阅:标题/简介/标签/AI属性/缺失必填+应用/放弃/重生成)接入 DetailTabs 顶部"
```

---

### Task 3: 产品文档同步 + 收尾

**Files:**
- Modify: `docs/product/workbench.md`

- [ ] **Step 1: 更新文档**

`workbench.md`：详情 tab 区补「ProposalPanel（AI 草案审阅，DetailTabs 顶部条件面板）」一节：交互(空态生成/审阅态编辑标题简介标签+AI属性+缺失必填/应用合并·放弃·重生成)、数据(draft.ai_proposal + aiProposalPatch/Apply + aiGenerate/aiCopy)、规则(与 F1d-2 直填/F1d-3b 图集计划独立；与流水线 copy 自动 apply 互补=单变体精细审阅；标签 attr 23171；apply 后 fm.load+wb.reload；unmapped 提示)。变更历史加一行。

- [ ] **Step 2: 提交**

```bash
git add docs/product/workbench.md
git commit -m "docs(product): workbench 补 AI 提案审阅(F1d-4)交互/数据/规则"
```

---

## Controller 复核（每任务后 + 全部后）
- 每任务：读 diff、跑该任务测试、TDD 红→绿。
- 全部后：`npm run test`(≤32) + `npm run build`；起本地后端**端到端验**：种带 ai_proposal 的草稿(直接 set_ai_proposal 灌一份 {fields, attributes(ai+missing)})，curl getDraft 确认返 ai_proposal；aiProposalPatch(edit_field/edit_attr/discard) 改对；aiProposalApply 合并进正式字段+清草案+返 unmapped。前端浏览器看 ProposalPanel 空态/审阅态渲染 + 应用刷新。验完清理环境。
- **F1 收口(下一步，先确认再做)**：F1d-4 完成即可删 `DraftDetail.vue`/`Collect.vue` god-component、退役 `/drafts-classic`。涉及删大文件，单独确认后执行。
