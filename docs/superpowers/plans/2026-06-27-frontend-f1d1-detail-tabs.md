# 前端重建 F1d-1:详情 tab 壳 + 简单 tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。Steps 用 checkbox。

**Goal:** 中栏 PipelinePanel 下加"当前变体详情编辑区":tab 容器 + useDraftForm(拉草稿/保存)+ 4 个简单 tab(商品信息/采购/视频/富文本),特征/图片 tab 占位。

**Architecture:** `useDraftForm(draftIdRef)` 从 god-component 抽 load/collectPatch/save(`api.getDraft`→form→`api.patchDraft`);`DetailTabs.vue` 读 `workbench.currentVariantId` 渲 STabs + 简单 tab;复用现有 CategorySelect/BrandSelect/MediaManager/RichContentPreview/AiVideoDialog。不动 legacy DraftDetail/Collect。

**Tech Stack:** Vue3 `<script setup>`、Pinia、Element Plus、Vitest。

**全局约定:** 工作目录 `E:\personal\ozon-helper\apps\webui\frontend`;分支 `feat/auto-listing-ai-pipeline`;`npm`;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。**gating**:前端新测试过 + `npm test` 失败数 ≤ **32**(历史基线,不新增)+ `npm run build` 成功。视觉对照原型 `变体工作台.dc.html` 中栏详情区。复用组件在 `src/components/`;设计系统 `src/ui`;参考 spec `docs/superpowers/specs/2026-06-27-frontend-f1d1-detail-tabs-design.md`;源逻辑 `src/components/DraftDetail.vue`(`initFromDraft` 1295、`collectPatch` 1353)。

**简单字段(PATCH 部分更新,特征/图片字段不碰)**:`ozon_title/description/category_id/type_id/brand_id/brand_name/stock/weight_g/length_mm/width_mm/height_mm/price/old_price/cost_cny/purchase_url/purchase_note/supplier/offer_id`。

---

## File Structure
| 文件 | 职责 |
|---|---|
| `src/api.js` | 加 `getDraft(id)` |
| `src/composables/useDraftForm.js` | 拉草稿→form / collectPatch / save |
| `src/components/workbench/DetailTabs.vue` | tab 容器(STabs + 当前变体 + 渲 tab) |
| `src/components/workbench/tabs/InfoTab.vue` | 商品信息表单 |
| `src/components/workbench/tabs/PurchaseTab.vue` | 采购表单 |
| `src/components/workbench/tabs/VideoTab.vue` | 视频(复用 MediaManager) |
| `src/components/workbench/tabs/RichTextTab.vue` | 富文本(复用 RichContentPreview) |
| `src/views/Workbench.vue` | 中栏接 DetailTabs |

---

## Task 1:api.getDraft + useDraftForm

**Files:**
- Modify: `src/api.js`(加 getDraft)
- Create: `src/composables/useDraftForm.js`、`src/composables/draftform.test.js`

- [ ] **Step 1: 确认 patchDraft 是部分更新** —— 读 `apps/webui/src/webui/app_service.py` 的 `update_draft`(或 store)看 PATCH 是否只更新传入的键(部分 merge)。**若是部分更新**:collectPatch 只发简单字段即可(下面如此)。**若是全量替换**(罕见):collectPatch 还需带回 `attributes`/`images`/`source_raw`(从 loaded draft 原样),否则会清空——那就在 collectPatch 加 `attributes: draft.value.attributes, images: draft.value.images`。先确认再定。

- [ ] **Step 2: api.js 加 getDraft**(`/api/drafts/{id}` 端点已存在):
```js
  getDraft: (id) => req('GET', `/api/drafts/${id}`),
```
(加在 `listDrafts` 附近。)

- [ ] **Step 3: 写测试(先红)** `src/composables/draftform.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  getDraft: vi.fn().mockResolvedValue({ id: 7, ozon_title: '杯', price: 38, stock: 5,
    category_id: '1', type_id: '2', source_raw: {}, attributes: [] }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7, ozon_title: '新杯' } }),
} }))
import { api } from '../api.js'
import { useDraftForm } from './useDraftForm.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('useDraftForm', () => {
  it('draftId 变 → 拉草稿填 form', async () => {
    const id = ref(7)
    const fm = useDraftForm(id)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(api.getDraft).toHaveBeenCalledWith(7)
    expect(fm.form.ozon_title).toBe('杯')
    expect(fm.form.price).toBe(38)
  })
  it('save 调 patchDraft(collectPatch)', async () => {
    const id = ref(7); const fm = useDraftForm(id)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    fm.form.ozon_title = '新杯'
    await fm.save()
    expect(api.patchDraft).toHaveBeenCalled()
    const patch = api.patchDraft.mock.calls[0][1]
    expect(patch.ozon_title).toBe('新杯')
    expect(patch.category_id).toBe('1')
  })
})
```

