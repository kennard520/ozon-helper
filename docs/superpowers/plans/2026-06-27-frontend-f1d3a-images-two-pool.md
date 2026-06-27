# F1d-3a 图片 tab（两池图片管理）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。逐任务实现，checkbox 跟踪。

**Goal:** 工作台「图片」tab 第一期：接素材库/图集两池后端 —— 图集区（排序/移出/删除/上传）+ 素材库区（加入图集/删除）+ 来自变体借图。AI 出图拆到 F1d-3b。

**Architecture:** `api.js` 补 gallery 系列 + copyImagesTo；`useGallery` composable（派生两池 + mutation，单一真相=后端 draft，改后 onChange 重拉）；`ImageCard.vue`（纯展示）；`ImagesTab.vue`（三段，接 DetailTabs）。零后端改动。

**Tech Stack:** Vue 3.5 `<script setup>`、Element Plus、Pinia、Vitest + @vue/test-utils。命令在 `apps/webui/frontend/` 跑 `npm run test`。

---

### Task 1: api.js gallery 方法 + useGallery composable

**Files:**
- Modify: `apps/webui/frontend/src/api.js`
- Create: `apps/webui/frontend/src/composables/useGallery.js`
- Test: `apps/webui/frontend/src/composables/useGallery.test.js`

- [ ] **Step 1: api.js 加方法**

在 `apps/webui/frontend/src/api.js` 里，找到已有的 `discardCandidates:` 那一行之后（或 uploadMedia 附近），加这 5 个方法（与周围风格一致，用已有的 `req` 与模板串）：
```js
  galleryAdd: (id, imageIds) => req('POST', `/api/drafts/${id}/gallery/add`, { image_ids: imageIds }),
  galleryRemove: (id, imageIds) => req('POST', `/api/drafts/${id}/gallery/remove`, { image_ids: imageIds }),
  galleryReorder: (id, imageIds) => req('POST', `/api/drafts/${id}/gallery/reorder`, { image_ids: imageIds }),
  deleteImage: (id, imageId) => req('DELETE', `/api/drafts/${id}/images/${imageId}`),
  copyImagesTo: (id, imageUrls, targetDraftIds) => req('POST', `/api/drafts/${id}/copy-images-to`, { image_urls: imageUrls, target_draft_ids: targetDraftIds }),
```

- [ ] **Step 2: 写失败测试**

