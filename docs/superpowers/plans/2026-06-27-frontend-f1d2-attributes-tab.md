# F1d-2 特征(Attributes)tab 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。逐任务实现，checkbox 跟踪。

**Goal:** 工作台 DetailTabs 的「特征」tab：按类目展示/填写 Ozon 属性（变体维度/必填/可选），字典下拉(单多选+大字典远程搜)/自由文本/AI 填充/必填缺失提示，单一真相源、客户端算 missing、防抖保存。

**Architecture:** `useAttributes` composable（数据+逻辑）+ `AttrField.vue`（纯展示单字段）+ `AttributesTab.vue`（布局/AI/保存）。零后端改动，复用 `requiredCheck/attributeOptions/attributeValues/aiFillAttributes/patchDraft`。

**Tech Stack:** Vue 3.5 `<script setup>`、Element Plus(ElSelect/ElOption/ElInput)、Pinia、Vitest + @vue/test-utils。

**目录基准**：前端根 `apps/webui/frontend/`，命令在该目录跑 `npm run test`（vitest run）。canonical 单属性值形状：`Array<{dictionary_value_id?, value}>`。

---

### Task 1: useAttributes composable —— 值模型 + missing 派生 + 保存

**Files:**
- Create: `apps/webui/frontend/src/composables/useAttributes.js`
- Test: `apps/webui/frontend/src/composables/useAttributes.test.js`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/composables/useAttributes.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  requiredCheck: vi.fn().mockResolvedValue({
    aspects: [{ id: 10, name: '颜色', is_required: true, is_aspect: true, is_collection: false, dictionary_id: 5 }],
    required: [{ id: 20, name: '材料', is_required: true, is_aspect: false, is_collection: false, dictionary_id: 7 }],
    optional: [{ id: 30, name: '备注', is_required: false, is_aspect: false, is_collection: false, dictionary_id: 0 }],
    missing: [{ id: 20, name: '材料' }], errors: [],
  }),
  attributeOptions: vi.fn().mockResolvedValue({ values: [{ id: 101, value: '红' }], oversized: false }),
  attributeValues: vi.fn().mockResolvedValue({ result: [{ id: 999, value: '搜到的' }] }),
  aiFillAttributes: vi.fn().mockResolvedValue({ draft: { id: 7, category_id: '1', type_id: '2',
    attributes: [{ id: 20, values: [{ dictionary_value_id: 701, value: '棉' }] }] }, mapped_count: 1 }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
} }))
import { api } from '../api.js'
import { useAttributes } from './useAttributes.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); vi.useFakeTimers() })

function mkDraft(attrs = []) {
  return ref({ id: 7, category_id: '1', type_id: '2', attributes: attrs })
}