- [ ] **Step 4: 跑确认红** `cd /e/personal/ozon-helper/apps/webui/frontend && npm test src/composables/draftform.test.js 2>&1 | tail -8` → FAIL。

- [ ] **Step 5: 实现 `src/composables/useDraftForm.js`**
```js
import { reactive, ref, watch } from 'vue'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'

function numOrNull(v) { return v === '' || v === null || v === undefined ? null : Number(v) }

export function useDraftForm(draftIdRef) {
  const store = useAppStore()
  const wb = useWorkbenchStore()
  const draft = ref(null)
  const loading = ref(false)
  const form = reactive({})

  function initFromDraft(d) {
    const s = d || {}
    Object.assign(form, {
      ozon_title: s.ozon_title ?? '', description: s.description ?? '',
      category_id: s.category_id ?? '', type_id: s.type_id ?? '',
      brand_id: s.brand_id ?? null, brand_name: s.brand_name ?? '',
      stock: s.stock ?? 0, price: s.price ?? '', old_price: s.old_price ?? '',
      cost_cny: s.cost_cny ?? '', weight_g: s.weight_g ?? 0,
      length_mm: s.length_mm ?? 0, width_mm: s.width_mm ?? 0, height_mm: s.height_mm ?? 0,
      purchase_url: s.purchase_url ?? '', purchase_note: s.purchase_note ?? '',
      supplier: s.supplier ?? '', offer_id: s.offer_id ?? '',
    })
  }
  function collectPatch() {
    const price = form.price
    return {
      ozon_title: form.ozon_title, description: form.description,
      category_id: form.category_id, type_id: form.type_id,
      brand_id: form.brand_id ?? null, brand_name: form.brand_name,
      stock: Number(form.stock || 0),
      weight_g: numOrNull(form.weight_g), length_mm: numOrNull(form.length_mm),
      width_mm: numOrNull(form.width_mm), height_mm: numOrNull(form.height_mm),
      price, old_price: (String(form.old_price || '').trim()) || price,
      cost_cny: numOrNull(form.cost_cny),
      purchase_url: form.purchase_url, purchase_note: form.purchase_note,
      supplier: form.supplier, offer_id: form.offer_id,
    }
  }
  async function load() {
    const id = draftIdRef.value
    if (id == null) { draft.value = null; return }
    loading.value = true
    try { const d = await api.getDraft(id); draft.value = d; initFromDraft(d) }
    finally { loading.value = false }
  }
  async function save() {
    const id = draftIdRef.value; if (id == null) return
    const r = await api.patchDraft(id, collectPatch())
    if (r && r.draft) { draft.value = r.draft; store.upsertDraft(r.draft); wb.reload() }
    return r
  }
  watch(draftIdRef, () => load(), { immediate: true })
  return { draft, form, loading, load, save, collectPatch }
}
```
> 注:Step1 若发现 patchDraft 是全量替换,在 collectPatch 末尾加 `attributes: (draft.value && draft.value.attributes) || [], images: (draft.value && draft.value.images) || [], source_raw: (draft.value && draft.value.source_raw) || {}`(保 特征/图片 不被清)。

- [ ] **Step 6: 跑测试 + 提交**
```bash
npm test src/composables/draftform.test.js 2>&1 | tail -5    # PASS
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/api.js apps/webui/frontend/src/composables/useDraftForm.js apps/webui/frontend/src/composables/draftform.test.js
git commit -m "feat(detail): useDraftForm(api.getDraft→form/collectPatch/save)+ api.getDraft

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2:DetailTabs 容器 + 接 Workbench

**Files:**
- Create: `src/components/workbench/DetailTabs.vue`、`.../detailtabs.test.js`
- Modify: `src/views/Workbench.vue`
- (依赖 Task3/4 的 tab 组件——本任务先用占位 div 渲 4 个简单 tab,Task3/4 替换为真组件)

- [ ] **Step 1: 写测试(先红)** `detailtabs.test.js`:mock pinia + `useDraftForm`(或直接 mock api.getDraft),wb.currentVariantId=7,mount DetailTabs,断言渲染 6 个 tab 头(商品信息/特征/图片/视频/富文本/采购信息),点"特征"tab → 显占位文本。

- [ ] **Step 2: 跑确认红** → FAIL。

- [ ] **Step 3: 实现 `DetailTabs.vue`**
```vue
<script setup>
import { ref, computed } from 'vue'
import { useWorkbenchStore } from '../../stores/workbench.js'
import { useDraftForm } from '../../composables/useDraftForm.js'
import { STabs } from '../../ui/index.js'
import InfoTab from './tabs/InfoTab.vue'
import PurchaseTab from './tabs/PurchaseTab.vue'
import VideoTab from './tabs/VideoTab.vue'
import RichTextTab from './tabs/RichTextTab.vue'