`apps/webui/frontend/src/composables/useGallery.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  galleryAdd: vi.fn().mockResolvedValue({ id: 7 }),
  galleryRemove: vi.fn().mockResolvedValue({ id: 7 }),
  galleryReorder: vi.fn().mockResolvedValue({ id: 7 }),
  deleteImage: vi.fn().mockResolvedValue({ id: 7 }),
  copyImagesTo: vi.fn().mockResolvedValue({ ok: true, added: { 8: 1 } }),
  uploadMedia: vi.fn().mockResolvedValue({ url: 'http://up/new.jpg' }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
  getDraft: vi.fn().mockResolvedValue({ draft: { id: 8, materials: [
    { id: 81, url: 'http://s/8a.jpg', type: '', source: 'collected', in_gallery: 0, position: 0 },
  ] } }),
} }))
import { api } from '../api.js'
import { useGallery } from './useGallery.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function mkDraft() {
  return ref({
    id: 7,
    images: ['http://g/1.jpg', 'http://g/2.jpg'],
    local_images: ['/media/1.jpg', '/media/2.jpg'],
    materials: [
      { id: 1, url: 'http://g/1.jpg', type: '白底', source: 'generated', in_gallery: 1, position: 0 },
      { id: 2, url: 'http://g/2.jpg', type: '场景', source: 'generated', in_gallery: 1, position: 1 },
      { id: 3, url: 'http://m/3.jpg', type: '', source: 'collected', in_gallery: 0, position: 2 },
      { id: 4, url: 'http://m/4.jpg', type: '', source: 'collected', in_gallery: 0, position: 3 },
    ],
  })
}

describe('useGallery', () => {
  it('派生两池：galleryItems(in_gallery 真,按 position) / materialItems(假)', () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    expect(g.galleryItems.value.map(i => i.id)).toEqual([1, 2])
    expect(g.materialItems.value.map(i => i.id)).toEqual([3, 4])
  })

  it('localUrl：图集 url 命中本地代理,素材回退原 url', () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    expect(g.localUrl('http://g/1.jpg')).toBe('/media/1.jpg')
    expect(g.localUrl('http://m/3.jpg')).toBe('http://m/3.jpg')
  })

  it('addToGallery 调 api + onChange', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.addToGallery([3])
    expect(api.galleryAdd).toHaveBeenCalledWith(7, [3])
    expect(onChange).toHaveBeenCalled()
  })

  it('removeImage 调 deleteImage + onChange', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.removeImage(2)
    expect(api.deleteImage).toHaveBeenCalledWith(7, 2)
    expect(onChange).toHaveBeenCalled()
  })

  it('moveUp 据 galleryItems 算新序调 reorder', async () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    await g.moveUp(2)   // [1,2] → 把 2 上移 → [2,1]
    expect(api.galleryReorder).toHaveBeenCalledWith(7, [2, 1])
  })

  it('copyFrom 调 copyImagesTo(源兄弟,urls,[当前])', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.copyFrom(8, ['http://s/8a.jpg'])
    expect(api.copyImagesTo).toHaveBeenCalledWith(8, ['http://s/8a.jpg'], [7])
    expect(onChange).toHaveBeenCalled()
  })

  it('upload：uploadMedia→patchDraft 把新图并进图集', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.upload({ name: 'x.jpg' })
    expect(api.uploadMedia).toHaveBeenCalled()
    const patch = api.patchDraft.mock.calls[0][1]
    expect(patch.images).toEqual(['http://g/1.jpg', 'http://g/2.jpg', 'http://up/new.jpg'])
    expect(onChange).toHaveBeenCalled()
  })

  it('fetchSiblingMaterials 解包 getDraft 的 {draft}', async () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    const mats = await g.fetchSiblingMaterials(8)
    expect(api.getDraft).toHaveBeenCalledWith(8)
    expect(mats.map(m => m.id)).toEqual([81])
  })
})
```

- [ ] **Step 3: 跑测试确认失败**

Run: `npm run test -- useGallery`
Expected: FAIL（useGallery.js 不存在）

- [ ] **Step 4: 实现**