describe('useAttributes', () => {
  it('从 draft.attributes 建 values + 拉 defs 分组', async () => {
    const d = mkDraft([{ id: 10, values: [{ dictionary_value_id: 101, value: '红' }] }])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(api.requiredCheck).toHaveBeenCalledWith(7, 'ZH_HANS')
    expect(a.groups.value.aspects.length).toBe(1)
    expect(a.groups.value.required.length).toBe(1)
    expect(a.values[10]).toEqual([{ dictionary_value_id: 101, value: '红' }])
  })

  it('missingIds：required 空算缺、填了不缺', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(a.missingIds.value).toContain(20)        // 材料(required) 未填
    a.setValue(20, [{ dictionary_value_id: 701, value: '棉' }])
    await nextTick()
    expect(a.missingIds.value).not.toContain(20)
  })

  it('setValue 后防抖 patchDraft({attributes})', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    a.setValue(20, [{ dictionary_value_id: 701, value: '棉' }])
    vi.advanceTimersByTime(350)
    await Promise.resolve()
    expect(api.patchDraft).toHaveBeenCalled()
    const patch = api.patchDraft.mock.calls[0][1]
    expect(patch.attributes).toEqual([{ id: 20, values: [{ dictionary_value_id: 701, value: '棉' }] }])
  })

  it('aiFill 调 api 并用返回 draft 重建 values', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    await a.aiFill()
    expect(api.aiFillAttributes).toHaveBeenCalledWith(7)
    expect(a.values[20]).toEqual([{ dictionary_value_id: 701, value: '棉' }])
  })

  it('ensureOptions 拉全量选项；oversized 标记', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    await a.ensureOptions({ id: 10, dictionary_id: 5 })
    expect(api.attributeOptions).toHaveBeenCalledWith('1', '2', 10, 'ZH_HANS')
    expect(a.optionsOf(10)).toEqual([{ id: 101, value: '红' }])
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run（在 `apps/webui/frontend/`）: `npm run test -- useAttributes`
Expected: FAIL（useAttributes.js 不存在）

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/composables/useAttributes.js`:
```js
import { reactive, ref, computed, watch } from 'vue'
import { api } from '../api.js'

const LANG = 'ZH_HANS'

export function useAttributes(draftRef) {
  const groups = ref({ aspects: [], required: [], optional: [] })
  const errors = ref([])
  const loading = ref(false)
  const values = reactive({})              // 单一真相：attrId -> [{dictionary_value_id?, value}]
  const options = reactive({})             // attrId -> [{id,value}]
  const loadingMap = reactive({})          // attrId -> bool（远程搜 loading）
  const oversized = reactive({})           // attrId -> bool
  const optLoaded = reactive({})           // attrId -> bool（全量选项已拉）

  function catType() {
    const d = draftRef.value || {}
    return [String(d.category_id || '').trim(), String(d.type_id || '').trim()]
  }

  function rebuildValues(attrs) {
    for (const k of Object.keys(values)) delete values[k]
    for (const a of Array.isArray(attrs) ? attrs : []) {
      if (a && a.id != null && Array.isArray(a.values)) values[a.id] = a.values.map((v) => ({ ...v }))
    }
  }

  async function reloadDefs() {
    const d = draftRef.value
    if (!d || d.id == null) { groups.value = { aspects: [], required: [], optional: [] }; return }
    const [cat, typ] = catType()
    if (!cat || !typ) { groups.value = { aspects: [], required: [], optional: [] }; errors.value = []; return }
    loading.value = true
    try {
      const r = await api.requiredCheck(d.id, LANG)
      groups.value = { aspects: r.aspects || [], required: r.required || [], optional: r.optional || [] }
      errors.value = r.errors || []
    } finally { loading.value = false }
  }

  const allDefs = computed(() => [
    ...groups.value.aspects, ...groups.value.required, ...groups.value.optional,
  ])

  const missingIds = computed(() => {
    const req = allDefs.value.filter((d) => d.is_required)
    return req.filter((d) => {
      const v = values[d.id]
      return !Array.isArray(v) || v.length === 0
    }).map((d) => d.id)
  })

  let saveTimer = null
  function serialize() {
    return Object.keys(values)
      .map((id) => ({ id: Number(id), values: values[id] }))
      .filter((a) => Array.isArray(a.values) && a.values.length > 0)
  }
  async function save() {
    const d = draftRef.value
    if (!d || d.id == null) return
    await api.patchDraft(d.id, { attributes: serialize() })
  }
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { save() }, 300)
  }

  function setValue(attrId, valuesArr) {
    if (Array.isArray(valuesArr) && valuesArr.length) values[attrId] = valuesArr
    else delete values[attrId]
    scheduleSave()
  }

  async function ensureOptions(def) {
    const id = def.id
    if (Number(def.dictionary_id) <= 0 || optLoaded[id]) return
    const [cat, typ] = catType()
    if (!cat || !typ) return
    try {
      const r = await api.attributeOptions(cat, typ, id, LANG)
      if (r.oversized) { oversized[id] = true }
      else {
        const cur = (options[id] || []).filter((o) => !(r.values || []).some((x) => x.id === o.id))
        options[id] = [...cur, ...(r.values || [])]
      }
      optLoaded[id] = true
    } catch (e) { /* 不阻断，仍可手填/远程搜 */ }
  }

  async function search(def, q) {
    const id = def.id
    if (!q || String(q).length < 2) return
    const [cat, typ] = catType()
    if (!cat || !typ) return
    loadingMap[id] = true
    try {
      const r = await api.attributeValues(cat, typ, id, q, LANG)
      options[id] = r.result || []
    } finally { loadingMap[id] = false }
  }

  async function aiFill() {
    const d = draftRef.value
    if (!d || d.id == null) return { error: 'no draft' }
    loading.value = true
    try {
      const r = await api.aiFillAttributes(d.id)
      if (r && r.draft) rebuildValues(r.draft.attributes)
      return r || {}
    } finally { loading.value = false }
  }

  watch(draftRef, (d) => { rebuildValues(d && d.attributes); reloadDefs() }, { immediate: true, deep: false })
  // 类目变 → 重拉 defs
  watch(() => { const d = draftRef.value || {}; return `${d.category_id}|${d.type_id}` }, () => reloadDefs())

  return {
    groups, values, errors, loading, missingIds,
    optionsOf: (id) => options[id] || [],
    loadingOf: (id) => !!loadingMap[id],
    oversizedOf: (id) => !!oversized[id],
    ensureOptions, search, setValue, aiFill, save, reloadDefs,
  }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npm run test -- useAttributes`
Expected: PASS（5 个用例）

- [ ] **Step 5: 提交**

```bash
git add apps/webui/frontend/src/composables/useAttributes.js apps/webui/frontend/src/composables/useAttributes.test.js
git commit -m "feat(detail): useAttributes composable —— 单一真相值模型+客户端算missing+防抖保存+AI填充"
```

---

### Task 2: AttrField.vue —— 纯展示单属性字段

**Files:**
- Create: `apps/webui/frontend/src/components/workbench/AttrField.vue`
- Test: `apps/webui/frontend/src/components/workbench/AttrField.test.js`

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/components/workbench/AttrField.test.js`:
```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AttrField from './AttrField.vue'

const dictDef = { id: 10, name: '颜色', dictionary_id: 5, is_collection: false, is_required: true }
const multiDef = { id: 11, name: '标签', dictionary_id: 6, is_collection: true, max_value_count: 3 }
const textDef = { id: 30, name: '备注', dictionary_id: 0, is_collection: false }

function factory(def, props = {}) {
  return mount(AttrField, { props: { def, modelValue: [], options: [], loading: false, oversized: false, missing: false, ...props } })
}

describe('AttrField', () => {
  it('字典属性(dictionary_id>0)渲 ElSelect', () => {
    const w = factory(dictDef, { options: [{ id: 101, value: '红' }] })
    expect(w.findComponent({ name: 'ElSelect' }).exists()).toBe(true)
  })

  it('自由文本属性渲 ElInput', () => {
    const w = factory(textDef)
    expect(w.findComponent({ name: 'ElInput' }).exists()).toBe(true)
    expect(w.findComponent({ name: 'ElSelect' }).exists()).toBe(false)
  })

  it('字典单选 pick → emit canonical values 数组', async () => {
    const w = factory(dictDef, { options: [{ id: 101, value: '红' }] })
    w.findComponent({ name: 'ElSelect' }).vm.$emit('change', 101)
    await w.vm.$nextTick()
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual([{ dictionary_value_id: 101, value: '红' }])
  })

  it('字典多选 pick → emit 多条 canonical values', async () => {
    const w = factory(multiDef, { options: [{ id: 1, value: 'a' }, { id: 2, value: 'b' }] })
    w.findComponent({ name: 'ElSelect' }).vm.$emit('change', [1, 2])
    await w.vm.$nextTick()
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual([
      { dictionary_value_id: 1, value: 'a' }, { dictionary_value_id: 2, value: 'b' },
    ])
  })

  it('自由文本输入 → emit [{value}]', async () => {
    const w = factory(textDef)
    w.findComponent({ name: 'ElInput' }).vm.$emit('change', '手填值')
    await w.vm.$nextTick()
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual([{ value: '手填值' }])
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npm run test -- AttrField`
Expected: FAIL（AttrField.vue 不存在）

