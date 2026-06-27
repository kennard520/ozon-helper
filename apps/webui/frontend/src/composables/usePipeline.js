import { reactive, ref } from 'vue'
import { api } from '../api.js'
import { runConcurrent } from '../utils/runConcurrent.js'

export const WF = [
  { id: 'understand', label: '图文理解', eta: '~40s', dep: [] },
  { id: 'category', label: 'AI类型识别', eta: '~20s', dep: [] },
  { id: 'copy', label: 'AI文案', eta: '~90s', dep: [] },
  { id: 'attrs', label: '特征', eta: '~10s', dep: ['category'] },
  { id: 'images', label: '图集/出图', eta: '~2-3min', dep: ['understand'] },
  { id: 'rich', label: '富文本', eta: '即时', dep: ['images'] },
  { id: 'publish', label: '发布', eta: '~30s', dep: ['copy', 'images', 'rich'] },
]
const RUN_ONE = {
  understand: (id) => api.understand(id),
  category: (id) => api.recognizeCategory(id),
  copy: async (id) => { await api.aiGenerate(id); await api.aiProposalApply(id) },
  attrs: (id) => api.autoMap(id),
  images: async (id) => { await api.designImagePlan(id, 10); await api.imagePlan(id, false) },
  rich: (id) => api.makeRichContent(id, {}),
}

export function usePipeline(workbench, store) {
  const stepStatus = reactive(Object.fromEntries(WF.map(s => [s.id, 'idle'])))
  const batchRunningOp = ref('')

  function wfDepOk(stepId, variant) {
    const step = WF.find(s => s.id === stepId); if (!step) return false
    const flags = (variant && variant.steps) || {}
    return step.dep.every(d => flags[d])
  }
  async function runStep(stepId) {
    if (stepId === 'publish' || !RUN_ONE[stepId]) return
    const ids = [...workbench.selectedVariantIds]
    if (!ids.length) return
    stepStatus[stepId] = 'running'; batchRunningOp.value = stepId
    try {
      await runConcurrent(ids, 4, (id) => RUN_ONE[stepId](id), () => {})
      await workbench.reload()
      if (store && store.loadDrafts) store.loadDrafts()
    } finally { stepStatus[stepId] = 'idle'; batchRunningOp.value = '' }
  }
  async function runAll() {
    batchRunningOp.value = 'all'
    try {
      for (const step of WF) {
        if (step.id === 'publish' || !RUN_ONE[step.id]) continue
        await runStep(step.id)
      }
    } finally { batchRunningOp.value = '' }
  }
  return { WF, stepStatus, batchRunningOp, wfDepOk, runStep, runAll }
}