`apps/webui/frontend/src/composables/useGallery.js`:
```js
import { computed } from 'vue'
import { api } from '../api.js'

export function useGallery(draftRef, { onChange } = {}) {
  const fire = () => { if (typeof onChange === 'function') return onChange() }

  const materials = computed(() => {
    const d = draftRef.value || {}
    return Array.isArray(d.materials) ? d.materials : []
  })
  const galleryItems = computed(() =>
    materials.value.filter((m) => !!m.in_gallery)
      .slice().sort((a, b) => (a.position || 0) - (b.position || 0)))
  const materialItems = computed(() => materials.value.filter((m) => !m.in_gallery))

  // 图集本地代理：zip draft.images ↔ draft.local_images（同 legacy），素材回退原 url
  const localMap = computed(() => {
    const d = draftRef.value || {}
    const imgs = Array.isArray(d.images) ? d.images : []
    const loc = Array.isArray(d.local_images) ? d.local_images : []
    const out = {}
    imgs.forEach((u, i) => { if (u && loc[i]) out[u] = loc[i] })
    return out
  })
  function localUrl(url) { return localMap.value[url] || url }

  function did() { const d = draftRef.value || {}; return d.id }

  async function addToGallery(ids) { await api.galleryAdd(did(), ids); return fire() }
  async function removeFromGallery(ids) { await api.galleryRemove(did(), ids); return fire() }
  async function reorder(ids) { await api.galleryReorder(did(), ids); return fire() }
  async function removeImage(id) { await api.deleteImage(did(), id); return fire() }

  function _move(id, delta) {
    const order = galleryItems.value.map((i) => i.id)
    const idx = order.indexOf(id)
    const j = idx + delta
    if (idx < 0 || j < 0 || j >= order.length) return null
    const next = order.slice()
    ;[next[idx], next[j]] = [next[j], next[idx]]
    return next
  }
  async function moveUp(id) { const o = _move(id, -1); if (o) { await api.galleryReorder(did(), o); return fire() } }
  async function moveDown(id) { const o = _move(id, 1); if (o) { await api.galleryReorder(did(), o); return fire() } }

  async function copyFrom(siblingId, urls) {
    if (!urls || !urls.length) return
    await api.copyImagesTo(siblingId, urls, [did()])
    return fire()
  }

  async function upload(file) {
    const r = await api.uploadMedia(did(), file, 'image')
    const url = r && r.url
    if (!url) return
    const d = draftRef.value || {}
    const imgs = Array.isArray(d.images) ? d.images.slice() : []
    imgs.push(url)
    await api.patchDraft(did(), { images: imgs })
    return fire()
  }

  async function fetchSiblingMaterials(siblingId) {
    const r = await api.getDraft(siblingId)
    const d = (r && r.draft) ? r.draft : r
    return Array.isArray(d && d.materials) ? d.materials : []
  }

  return {
    galleryItems, materialItems, localUrl,
    addToGallery, removeFromGallery, reorder, removeImage,
    moveUp, moveDown, copyFrom, upload, fetchSiblingMaterials,
  }
}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `npm run test -- useGallery`
Expected: PASS（9 个用例）

- [ ] **Step 6: 提交**

```bash
git add apps/webui/frontend/src/api.js apps/webui/frontend/src/composables/useGallery.js apps/webui/frontend/src/composables/useGallery.test.js
git commit -m "feat(images): api gallery 系列+copyImagesTo + useGallery composable(两池派生+增删序借图上传)"
```

---

### Task 2: ImageCard.vue 纯展示组件

**Files:**
- Create: `apps/webui/frontend/src/components/workbench/ImageCard.vue`
- Test: `apps/webui/frontend/src/components/workbench/ImageCard.test.js`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/components/workbench/ImageCard.test.js`:
```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ImageCard from './ImageCard.vue'

function factory(props = {}, slots = {}) {
  return mount(ImageCard, {
    props: { url: 'http://x/a.jpg', localUrl: '/media/a.jpg', type: '白底', source: 'generated', ...props },
    slots,
  })
}

describe('ImageCard', () => {
  it('img 用 localUrl 优先', () => {
    const w = factory()
    expect(w.find('img').attributes('src')).toBe('/media/a.jpg')
  })
  it('localUrl 缺时回退 url', () => {
    const w = factory({ localUrl: '' })
    expect(w.find('img').attributes('src')).toBe('http://x/a.jpg')
  })
  it('显示类型徽章', () => {
    expect(factory().text()).toContain('白底')
  })
  it('selected 加选中类', () => {
    const w = factory({ selected: true })
    expect(w.classes().some(c => c.includes('selected') || c.includes('is-sel'))).toBe(true)
  })
  it('actions 插槽渲染', () => {
    const w = factory({}, { actions: '<button class="act">删</button>' })
    expect(w.find('button.act').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npm run test -- ImageCard`
Expected: FAIL

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/components/workbench/ImageCard.vue`:
```vue
<script setup>
import { computed } from 'vue'

const props = defineProps({
  url: { type: String, required: true },
  localUrl: { type: String, default: '' },
  type: { type: String, default: '' },
  source: { type: String, default: '' },
  selected: { type: Boolean, default: false },
  badge: { type: String, default: '' },
})
const src = computed(() => props.localUrl || props.url)
const sourceLabel = computed(() => (props.source === 'generated' ? '生成' : props.source === 'collected' ? '采集' : ''))
</script>

<template>
  <div class="img-card" :class="{ 'is-selected': selected }">
    <img :src="src" loading="lazy" alt="" />
    <span v-if="type" class="img-card__type">{{ type }}</span>
    <span v-if="sourceLabel" class="img-card__src">{{ sourceLabel }}</span>
    <span v-if="badge" class="img-card__badge">{{ badge }}</span>
    <div class="img-card__actions"><slot name="actions" /></div>
  </div>
</template>

