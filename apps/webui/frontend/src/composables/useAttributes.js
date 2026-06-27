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