- [ ] **Step 3: 实现**

`apps/webui/frontend/src/components/workbench/AttrField.vue`:
```vue
<script setup>
import { computed } from 'vue'
import { ElSelect, ElOption, ElInput } from 'element-plus'

const props = defineProps({
  def: { type: Object, required: true },
  modelValue: { type: Array, default: () => [] },   // canonical [{dictionary_value_id?, value}]
  options: { type: Array, default: () => [] },        // [{id, value}]
  loading: { type: Boolean, default: false },
  oversized: { type: Boolean, default: false },
  missing: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'ensure', 'search'])

const isDict = computed(() => Number(props.def.dictionary_id) > 0)
const multiple = computed(() => !!props.def.is_collection)

// 下拉选中态：单选=标量 id，多选=id 数组
const selected = computed(() => {
  const ids = (props.modelValue || []).map((v) => v.dictionary_value_id).filter((x) => x != null)
  return multiple.value ? ids : (ids[0] ?? '')
})
// 文本态
const textVal = computed(() => (props.modelValue || []).map((v) => v.value || '').filter(Boolean).join(' , '))

function optById(id) {
  const o = props.options.find((x) => x.id === id)
  return o ? { dictionary_value_id: o.id, value: o.value } : { dictionary_value_id: id, value: String(id) }
}
function onPick(val) {
  const ids = Array.isArray(val) ? val : (val == null || val === '' ? [] : [val])
  emit('update:modelValue', ids.map(optById))
}
function onText(v) {
  const t = String(v || '').trim()
  emit('update:modelValue', t ? [{ value: t }] : [])
}
</script>

<template>
  <div class="attr-field" :class="{ 'attr-field--missing': missing }">
    <label class="attr-field__label">
      <span v-if="def.is_required" class="attr-field__req">*</span>{{ def.name }}
    </label>
    <ElSelect
      v-if="isDict"
      :model-value="selected"
      :multiple="multiple"
      :multiple-limit="def.max_value_count || 0"
      filterable clearable
      :remote="oversized"
      :remote-method="(q) => emit('search', q)"
      :loading="loading"
      placeholder="选择或搜索"
      style="width:100%"
      @visible-change="(open) => open && emit('ensure')"
      @change="onPick"
    >
      <ElOption v-for="o in options" :key="o.id" :label="o.value" :value="o.id" />
    </ElSelect>
    <ElInput v-else :model-value="textVal" placeholder="填写" @change="onText" />
  </div>
</template>

<style scoped>
.attr-field{margin-bottom:var(--sp-3, 12px)}
.attr-field__label{display:block;font-size:var(--fs-sm,13px);color:var(--c-text-2,#555);margin-bottom:4px}
.attr-field__req{color:var(--c-danger,#e5484d);margin-right:2px}
.attr-field--missing :deep(.el-select),.attr-field--missing :deep(.el-input){outline:1px solid var(--c-danger,#e5484d);border-radius:6px}
</style>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npm run test -- AttrField`
Expected: PASS（5 个用例）

