# 前端重建 F1a:变体工作台地基 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。Steps 用 checkbox(`- [ ]`)。

**Goal:** 建变体工作台地基——工作台状态脊柱(Pinia workbench 模块)+ 3 栏外壳 + 草稿列表(替 DraftTable)+ 变体卡面板,旧编辑器挪 legacy 路由兜底。

**Architecture:** 状态脊柱 `stores/workbench.js`(选草稿→变体组→多选→当前变体)。新 `views/Workbench.vue`(3 栏,挂 `/`)组合 `DraftListPane`(左)+ 中栏占位 + `VariantCardsPane`(右)。旧 `Collect.vue` 移 `/drafts-classic`。用 F0 设计系统(`src/ui`),接现有 Pinia `app.js` + `api.variantGroup`,零后端改动。

**Tech Stack:** Vue 3.5 `<script setup>`、Pinia、vue-router、Element Plus(重控件)、F0 `src/ui` 组件、Vitest + @vue/test-utils。

**全局约定:** 工作目录 `E:\personal\ozon-helper\apps\webui\frontend`;分支 `feat/auto-listing-ai-pipeline`;`npm`;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。**测试 gating**:前端有 **32 个历史失败**(`tests/*.spec.js`,与本块无关)——新增 `src/` 测试全过 + 全量 `npm test` 失败数 ≤ 32(不新增)+ `npm run build` 成功。视觉对照:本地 `python -m http.server` 渲染原型 `变体工作台.dc.html`。设计系统组件从 `src/ui/index.js` 导入,样式只用 tokens 变量。参考:spec `docs/superpowers/specs/2026-06-27-frontend-f1a-workbench-foundation-design.md`;现有 `src/components/DraftTable.vue`(列表逻辑来源)、`src/views/Collect.vue`(批量/发布逻辑来源)、`src/stores/app.js`。

---

## File Structure
| 文件 | 职责 |
|---|---|
| `src/stores/workbench.js` | 工作台状态脊柱(变体组+多选+当前变体) |
| `src/views/Workbench.vue` | 3 栏外壳(挂 `/`) |
| `src/components/workbench/DraftListPane.vue` | 左栏草稿列表(替 DraftTable) |
| `src/components/workbench/VariantCardsPane.vue` | 右栏变体卡 |
| `src/composables/useDraftBatchOps.js` | 批量/发布逻辑(从 Collect 抽出复用) |
| `src/router/index.js` | `/`→Workbench、`/drafts-classic`→Collect |

---

## Task 1:工作台状态脊柱 `stores/workbench.js`

**Files:**
- Create: `src/stores/workbench.js`、`src/stores/workbench.test.js`

- [ ] **Step 1: 写测试(先红)** `src/stores/workbench.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: { variantGroup: vi.fn() } }))
import { api } from '../api.js'
import { useWorkbenchStore } from './workbench.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('workbench store', () => {
  it('loadForDraft 填变体 + 默认全选 + 当前变体', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2,
      variants: [{ id: 1, spec: '雾灰·350ml', price: 1190, status: 'ready', image: 'a.jpg', current: true },
                 { id: 2, spec: '雾灰·500ml', price: 1290, status: 'ready', image: 'b.jpg', current: false }] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.groupKey).toBe('G')
    expect(wb.variants.length).toBe(2)
    expect(wb.currentVariantId).toBe(1)
    expect([...wb.selectedVariantIds].sort()).toEqual([1, 2])  // 默认全选
    expect(wb.currentVariant.spec).toBe('雾灰·350ml')
  })
  it('单草稿无组退化', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: '', count: 0, variants: [] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(5)
    expect(wb.groupKey).toBe('')
    expect(wb.currentVariantId).toBe(5)
  })
  it('toggle/selectAll/clear/invert', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.clearSelection(); expect(wb.selectedVariantIds.size).toBe(0)
    wb.toggleVariant(2); expect([...wb.selectedVariantIds]).toEqual([2])
    wb.invertSelection(); expect([...wb.selectedVariantIds].sort()).toEqual([1])
    wb.selectAll(); expect(wb.selectedVariantIds.size).toBe(2)
  })
})
```