<style scoped>
.img-card{position:relative;width:88px;height:88px;border-radius:var(--r-sm,8px);overflow:hidden;
  border:1px solid var(--c-border,#e5e7eb);background:#fafafa}
.img-card.is-selected{outline:2px solid var(--c-primary,#7c3aed);outline-offset:1px}
.img-card img{width:100%;height:100%;object-fit:cover;display:block}
.img-card__type{position:absolute;left:3px;top:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(124,58,237,.85);color:#fff}
.img-card__src{position:absolute;right:3px;top:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff}
.img-card__badge{position:absolute;left:3px;bottom:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff}
.img-card__actions{position:absolute;inset:auto 0 0 0;display:flex;gap:2px;justify-content:center;
  padding:2px;background:rgba(255,255,255,.9);opacity:0;transition:.15s}
.img-card:hover .img-card__actions{opacity:1}
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npm run test -- ImageCard`
Expected: PASS（5 个用例）

- [ ] **Step 5: 提交**

```bash
git add apps/webui/frontend/src/components/workbench/ImageCard.vue apps/webui/frontend/src/components/workbench/ImageCard.test.js
git commit -m "feat(images): ImageCard 纯展示(localUrl优先/类型来源徽章/选中/actions插槽)"
```

---

### Task 3: ImagesTab.vue 三段 + 接线 DetailTabs

**Files:**
- Create: `apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue`
- Test: `apps/webui/frontend/src/components/workbench/tabs/ImagesTab.test.js`
- Modify: `apps/webui/frontend/src/components/workbench/DetailTabs.vue`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/components/workbench/tabs/ImagesTab.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
vi.mock('../../../api.js', () => ({ api: {
  galleryAdd: vi.fn().mockResolvedValue({ id: 7 }),
  galleryRemove: vi.fn().mockResolvedValue({ id: 7 }),
  galleryReorder: vi.fn().mockResolvedValue({ id: 7 }),
  deleteImage: vi.fn().mockResolvedValue({ id: 7 }),
  copyImagesTo: vi.fn().mockResolvedValue({ ok: true, added: {} }),
  uploadMedia: vi.fn().mockResolvedValue({ url: 'http://up/n.jpg' }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
  getDraft: vi.fn().mockResolvedValue({ draft: { id: 8, materials: [] } }),
} }))
import { api } from '../../../api.js'
import ImagesTab from './ImagesTab.vue'

const draft = {
  id: 7, images: ['http://g/1.jpg'], local_images: ['/media/1.jpg'],
  materials: [
    { id: 1, url: 'http://g/1.jpg', type: '白底', source: 'generated', in_gallery: 1, position: 0 },
    { id: 3, url: 'http://m/3.jpg', type: '', source: 'collected', in_gallery: 0, position: 1 },
  ],
}

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function factory() {
  return mount(ImagesTab, { props: { draft }, global: { stubs: { teleport: true } } })
}

describe('ImagesTab', () => {
  it('渲图集段(1)+素材段(1)', () => {
    const w = factory()
    expect(w.findAllComponents({ name: 'ImageCard' }).length).toBe(2)
    expect(w.text()).toContain('图集'); expect(w.text()).toContain('素材')
  })
  it('素材「加入图集」触发 galleryAdd', async () => {
    const w = factory()
    const addBtn = w.findAll('button').find(b => b.text().includes('加入图集'))
    await addBtn.trigger('click')
    expect(api.galleryAdd).toHaveBeenCalledWith(7, [3])
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npm run test -- ImagesTab`
Expected: FAIL

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue`:
```vue
<script setup>
import { ref, computed, toRef } from 'vue'
import { ElMessage, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import { useWorkbenchStore } from '../../../stores/workbench.js'
import { useGallery } from '../../../composables/useGallery.js'
import ImageCard from '../ImageCard.vue'
import { SButton } from '../../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['saved'])
const draftRef = toRef(props, 'draft')
const wb = useWorkbenchStore()
const g = useGallery(draftRef, { onChange: () => emit('saved') })

const selMaterials = ref([])           // 素材多选 id
const toggleMat = (id) => { const i = selMaterials.value.indexOf(id); i >= 0 ? selMaterials.value.splice(i, 1) : selMaterials.value.push(id) }

const siblings = computed(() => wb.variants.filter((v) => v.id !== props.draft.id))
const borrowId = ref(null)
const borrowMats = ref([])
const borrowSel = ref([])
async function onBorrowPick(id) {
  borrowId.value = id; borrowSel.value = []
  borrowMats.value = id != null ? await g.fetchSiblingMaterials(id) : []
}
const toggleBorrow = (url) => { const i = borrowSel.value.indexOf(url); i >= 0 ? borrowSel.value.splice(i, 1) : borrowSel.value.push(url) }

async function addOne(id) { await g.addToGallery([id]) }
async function batchAdd() { if (selMaterials.value.length) { await g.addToGallery(selMaterials.value.slice()); selMaterials.value = [] } }
async function delImg(id) {
  try { await ElMessageBox.confirm('彻底删除这张图（素材与图集都删）？', '确认', { type: 'warning' }) } catch { return }
  await g.removeImage(id)
}
async function doBorrow() {
  if (!borrowId.value || !borrowSel.value.length) return
  await g.copyFrom(borrowId.value, borrowSel.value.slice())
  ElMessage.success(`已借 ${borrowSel.value.length} 张到图集`); borrowSel.value = []
}
const fileInput = ref(null)
function pickFile() { fileInput.value && fileInput.value.click() }
async function onFile(e) {
  const f = e.target.files && e.target.files[0]; if (!f) return
  await g.upload(f); e.target.value = ''; ElMessage.success('已上传到图集')
}
</script>

<template>
  <div class="images-tab">
    <!-- 图集段 -->
    <section class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">图集（发布顺序，{{ g.galleryItems.value.length }}）</span>
        <SButton size="sm" @click="pickFile">上传图片</SButton>
        <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onFile" />
      </div>
      <div v-if="g.galleryItems.value.length" class="images-tab__grid">
        <ImageCard v-for="(it, i) in g.galleryItems.value" :key="it.id"
          :url="it.url" :local-url="g.localUrl(it.url)" :type="it.type" :source="it.source" :badge="String(i + 1)">
          <template #actions>
            <button class="ic-btn" :disabled="i === 0" title="上移" @click="g.moveUp(it.id)">↑</button>
            <button class="ic-btn" :disabled="i === g.galleryItems.value.length - 1" title="下移" @click="g.moveDown(it.id)">↓</button>
            <button class="ic-btn" title="移出图集" @click="g.removeFromGallery([it.id])">−</button>
            <button class="ic-btn ic-btn--danger" title="删除" @click="delImg(it.id)">✕</button>
          </template>
        </ImageCard>
      </div>
      <div v-else class="images-tab__empty">图集为空，从下方素材库选图加入。</div>
    </section>

    <!-- 素材库段 -->
    <section class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">素材库（{{ g.materialItems.value.length }}）</span>
        <SButton v-if="selMaterials.length" size="sm" variant="primary" @click="batchAdd">批量加入图集（{{ selMaterials.length }}）</SButton>
      </div>
      <div v-if="g.materialItems.value.length" class="images-tab__grid">
        <ImageCard v-for="m in g.materialItems.value" :key="m.id"
          :url="m.url" :local-url="g.localUrl(m.url)" :type="m.type" :source="m.source"
          :selected="selMaterials.includes(m.id)" @click="toggleMat(m.id)">
          <template #actions>
            <button class="ic-btn" title="加入图集" @click.stop="addOne(m.id)">加入图集</button>
            <button class="ic-btn ic-btn--danger" title="删除" @click.stop="delImg(m.id)">✕</button>
          </template>
        </ImageCard>
      </div>
      <div v-else class="images-tab__empty">没有未入图集的素材。</div>
    </section>

    <!-- 来自变体借图 -->
    <section v-if="siblings.length" class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">来自变体</span>
        <ElSelect :model-value="borrowId" placeholder="选一个同组变体借图" clearable style="width:200px" @change="onBorrowPick">
          <ElOption v-for="v in siblings" :key="v.id" :label="v.spec || `变体${v.id}`" :value="v.id" />
        </ElSelect>
        <SButton v-if="borrowSel.length" size="sm" variant="primary" @click="doBorrow">借 {{ borrowSel.length }} 张到图集</SButton>
      </div>
      <div v-if="borrowMats.length" class="images-tab__grid">
        <ImageCard v-for="m in borrowMats" :key="m.id"
          :url="m.url" :local-url="m.url" :type="m.type" :source="m.source"
          :selected="borrowSel.includes(m.url)" @click="toggleBorrow(m.url)" />
      </div>
      <div v-else-if="borrowId != null" class="images-tab__empty">该变体没有素材。</div>
    </section>
  </div>
</template>

<style scoped>
.images-tab{padding:var(--sp-3,12px)}
.images-tab__sec{margin-bottom:var(--sp-5,20px)}
.images-tab__head{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-2,8px)}
.images-tab__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.images-tab__grid{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px)}
.images-tab__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888)}
.ic-btn{border:none;background:transparent;cursor:pointer;font-size:11px;padding:1px 4px;color:var(--c-text-2,#555)}
.ic-btn:hover{color:var(--c-primary,#7c3aed)}
.ic-btn--danger:hover{color:var(--c-danger,#e5484d)}
.ic-btn:disabled{opacity:.35;cursor:not-allowed}
</style>
```

> 注意：若 `npm run test -- ImagesTab` 因 ElSelect/ElMessageBox 在 jsdom 报错，可在测试用 `global.stubs` 里 stub `ElSelect`；测试意图保留（2 张 ImageCard、「加入图集」触发 galleryAdd(7,[3])）。`SButton` size/variant 已确认存在。

- [ ] **Step 4: 跑测试确认通过**

Run: `npm run test -- ImagesTab`
Expected: PASS（2 个用例）

- [ ] **Step 5: 接线 DetailTabs.vue**

`apps/webui/frontend/src/components/workbench/DetailTabs.vue`：
- 顶部 import 加：`import ImagesTab from './tabs/ImagesTab.vue'`
- 模板把 `<div v-else-if="active === 'images'" class="dt__ph">图片 tab 将在 F1d-3 实现(接素材/图集)</div>`
  换成：`<ImagesTab v-else-if="active === 'images'" :draft="fm.draft.value" @saved="fm.load" />`

- [ ] **Step 6: 全量测试 + 提交**

Run: `npm run test`
Expected: 失败数 ≤32（基线），新增用例全过。

```bash
git add apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue apps/webui/frontend/src/components/workbench/tabs/ImagesTab.test.js apps/webui/frontend/src/components/workbench/DetailTabs.vue
git commit -m "feat(images): ImagesTab 三段(图集排序/素材加入/来自变体借图/上传)接入 DetailTabs"
```

---

### Task 4: 产品文档同步 + 收尾

**Files:**
- Modify: `docs/product/material-gallery.md`（§4 前端图片 tab 补实现）
- Modify: `docs/product/workbench.md`（图片 tab 行 + 变更历史）

- [ ] **Step 1: 更新 material-gallery.md**

把 §4「前端图片 tab（ImagesTab，F1d-3 — 待建）」改成已实现：三段（图集排序/移出/删除/上传、素材加入图集/删除、来自变体借图），用 `useGallery` composable（派生两池 + mutation 后 onChange 重拉）+ `ImageCard`；api.js 补 galleryAdd/Remove/Reorder/deleteImage/copyImagesTo。注明 AI 出图在 F1d-3b。变更历史加一行。

- [ ] **Step 2: 更新 workbench.md**

详情 tab 第 3 行「图片 ImagesTab」补：两池（图集/素材）+ 借图 + 上传，详见 material-gallery.md。变更历史加 F1d-3a 一行。

- [ ] **Step 3: 提交**

```bash
git add docs/product/material-gallery.md docs/product/workbench.md
git commit -m "docs(product): 图片 tab 两池管理(F1d-3a)交互/数据/规则同步"
```

---

## Controller 复核（每任务后 + 全部后）
- 每任务：读 diff、跑该任务测试、确认 TDD 红→绿。
- 全部后：`npm run test` 全量（≤32 不新增）+ `npm run build`；起本地后端做**端到端/浏览器验收**：隔离临时库种一个带 materials（混 in_gallery 0/1）+ local_images 的草稿（最好同组 2 变体便于验借图），验：图集段有序渲染、素材段渲染、加入图集/移出/↑↓/删除走通、借图下拉拉到兄弟素材并复制成功。**重点实证「素材（采集图）能否显示」**（spec 已知风险）：若纯 1688 防盗链显示不出，记录并起小后端补丁任务（getDraft 给 material 加 local_url）。验完杀后端 + 删临时库。