- [ ] **Step 5: 提交**

```bash
git add apps/webui/frontend/src/components/workbench/AttrField.vue apps/webui/frontend/src/components/workbench/AttrField.test.js
git commit -m "feat(detail): AttrField 纯展示单属性字段(字典单多选/大字典远程搜/自由文本/必填标红)"
```

---

### Task 3: AttributesTab.vue —— 布局 + AI 填充 + 接线

**Files:**
- Create: `apps/webui/frontend/src/components/workbench/tabs/AttributesTab.vue`
- Test: `apps/webui/frontend/src/components/workbench/tabs/AttributesTab.test.js`
- Modify: `apps/webui/frontend/src/components/workbench/DetailTabs.vue`（替换 attrs 占位）

- [ ] **Step 1: 写失败测试**

`apps/webui/frontend/src/components/workbench/tabs/AttributesTab.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
vi.mock('../../../api.js', () => ({ api: {
  requiredCheck: vi.fn().mockResolvedValue({
    aspects: [{ id: 10, name: '颜色', is_required: true, is_aspect: true, dictionary_id: 5 }],
    required: [{ id: 20, name: '材料', is_required: true, is_aspect: false, dictionary_id: 7 }],
    optional: [{ id: 30, name: '备注', is_required: false, is_aspect: false, dictionary_id: 0 }],
    missing: [{ id: 20, name: '材料' }], errors: [],
  }),
  attributeOptions: vi.fn().mockResolvedValue({ values: [], oversized: false }),
  attributeValues: vi.fn().mockResolvedValue({ result: [] }),
  aiFillAttributes: vi.fn().mockResolvedValue({ draft: { id: 7, category_id: '1', type_id: '2', attributes: [] }, mapped_count: 2 }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
} }))
import { api } from '../../../api.js'
import AttributesTab from './AttributesTab.vue'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function factory() {
  return mount(AttributesTab, {
    props: { draft: { id: 7, category_id: '1', type_id: '2', attributes: [] } },
    global: { stubs: { teleport: true } },
  })
}

describe('AttributesTab', () => {
  it('渲三组 + missing banner', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await nextTick()
    expect(api.requiredCheck).toHaveBeenCalled()
    expect(w.findAllComponents({ name: 'AttrField' }).length).toBe(3)
    expect(w.text()).toContain('缺')   // missing banner 文案含「缺」
  })

  it('AI 填充按钮触发 aiFillAttributes', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    const btns = w.findAll('button')
    const aiBtn = btns.find((b) => b.text().includes('AI'))
    await aiBtn.trigger('click')
    await Promise.resolve()
    expect(api.aiFillAttributes).toHaveBeenCalledWith(7)
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `npm run test -- AttributesTab`
Expected: FAIL（AttributesTab.vue 不存在）

- [ ] **Step 3: 实现 AttributesTab.vue**

`apps/webui/frontend/src/components/workbench/tabs/AttributesTab.vue`:
```vue
<script setup>
import { toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAttributes } from '../../../composables/useAttributes.js'
import AttrField from '../AttrField.vue'
import { SButton, SAlert } from '../../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['saved'])
const draftRef = toRef(props, 'draft')
const a = useAttributes(draftRef)