const wb = useWorkbenchStore()
const fm = useDraftForm(computed(() => wb.currentVariantId))
const active = ref('info')
const TABS = [
  { key: 'info', label: '商品信息' }, { key: 'attrs', label: '特征' },
  { key: 'images', label: '图片' }, { key: 'video', label: '视频' },
  { key: 'richtext', label: '富文本' }, { key: 'purchase', label: '采购信息' },
]
</script>
<template>
  <div v-if="wb.currentVariantId != null" class="dt">
    <STabs :items="TABS" :active-key="active" @change="(k) => active = k" />
    <div class="dt__body">
      <InfoTab v-if="active === 'info'" :form="fm.form" :draft="fm.draft.value" @save="fm.save" />
      <PurchaseTab v-else-if="active === 'purchase'" :form="fm.form" @save="fm.save" />
      <VideoTab v-else-if="active === 'video'" :draft="fm.draft.value" @save="fm.save" />
      <RichTextTab v-else-if="active === 'richtext'" :draft="fm.draft.value" />
      <div v-else-if="active === 'attrs'" class="dt__ph">特征 tab 将在 F1d-2 实现</div>
      <div v-else-if="active === 'images'" class="dt__ph">图片 tab 将在 F1d-3 实现(接素材/图集)</div>
    </div>
  </div>
</template>
<style scoped>
.dt{margin-top:var(--sp-5);border-top:1px solid var(--c-border);padding-top:var(--sp-4)}
.dt__body{margin-top:var(--sp-4)}
.dt__ph{color:var(--c-text-3);font-size:var(--fs-sm);padding:var(--sp-5)}
</style>
```
> Task3/4 没建 tab 组件前,这里 import 会报错——**本任务连同 Task3/4 的最简骨架先建**(InfoTab/PurchaseTab/VideoTab/RichTextTab 各先建一个 `<template><div>xx</div></template>` 占位,Task3/4 填实),保证 DetailTabs 能编译。或调整任务顺序:先 Task3/4 建组件再 Task2。**实现者按此:本任务先建 4 个 tab 的最简占位文件,Task3/4 填充内容。**

- [ ] **Step 4: 接 Workbench.vue** —— 中栏 `v-else` 分支,PipelinePanel **下面**加 `<DetailTabs />`(import 之)。

- [ ] **Step 5: 跑测试 + 构建 + 提交**
```bash
npm test src/components/workbench/detailtabs.test.js 2>&1 | tail -6
npm run build 2>&1 | tail -3
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/DetailTabs.vue apps/webui/frontend/src/components/workbench/tabs apps/webui/frontend/src/components/workbench/detailtabs.test.js apps/webui/frontend/src/views/Workbench.vue
git commit -m "feat(detail): DetailTabs 容器(6 tab + 当前变体)接入工作台中栏 + tab 占位骨架

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3:InfoTab + PurchaseTab(表单)

**Files:**
- Modify: `src/components/workbench/tabs/InfoTab.vue`、`PurchaseTab.vue`(占位 → 完整)
- Test: `src/components/workbench/tabs/forms.test.js`

- [ ] **Step 1: 写测试(先红)** `forms.test.js`:mount InfoTab(props.form={ozon_title:'杯',price:38,stock:5,...}),断言渲染标题输入(值'杯')、改 stock 后点"保存"emit save。PurchaseTab 同理(purchase_url/supplier/cost_cny)。(mount 用 ElementPlus plugin + stub CategorySelect/BrandSelect。)

- [ ] **Step 2: 跑确认红** → FAIL。

- [ ] **Step 3: 实现 InfoTab.vue**
- props `{ form: Object, draft: Object }`,emit `['save']`。
- `import { ElInput, ElInputNumber } from 'element-plus'`、`CategorySelect`、`BrandSelect`、`SButton`。
- `categoryModel` computed(get/set form.category_id+type_id,喂 CategorySelect v-model——看 `DraftDetail.vue` 的 categoryModel 怎么定义,搬一份)。
- 字段:Ozon 标题(ElInput v-model form.ozon_title)、类目(`<CategorySelect v-model="categoryModel">`)、品牌(`<BrandSelect v-model:brand-id="form.brand_id" v-model:brand-name="form.brand_name">`——看 BrandSelect 的 props/事件适配)、库存/售价/划线价/克重/尺寸长宽高(ElInputNumber)、简介(ElInput type=textarea v-model form.description)。
- 底部 `<SButton variant="primary" @click="emit('save')">保存</SButton>`。
- tokens 样式。
> CategorySelect/BrandSelect 的 v-model 契约:读 `src/components/CategorySelect.vue`/`BrandSelect.vue` 的 defineProps/defineEmits 适配(别猜)。

