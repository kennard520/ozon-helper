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
