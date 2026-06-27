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