- [ ] **Step 2: 跑确认红** `npm test src/stores/workbench.test.js 2>&1 | tail -8` → FAIL。

- [ ] **Step 3: 实现 `src/stores/workbench.js`**
```js
import { defineStore } from 'pinia'
import { api } from '../api.js'

export const useWorkbenchStore = defineStore('workbench', {
  state: () => ({
    groupKey: '', variants: [], selectedVariantIds: new Set(),
    currentVariantId: null, loading: false,
  }),
  getters: {
    currentVariant: (s) => s.variants.find(v => v.id === s.currentVariantId) || null,
    selectedVariants: (s) => s.variants.filter(v => s.selectedVariantIds.has(v.id)),
    variantCount: (s) => s.variants.length,
    allSelected: (s) => s.variants.length > 0 && s.variants.every(v => s.selectedVariantIds.has(v.id)),
  },
  actions: {
    async loadForDraft(draftId) {
      if (draftId == null) { this.reset(); return }
      this.loading = true
      try {
        const r = await api.variantGroup(draftId)
        const vs = r.variants || []
        this.groupKey = r.group || ''
        this.variants = vs.length ? vs : [{ id: draftId, spec: '', price: null, status: '', image: '', current: true }]
        this.currentVariantId = draftId
        this.selectedVariantIds = new Set(this.variants.map(v => v.id))  // 默认全选
      } finally { this.loading = false }
    },
    reset() { this.groupKey = ''; this.variants = []; this.selectedVariantIds = new Set(); this.currentVariantId = null },
    setCurrentVariant(id) { this.currentVariantId = id },
    toggleVariant(id) {
      const s = new Set(this.selectedVariantIds)
      s.has(id) ? s.delete(id) : s.add(id); this.selectedVariantIds = s
    },
    selectAll() { this.selectedVariantIds = new Set(this.variants.map(v => v.id)) },
    clearSelection() { this.selectedVariantIds = new Set() },
    invertSelection() {
      this.selectedVariantIds = new Set(this.variants.filter(v => !this.selectedVariantIds.has(v.id)).map(v => v.id))
    },
    async reload() { if (this.currentVariantId != null) await this.loadForDraft(this.currentVariantId) },
  },
})
```

- [ ] **Step 4: 跑确认绿** `npm test src/stores/workbench.test.js 2>&1 | tail -6` → PASS。
- [ ] **Step 5: 提交**
```bash
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/stores/workbench.js apps/webui/frontend/src/stores/workbench.test.js
git commit -m "feat(fe): F1a 工作台状态脊柱 stores/workbench.js(变体组+多选+当前变体)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2:路由切换 + Workbench 外壳骨架

**Files:**
- Modify: `src/router/index.js`(`/`→Workbench、新增 `/drafts-classic`→Collect)
- Create: `src/views/Workbench.vue`(3 栏骨架,左右先占位)
- Test: `src/views/workbench.test.js`

- [ ] **Step 1: 写测试(先红)** `src/views/workbench.test.js`:
```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workbench from './Workbench.vue'

