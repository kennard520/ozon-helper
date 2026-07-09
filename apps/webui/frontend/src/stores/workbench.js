import { defineStore } from 'pinia'
import { api } from '../api.js'

// —— 变体颜色芯片取色策略(VariantCardsPane / DetailTabs 共用,别两处写死)——
// 1) 优先从变体数据取颜色词(显式 color 字段 / aspect 属性 / spec 文本)
// 2) 命中常见中/俄/英颜色名 → 固定 hex
// 3) 取不到 → 按变体 id 稳定哈希出 hue,保证各变体色块互相可区分(非全紫,也不假装精确商品色)
const COLOR_HEX = {
  // 中文
  '红': '#ef4444', '红色': '#ef4444', '黑': '#1f2733', '黑色': '#1f2733',
  '白': '#f3f4f6', '白色': '#f3f4f6', '蓝': '#3b82f6', '蓝色': '#3b82f6',
  '绿': '#10b981', '绿色': '#10b981', '黄': '#f59e0b', '黄色': '#f59e0b',
  '灰': '#9ca3af', '灰色': '#9ca3af', '粉': '#ec4899', '粉色': '#ec4899',
  '紫': '#7c3aed', '紫色': '#7c3aed', '橙': '#f97316', '橙色': '#f97316',
  '棕': '#92400e', '棕色': '#92400e', '银': '#cbd5e1', '银色': '#cbd5e1',
  '金': '#d4af37', '金色': '#d4af37',
  // 俄语
  'красный': '#ef4444', 'чёрный': '#1f2733', 'черный': '#1f2733',
  'белый': '#f3f4f6', 'синий': '#3b82f6', 'голубой': '#60a5fa',
  'зелёный': '#10b981', 'зеленый': '#10b981', 'жёлтый': '#f59e0b', 'желтый': '#f59e0b',
  'серый': '#9ca3af', 'розовый': '#ec4899', 'фиолетовый': '#7c3aed',
  'оранжевый': '#f97316', 'коричневый': '#92400e', 'серебристый': '#cbd5e1',
  'золотой': '#d4af37',
  // 英语
  'red': '#ef4444', 'black': '#1f2733', 'white': '#f3f4f6', 'blue': '#3b82f6',
  'green': '#10b981', 'yellow': '#f59e0b', 'gray': '#9ca3af', 'grey': '#9ca3af',
  'pink': '#ec4899', 'purple': '#7c3aed', 'orange': '#f97316', 'brown': '#92400e',
  'silver': '#cbd5e1', 'gold': '#d4af37',
}

export function variantColorName(v) {
  // 显式颜色字段优先;其次从 aspect 属性里找;最后回退 spec 文本
  if (v && v.color) return String(v.color)
  if (v && Array.isArray(v.aspects)) {
    const a = v.aspects.find(x => /颜色|цвет|color/i.test(String(x && x.name)))
    if (a && a.value) return String(a.value)
  }
  return v && v.spec ? String(v.spec) : ''
}

function hashHue(id) {
  const str = String(id == null ? '' : id)
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h % 360
}

export function variantColor(v) {
  const name = variantColorName(v).toLowerCase()
  for (const key in COLOR_HEX) {
    if (name.includes(key)) return COLOR_HEX[key]
  }
  // 取不到可识别颜色名 → 按 id 稳定哈希出可区分色相
  return `hsl(${hashHue(v && v.id)}, 62%, 56%)`
}