const missingSet = computed(() => new Set(a.missingIds.value))
const showOptional = computed({ get: () => optionalOpen.value, set: (v) => optionalOpen.value = v })
import { ref } from 'vue'
const optionalOpen = ref(false)

function model(def) {
  return {
    get value() { return a.values[def.id] || [] },
  }
}
function onUpdate(def, val) { a.setValue(def.id, val) }

async function doAiFill() {
  const r = await a.aiFill()
  if (r && r.error) ElMessage.warning(`AI 填充失败：${r.error}`)
  else ElMessage.success(`AI 已填充 ${r.mapped_count ?? 0} 项`)
  emit('saved')
}
async function doSave() { await a.save(); emit('saved'); ElMessage.success('已保存') }
</script>

<template>
  <div class="attrs-tab">
    <div class="attrs-tab__bar">
      <SButton variant="primary" :loading="a.loading.value" @click="doAiFill">AI 填充特征</SButton>
      <SButton @click="doSave">保存</SButton>
    </div>

    <SAlert v-if="a.missingIds.value.length" type="warning">
      还缺 {{ a.missingIds.value.length }} 项必填特征
    </SAlert>

    <div v-if="a.groups.value.aspects.length" class="attrs-tab__group">
      <div class="attrs-tab__glabel">区别特征（变体维度）— 合并成一张卡时各变体靠它区分</div>
      <AttrField
        v-for="def in a.groups.value.aspects" :key="def.id" :def="def"
        :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
        :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="missingSet.has(def.id)"
        @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
      />
    </div>

    <div v-if="a.groups.value.required.length" class="attrs-tab__group">
      <div class="attrs-tab__glabel">必填（{{ a.groups.value.required.length }}）</div>
      <AttrField
        v-for="def in a.groups.value.required" :key="def.id" :def="def"
        :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
        :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="missingSet.has(def.id)"
        @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
      />
      <div class="attrs-tab__hint">品牌在「商品信息」tab 填。</div>
    </div>

    <div v-if="a.groups.value.optional.length" class="attrs-tab__group">
      <SButton size="sm" @click="optionalOpen = !optionalOpen">
        {{ optionalOpen ? '收起可选项' : `展开可选项（${a.groups.value.optional.length}）` }}
      </SButton>
      <template v-if="optionalOpen">
        <AttrField
          v-for="def in a.groups.value.optional" :key="def.id" :def="def"
          :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
          :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="false"
          @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
        />
      </template>
    </div>

    <div v-if="!a.groups.value.aspects.length && !a.groups.value.required.length && !a.groups.value.optional.length"
         class="attrs-tab__empty">先在「商品信息」tab 选好类目，再填特征。</div>
  </div>