describe('Workbench 外壳', () => {
  it('渲染三栏容器', () => {
    setActivePinia(createPinia())
    const w = mount(Workbench, { global: { stubs: { DraftListPane: true, VariantCardsPane: true } } })
    expect(w.find('.wb-grid').exists()).toBe(true)
    expect(w.find('.wb-center').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 跑确认红** → FAIL。

- [ ] **Step 3: `src/views/Workbench.vue`(骨架,左右先放占位 div,Task3/4 替换为真组件)**
```vue
<script setup>
import { watch } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'

const store = useAppStore()
const wb = useWorkbenchStore()
watch(() => store.selectedId, (id) => wb.loadForDraft(id), { immediate: true })
</script>
<template>
  <div class="wb-grid">
    <aside class="wb-left"><!-- Task3: DraftListPane --></aside>
    <main class="wb-center">
      <div v-if="!store.selectedDraft" class="wb-empty">
        <div class="wb-empty__i">📦</div>
        <div class="wb-empty__t">选中左侧草稿后在此进入 AI 工作台</div>
      </div>
      <div v-else class="wb-center-placeholder">中栏(AI 工作台 + 详情)将在 F1c/F1d 实现</div>
    </main>
    <aside class="wb-right"><!-- Task4: VariantCardsPane --></aside>
  </div>
</template>
<style scoped>
.wb-grid{display:grid;grid-template-columns:360px 1fr 360px;gap:var(--sp-4);height:calc(100vh - 56px - var(--sp-5)*2)}
.wb-left,.wb-right{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden;display:flex;flex-direction:column}
.wb-center{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:auto;padding:var(--sp-5)}
.wb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--c-text-3)}
.wb-empty__i{font-size:40px;margin-bottom:12px;opacity:.7}
.wb-center-placeholder{color:var(--c-text-3);font-size:var(--fs-sm)}
</style>
```

- [ ] **Step 4: 路由改 `src/router/index.js`** —— `/` 的 component 从 Collect 改 Workbench,加 `/drafts-classic`。把 children 里 `{ path: '', name: 'drafts', component: () => import('../views/Collect.vue') }` 改为:
```js
    { path: '', name: 'drafts', component: () => import('../views/Workbench.vue') },
    { path: 'drafts-classic', name: 'drafts-classic', component: () => import('../views/Collect.vue') },
```

- [ ] **Step 5: 跑测试 + 构建** `npm test src/views/workbench.test.js 2>&1 | tail -6` → PASS。`npm run build 2>&1 | tail -3` → 成功。`npm test 2>&1 | tail -3` → 失败数 ≤ 32。
- [ ] **Step 6: 提交**
```bash
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/views/Workbench.vue apps/webui/frontend/src/views/workbench.test.js apps/webui/frontend/src/router/index.js
git commit -m "feat(fe): F1a 工作台 3 栏外壳 + 路由(/ → Workbench,旧编辑器挪 /drafts-classic)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3:左栏 `DraftListPane.vue`(替 DraftTable,设计系统重绘)

**Files:**
- Create: `src/components/workbench/DraftListPane.vue`、`src/components/workbench/draftlist.test.js`
- Modify: `src/views/Workbench.vue`(挂载 DraftListPane)

- [ ] **Step 1: 读** `src/components/DraftTable.vue` —— 把它的逻辑搬来(本任务是它的设计系统重绘版):`statusLabel`(invalid→待完善/ready→待发布/failed→发布失败/published→已发布)、`tagType`、`sourceLabel`/`sourceTagType`(source_platform→1688/Ozon/WB)、`firstImage`(local_images[0]||images[0])、`visibleDrafts`(query 过滤)、多选(checked/toggleAll/isChecked)、批量工具条(stock/warehouse popover + 发布 + 删除)、分页。

- [ ] **Step 2: 写测试(先红)** `src/components/workbench/draftlist.test.js`:
```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DraftListPane from './DraftListPane.vue'

const drafts = [
  { id: 1, source_title: '保温杯', source_platform: '1688', price: 38, status: 'ready', images: ['a.jpg'] },
  { id: 2, ozon_title: 'Кружка', source_platform: 'ozon', price: 99, status: 'published', images: [] },
]
const counts = { all: 2, invalid: 0, ready: 1, failed: 0, published: 1 }
function mountPane(props = {}) {
  return mount(DraftListPane, {
    props: { drafts, counts, filter: 'all', selectedId: null, warehouses: [], total: 2, page: 1, pageSize: 20, ...props },
    global: { plugins: [ElementPlus] },
  })
}
describe('DraftListPane', () => {
  it('渲染草稿卡 + 状态/来源标签', () => {
    const w = mountPane()
    expect(w.text()).toContain('保温杯'); expect(w.text()).toContain('Кружка')
    expect(w.text()).toContain('待发布'); expect(w.text()).toContain('已发布')
    expect(w.text()).toContain('1688')
  })
  it('点卡 emit select', async () => {
    const w = mountPane()
    await w.find('.dcard').trigger('click')
    expect(w.emitted('select')[0]).toEqual([1])
  })
  it('切 tab emit update:filter', async () => {
    const w = mountPane()
    // STabs 的"已发布"项
    const tab = w.findAll('.s-tabs__item').find(t => t.text().includes('已发布'))
    await tab.trigger('click')
    expect(w.emitted('update:filter')[0]).toEqual(['published'])
  })
})
```

- [ ] **Step 3: 跑确认红** → FAIL。

- [ ] **Step 4: 实现 `DraftListPane.vue`** —— props/emits **与 DraftTable 完全一致**(`drafts/counts/filter/selectedId/warehouses/total/page/pageSize` props;`select/delete/update:filter/batch-update/batch-publish/page-change/size-change/refresh` emits),逻辑搬 DraftTable(Step1 列的那些函数)。**UI 用设计系统重绘**(对照原型 `变体工作台.dc.html` 左栏):
  - 头:"商品草稿" + count(SBadge primary)+ 刷新(SButton ghost sm)。
  - 状态筛选用 **STabs**(`items` = `[{key:'all',label:'全部',count:c.all},{key:'invalid',label:'待完善',count:c.invalid},{key:'ready',label:'待发布',count:c.ready},{key:'failed',label:'失败',count:c.failed},{key:'published',label:'已发布',count:c.published}]`,`activeKey=filter`,`@change` → `emit('update:filter', key)`)。
  - 过滤框(ElInput)+ 全选(ElCheckbox)。
  - 批量工具条(选中>0):已选 N + 批量设置(ElPopover:stock/warehouse,沿用 applyStock/applyWarehouse emit batch-update)+ 发布 SButton + 删除 SButton danger。
  - 草稿卡(`.dcard`,点 emit select,active 高亮 currentStore 紫):ElCheckbox 多选 + 缩略图 + 标题 + 来源 SBadge(`1688`→primary/`Ozon`→info)+ ID + 价(¥)+ 状态 SBadge(ready/published→success、failed→danger、invalid→warn)。
  - 分页(ElPagination + 每页选择,emit page-change/size-change)。
  - 样式只用 tokens(把 DraftTable 的 `--gp-*` 换成 `--c-*`)。

- [ ] **Step 5: Workbench.vue 挂载** —— import DraftListPane + useAppStore,左栏放:
```vue
<DraftListPane
  :drafts="store.filteredDrafts" :counts="store.counts" :filter="store.filter"
  :selected-id="store.selectedId" :warehouses="warehouses" :total="store.total"
  :page="store.page" :page-size="store.pageSize"
  @refresh="store.loadDrafts()" @update:filter="store.setFilter"
  @select="(id) => store.selectedId = id" @page-change="store.setPage" @size-change="store.setPageSize"
  @delete="onDelete" @batch-update="onBatchUpdate" @batch-publish="onBatchPublish" />
```
(`warehouses`/`onDelete`/`onBatchUpdate`/`onBatchPublish` 在 Task5 接 composable;本任务先放空实现 `const warehouses = ref([])` + 三个空 async 函数占位,Task5 替换。)

- [ ] **Step 6: 跑测试 + 构建 + 提交**
```bash
npm test src/components/workbench/draftlist.test.js 2>&1 | tail -6   # PASS
npm run build 2>&1 | tail -3                                          # 成功
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/DraftListPane.vue apps/webui/frontend/src/components/workbench/draftlist.test.js apps/webui/frontend/src/views/Workbench.vue
git commit -m "feat(fe): F1a 左栏 DraftListPane(替 DraftTable,设计系统重绘 + STabs/SBadge)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4:右栏 `VariantCardsPane.vue`

**Files:**
- Create: `src/components/workbench/VariantCardsPane.vue`、`src/components/workbench/variantcards.test.js`
- Modify: `src/views/Workbench.vue`(挂载 + 右栏)

- [ ] **Step 1: 写测试(先红)** `src/components/workbench/variantcards.test.js`:
```js
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import VariantCardsPane from './VariantCardsPane.vue'
import { useWorkbenchStore } from '../../stores/workbench.js'

function setup() {
  setActivePinia(createPinia())
  const wb = useWorkbenchStore()
  wb.variants = [{ id: 1, spec: '雾灰·350ml', price: 1190, status: 'ready', image: 'a.jpg' },
                 { id: 2, spec: '雾灰·500ml', price: 1290, status: 'ready', image: 'b.jpg' }]
  wb.selectedVariantIds = new Set([1, 2]); wb.currentVariantId = 1
  const w = mount(VariantCardsPane, { global: { plugins: [ElementPlus] } })
  return { w, wb }
}
describe('VariantCardsPane', () => {
  it('渲染变体卡 + 已选数', () => {
    const { w } = setup()
    expect(w.text()).toContain('雾灰·350ml'); expect(w.text()).toContain('1190')
    expect(w.text()).toContain('已选 2')
  })
  it('点卡设当前变体', async () => {
    const { w, wb } = setup()
    const cards = w.findAll('.vcard')
    await cards[1].trigger('click')
    expect(wb.currentVariantId).toBe(2)
  })
  it('清空选择', async () => {
    const { w, wb } = setup()
    const btn = w.findAll('button').find(b => b.text().includes('清空'))
    await btn.trigger('click')
    expect(wb.selectedVariantIds.size).toBe(0)
  })
})
```

- [ ] **Step 2: 跑确认红** → FAIL。

- [ ] **Step 3: 实现 `VariantCardsPane.vue`**(对照原型右栏)
  - `import { useWorkbenchStore }`、`storeToRefs`、`src/ui` 组件、`api`。
  - 头:"变体 {{ wb.variantCount }} 个 · 已选 {{ wb.selectedVariantIds.size }}" + "+ 新增"(SButton ghost,F1a 先 disabled 占位)。
  - 操作行:全选(`wb.selectAll`)/反选(`wb.invertSelection`)/清空(`wb.clearSelection`)SButton + 搜索框(ElInput,按 spec 本地过滤)。
  - 卡网格(`.vcard`,点 `wb.setCurrentVariant(v.id)`,`v.id===wb.currentVariantId` 高亮):多选 checkbox(`wb.selectedVariantIds.has(v.id)` → `wb.toggleVariant(v.id)`)+ 颜色芯片/spec(`v.spec`)+ 价(`v.price` ₽)+ 状态 SBadge(`v.status`)+ 缩略图(`v.image`)+ × 删除(`api.deleteDraft(v.id)` 二次确认 ElMessageBox → `wb.reload()`,若删的是 currentVariant 则 emit 通知父刷新列表)。
  - emit `variant-deleted`(父 Workbench 收到后 `store.loadDrafts()` 刷新左栏)。
  - 样式 tokens。

- [ ] **Step 4: Workbench.vue 右栏挂载** `<VariantCardsPane @variant-deleted="store.loadDrafts()" />`(import 之)。

- [ ] **Step 5: 跑测试 + 构建 + 提交**
```bash
npm test src/components/workbench/variantcards.test.js 2>&1 | tail -6   # PASS
npm run build 2>&1 | tail -3
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/VariantCardsPane.vue apps/webui/frontend/src/components/workbench/variantcards.test.js apps/webui/frontend/src/views/Workbench.vue
git commit -m "feat(fe): F1a 右栏 VariantCardsPane(变体卡多选驱动 workbench 状态)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5:批量/发布逻辑接线(composable)

**Files:**
- Create: `src/composables/useDraftBatchOps.js`
- Modify: `src/views/Workbench.vue`(用 composable 替占位的 warehouses/onDelete/onBatchUpdate/onBatchPublish + 顶部发布)
- Test: `src/composables/batchops.test.js`

- [ ] **Step 1: 读 `src/views/Collect.vue`** —— 把 `doBatchUpdate`/`doBatchPublish`/`doDelete`/`loadWarehouses`/`doPublish`(发布预览流)+ `confirmFn` 抽成 composable `useDraftBatchOps(store)`,逻辑**一字不变**地搬(它们已用 `api` + `store` + ElMessage/ElMessageBox)。

- [ ] **Step 2: 写测试(先红)** `src/composables/batchops.test.js`:用 mock api + pinia,测 `useDraftBatchOps` 暴露 `doBatchUpdate/doBatchPublish/doDelete/loadWarehouses/warehouses/confirmFn`,且 `doDelete` 在 confirmFn resolve 后调 `api.deleteDraft` + `store.removeDraft`。(参照 Collect 现有测试 `tests/collect*.spec.js` 若有,照搬 mock 模式。)

- [ ] **Step 3: 实现 composable** —— `export function useDraftBatchOps(store) { ... return { warehouses, confirmFn, loadWarehouses, doBatchUpdate, doBatchPublish, doDelete, doPublish, publishResult, selectedStore, storeOptions } }`,内容从 Collect.vue 搬。

- [ ] **Step 4: Workbench.vue 接线** —— `const ops = useDraftBatchOps(store)`,把 Task3 占位的 `warehouses/onBatchUpdate/onBatchPublish/onDelete` 换成 `ops.warehouses` / `ops.doBatchUpdate` / `ops.doBatchPublish` / `ops.doDelete`;`onMounted` 调 `ops.loadWarehouses()`;顶部加发布按钮(对当前 `store.selectedDraft` 调 `ops.doPublish`)。

- [ ] **Step 5: 跑测试 + 构建** `npm test src/composables/batchops.test.js 2>&1 | tail -6` → PASS。`npm run build` 成功。`npm test 2>&1 | tail -3` 失败数 ≤ 32。
- [ ] **Step 6: 提交**
```bash
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/composables/useDraftBatchOps.js apps/webui/frontend/src/composables/batchops.test.js apps/webui/frontend/src/views/Workbench.vue
git commit -m "feat(fe): F1a 批量/发布逻辑抽 composable + 接入工作台

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6:收尾验证 + 视觉验收

- [ ] **Step 1: 全量测试** `npm test 2>&1 | tail -5` → 新测试(workbench/draftlist/variantcards/batchops/workbench 外壳)全过,失败数 ≤ 32。
- [ ] **Step 2: 构建** `npm run build 2>&1 | tail -3` → 成功。
- [ ] **Step 3: 控制器视觉验收**(controller 执行):起本地后端(`OZON_WEBUI_DB=临时库 python -m uv run uvicorn webui.main:app --port 8586`)+ 临时改 `vite.config.js` proxy 指本地 + `npm run dev` + 浏览器登录 admin/admin → 确认:① `/` 渲新 3 栏工作台(左草稿列表 + 中占位 + 右变体卡);② 选草稿 → 右栏变体卡出现(变体组);③ STabs 切换/多选/分页工作;④ `/drafts-classic` 旧编辑器仍可用。验完**还原 vite.config**、清理后端/临时库。
- [ ] **Step 4: 有收尾改动则提交**。

---

## Self-Review
- **Spec 覆盖**:① 状态脊柱 workbench.js→T1;② 3 栏外壳 Workbench.vue→T2;③ 左栏 DraftListPane→T3;④ 右栏 VariantCardsPane→T4;⑤ legacy 路由→T2;⑥ 批量/发布(不丢功能)→T5;⑦ 测试→各任务+T6。全覆盖。
- **占位符**:T3/T4 的组件 markup 交实现者按"DraftTable 逻辑搬 + 原型对照 + 设计系统"实现——给了完整 props/emits 契约 + 要搬的具体函数 + 数据流,非空泛(前端视觉页按原型实现是正常粒度)。T3 Step5 的 warehouses/onXxx 占位明确标注 Task5 替换。
- **契约一致**:workbench store API(loadForDraft/currentVariant/selectedVariantIds Set/toggleVariant/selectAll/clearSelection/invertSelection/reload)T1 定义,T2/T4 复用;DraftListPane props/emits 与 DraftTable 一致(T3),Workbench 按此接(T3 Step5);VariantCardsPane 读 workbench store(T4)。
- **风险**:① DraftListPane 是 DraftTable 的重绘——搬逻辑时别漏 firstImage/sourceLabel/批量;② STabs `count` 字段已在 F0 STabs 支持(`it.count`);③ composable 抽取后 Collect.vue(legacy)仍用它自己的内联版即可(不强制改 legacy),避免动 legacy;④ 视觉验收方法见 F0 plan T6 同款。
