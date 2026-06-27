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
    stepProgress: (s) => (stepId) => {
      const sel = s.variants.filter(v => s.selectedVariantIds.has(v.id))
      return { done: sel.filter(v => v.steps && v.steps[stepId]).length, total: sel.length }
    },
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
        this.selectedVariantIds = new Set(this.variants.map(v => v.id))
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