- [ ] **Step 4: 实现 PurchaseTab.vue**:props.form + emit save;字段采购链接/供应商/成本价(¥,ElInputNumber)+ 保存按钮。

- [ ] **Step 5: 跑测试 + 构建 + 提交**
```bash
npm test src/components/workbench/tabs/forms.test.js 2>&1 | tail -6 && npm run build 2>&1 | tail -3
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/tabs/InfoTab.vue apps/webui/frontend/src/components/workbench/tabs/PurchaseTab.vue apps/webui/frontend/src/components/workbench/tabs/forms.test.js
git commit -m "feat(detail): InfoTab(标题/类目/品牌/价/尺寸)+ PurchaseTab(采购)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4:VideoTab + RichTextTab(复用媒体/富文本)

**Files:**
- Modify: `src/components/workbench/tabs/VideoTab.vue`、`RichTextTab.vue`(占位 → 完整)
- Test: `src/components/workbench/tabs/media.test.js`

- [ ] **Step 1: 读** `src/components/MediaManager.vue`、`RichContentPreview.vue`、`AiVideoDialog.vue` 的 props/事件;`DraftDetail.vue` 里 video tab(681)/richtext tab(708)怎么用它们(`onVideoChange`/`openAiVideo`/`richContentJson`)。

- [ ] **Step 2: 写测试(先红)** `media.test.js`:mount VideoTab(stub MediaManager/AiVideoDialog),断言渲染;RichTextTab(draft 带 source_raw.rich_content_json)断言渲染 RichContentPreview 或"生成富文本"。

- [ ] **Step 3: 实现 VideoTab.vue**:props `{ draft }` + emit save;`<MediaManager>`(video 模式,搬 DraftDetail 的用法 + onVideoChange→`api.patchDraft(id,{video_url})`)+ `<AiVideoDialog>` 触发按钮。

- [ ] **Step 4: 实现 RichTextTab.vue**:props `{ draft }`;`richContentJson` = `draft?.source_raw?.rich_content_json`;有则 `<RichContentPreview :rich-json>`,无则提示;"生成富文本"按钮 `api.makeRichContent(draft.id,{})` → 刷新。

- [ ] **Step 5: 跑测试 + 构建 + 提交**
```bash
npm test src/components/workbench/tabs/media.test.js 2>&1 | tail -6 && npm run build 2>&1 | tail -3
cd /e/personal/ozon-helper
git add apps/webui/frontend/src/components/workbench/tabs/VideoTab.vue apps/webui/frontend/src/components/workbench/tabs/RichTextTab.vue apps/webui/frontend/src/components/workbench/tabs/media.test.js
git commit -m "feat(detail): VideoTab(复用MediaManager/AiVideoDialog)+ RichTextTab(复用RichContentPreview)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5:收尾 + 视觉验收

- [ ] **Step 1: 全量** `npm test`(失败数 ≤ 32)+ `npm run build`。
- [ ] **Step 2: controller 视觉验收**:本地后端(灌变体含 title/category/price)+ 临时代理 + dev + 登录 → 选草稿 → 中栏 PipelinePanel 下出现详情 tab;切 商品信息/采购/视频/富文本 渲染正常;改字段点保存 → PATCH 成功(变体步骤进度可能随之变);特征/图片 tab 显占位。验完还原 vite.config + 清理。
- [ ] **Step 3: 有收尾改动则提交**。

---

## Self-Review
- **Spec 覆盖**:① api.getDraft+useDraftForm→T1;② DetailTabs+接Workbench→T2;③ InfoTab/PurchaseTab→T3;④ VideoTab/RichTextTab→T4;⑤ 特征/图片占位→T2;⑥ 复用子组件→T3/T4。全覆盖。
- **占位符**:T1 Step1(patchDraft 部分更新确认)+ T3(CategorySelect/BrandSelect v-model 契约读源)+ T4(MediaManager 用法读源)是明确的"读现有代码适配"指令,非空泛;给了源位置。
- **契约一致**:`useDraftForm(draftIdRef)->{draft(ref),form(reactive),loading,load,save,collectPatch}`;DetailTabs 传 `:form="fm.form" :draft="fm.draft.value"`;collectPatch 字段=简单子集(前后一致)。
- **风险**:① patchDraft 若全量替换→collectPatch 要带回 attributes/images(T1 Step1+注已覆盖);② CategorySelect/BrandSelect/MediaManager v-model 契约要读源适配(T3/T4 已要求);③ DetailTabs import tab 组件→Task2 连带建占位骨架避免编译错(T2 Step3 注已说明)。