export const useWorkbenchStore = defineStore('workbench', {
  state: () => ({
    groupKey: '', variants: [], selectedVariantIds: new Set(),
    currentVariantId: null, loading: false,
    currentVariantVersion: 0,
    taskByVariant: {}, taskCheckingIds: new Set(),
    focusTarget: null,
  }),
  getters: {
    currentVariant: (s) => s.variants.find(v => v.id === s.currentVariantId) || null,
    // 当前查看变体在 variants 中的下标(0-based);找不到 → -1
    currentVariantIndex: (s) => s.variants.findIndex(v => v.id === s.currentVariantId),
    selectedVariants: (s) => s.variants.filter(v => s.selectedVariantIds.has(v.id)),
    variantCount: (s) => s.variants.length,
    allSelected: (s) => s.variants.length > 0 && s.variants.every(v => s.selectedVariantIds.has(v.id)),
    stepProgress: (s) => (stepId) => {
      const sel = s.variants.filter(v => s.selectedVariantIds.has(v.id))
      return { done: sel.filter(v => v.steps && v.steps[stepId]).length, total: sel.length }
    },
    // 当前查看变体的某一步是否完成(流水线面板按单变体显示进度用);
    // currentVariant 为 null 或该步未完成都回 false
    currentStepDone: (s) => (stepId) => {
      if (!s.currentVariant) return false
      if (stepId === 'content') {
        const job = s.taskByVariant[s.currentVariant.id]
        if (String((job && job.status) || '').toLowerCase() === 'done') return true
      }
      return !!(s.currentVariant.steps && s.currentVariant.steps[stepId])
    },
    variantTask: (s) => (id) => (id == null ? null : (s.taskByVariant[id] || null)),
    variantTaskRunning: (s) => (id) => {
      const job = id == null ? null : s.taskByVariant[id]
      const status = String((job && job.status) || '').toLowerCase()
      return status && status !== 'done' && status !== 'failed'
    },
    variantTaskChecking: (s) => (id) => s.taskCheckingIds.has(id),
  },
  actions: {
    async loadForDraft(draftId) {
      if (draftId == null) { this.reset(); return }
      this.loading = true
      const versionAtStart = this.currentVariantVersion
      try {
        const r = await api.variantGroup(draftId)
        const vs = r.variants || []
        this.groupKey = r.group || ''
        this.variants = vs.length ? vs : [{ id: draftId, spec: '', price: null, status: '', image: '', current: true }]
        // 默认聚焦:优先打开传入的草稿(若它确在变体组里),否则回退到第一个变体,
        // 保证「进来就有一个变体被选中查看」、详情不空着。
        const hasDraft = this.variants.some(v => v.id === draftId)
        const userChangedCurrent = this.currentVariantVersion !== versionAtStart
        const hasCurrent = this.variants.some(v => v.id === this.currentVariantId)
        this.currentVariantId = (userChangedCurrent && hasCurrent)
          ? this.currentVariantId
          : (hasDraft ? draftId : (this.variants[0] ? this.variants[0].id : null))
        this.selectedVariantIds = new Set(this.variants.map(v => v.id))
      } finally { this.loading = false }
    },
    reset() {
      this.groupKey = ''
      this.variants = []
      this.selectedVariantIds = new Set()
      this.currentVariantId = null
      this.currentVariantVersion += 1
      this.taskByVariant = {}
      this.taskCheckingIds = new Set()
    },
    setCurrentVariant(id) { this.currentVariantId = id; this.currentVariantVersion += 1 },
    requestFocus(target) {
      this.focusTarget = { ...(target || {}), nonce: Date.now() }
    },
    setVariantTask(id, job) {
      if (id == null) return
      this.taskByVariant = { ...this.taskByVariant, [id]: job || null }
    },
    setVariantTaskChecking(id, checking) {
      if (id == null) return
      const s = new Set(this.taskCheckingIds)
      checking ? s.add(id) : s.delete(id)
      this.taskCheckingIds = s
    },
    async checkVariantTask(id) {
      if (id == null) return null
      this.setVariantTaskChecking(id, true)
      try {
        const job = await api.getLatestTextJob(id)
        this.setVariantTask(id, job || null)
        return job || null
      } catch {
        this.setVariantTask(id, null)
        return null
      } finally {
        this.setVariantTaskChecking(id, false)
      }
    },
    // 翻页切换「当前查看的变体」(独立于批量勾选),在 variants 里循环
    nextVariant() {
      if (!this.variants.length) return
      const i = this.currentVariantIndex
      const next = i < 0 ? 0 : (i + 1) % this.variants.length
      this.currentVariantId = this.variants[next].id
      this.currentVariantVersion += 1
    },
    prevVariant() {
      if (!this.variants.length) return
      const i = this.currentVariantIndex
      const prev = i < 0 ? 0 : (i - 1 + this.variants.length) % this.variants.length
      this.currentVariantId = this.variants[prev].id
      this.currentVariantVersion += 1
    },
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