</template>

<style scoped>
.attrs-tab{padding:var(--sp-3,12px)}
.attrs-tab__bar{display:flex;gap:var(--sp-2,8px);margin-bottom:var(--sp-3,12px)}
.attrs-tab__group{margin-top:var(--sp-4,16px)}
.attrs-tab__glabel{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555);margin-bottom:var(--sp-2,8px)}
.attrs-tab__hint,.attrs-tab__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888);margin-top:var(--sp-2,8px)}
</style>
```

> 注意：上面 `model(def)`/`showOptional` 是草稿期残留，**实现时删掉**——只保留 `optionalOpen` ref、`missingSet`、`onUpdate`、`doAiFill`、`doSave`。`import { ref }` 提到顶部 import 区。确保 `SAlert`/`SButton` 从 `ui/index.js` 具名导出存在（F0 已建）；`SButton` 若无 `size` prop 则去掉 `size="sm"`。

- [ ] **Step 4: 跑测试确认通过**

Run: `npm run test -- AttributesTab`
Expected: PASS（2 个用例）。若 `SButton` 无 `loading`/`size` prop，按实际 props 调整模板后再跑。

- [ ] **Step 5: 接线 DetailTabs.vue**

修改 `apps/webui/frontend/src/components/workbench/DetailTabs.vue`：
- 顶部 import 增加：`import AttributesTab from './tabs/AttributesTab.vue'`
- 模板里把 `<div v-else-if="active === 'attrs'" class="dt__ph">特征 tab 将在 F1d-2 实现</div>`
  换成：`<AttributesTab v-else-if="active === 'attrs'" :draft="fm.draft.value" @saved="fm.load" />`

- [ ] **Step 6: 跑全量前端测试 + 提交**

Run: `npm run test`
Expected: 失败数 ≤32（历史基线），本任务新增用例全过。

```bash
git add apps/webui/frontend/src/components/workbench/tabs/AttributesTab.vue apps/webui/frontend/src/components/workbench/tabs/AttributesTab.test.js apps/webui/frontend/src/components/workbench/DetailTabs.vue
git commit -m "feat(detail): AttributesTab(变体维度/必填/可选三组+AI填充+missing提示)接入 DetailTabs"
```

---

### Task 4: 产品文档同步 + 收尾

**Files:**
- Modify: `docs/product/workbench.md`（补「特征 tab」交互/数据/规则）

- [ ] **Step 1: 更新产品文档**

在 `docs/product/workbench.md` 的「详情 tab」AttributesTab 行补全，并在 §交互/§数据/§规则相应位置加特征 tab 说明：
- 交互：三组（变体维度置顶/必填/可选折叠）、字典下拉(单多选+大字典≥2字远程搜)、自由文本、AI 填充按钮、缺必填 banner。
- 数据：`requiredCheck`→分组 defs；值 canonical `[{dictionary_value_id?,value}]`；存 `patchDraft({attributes})`；选项 `attributeOptions`(oversized)/`attributeValues`(搜)。
- 规则：单一真相 values map、missing 客户端算、防抖 300ms 存、品牌/原产国/类型后端已排除不在此 tab、AI 直填 vs F1d-4 提案审阅区别。
- 变更历史加一行：2026-06-27 F1d-2 特征 tab。

- [ ] **Step 2: 提交**

```bash
git add docs/product/workbench.md
git commit -m "docs(product): workbench 补特征 tab 交互/数据/规则(F1d-2)"
```

---

## Controller 复核（每任务后 + 全部后）
- 每任务：读 diff、跑该任务测试、确认 TDD 红→绿。
- 全部后：`npm run test` 全量（失败数 ≤32 不新增）；起本地后端做**浏览器视觉验收**（灌一个有 category_id/type_id 的种子草稿，验：三组渲染、字典下拉拉选项、选中回显、AI 填充按钮、missing banner、类目空时空态文案）；验完 `git checkout vite.config.js` + 删临时库 + 杀端口。
