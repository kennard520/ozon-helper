import { computed, getCurrentInstance, onUnmounted, reactive, watch } from 'vue'
import { api } from '../api.js'

export const WF = [
  { id: 'content', label: 'AI 生成内容', eta: '~2min（后台）', dep: [] },
  { id: 'images', label: '图集/出图', eta: '~2-3min', dep: ['content'] },
  { id: 'rich', label: '富文本', eta: '即时', dep: ['images'] },
  { id: 'publish', label: '发布', eta: '~30s', dep: ['content', 'images', 'rich'] },
]

const RUN_ONE = {
  content: (id) => api.submitTextJob(id),
  images: async (id) => {
    await api.designImagePlan(id, 10)
    await api.imagePlan(id, false)
  },
  rich: (id) => api.makeRichContent(id, {}),
}

const PIPELINE_STEP = {
  content: 'ai_text',
  images: 'ai_image',
  rich: 'rich_content',
  publish: 'publish',
}

export function usePipeline(workbench, store) {
  const statusByVariant = reactive({})
  const jobByVariant = reactive({})
  const pipelineByVariant = reactive({})
  const pollTokens = reactive({})
  const stepStatus = {}
  let unmounted = false

  for (const step of WF) {
    Object.defineProperty(stepStatus, step.id, {
      enumerable: true,
      get: () => currentStepStatus(step.id),
    })
  }

  const textJob = computed(() => {
    const id = workbench.currentVariantId
    return id == null ? null : (jobByVariant[id] || null)
  })

  const pipeline = computed(() => {
    const id = workbench.currentVariantId
    return id == null ? null : (pipelineByVariant[id] || null)
  })

  const batchRunningOp = computed(() => {
    const id = workbench.currentVariantId
    if (id == null) return ''
    const serverRunning = ((pipelineByVariant[id] && pipelineByVariant[id].steps) || [])
      .find(s => s.status === 'running')
    if (serverRunning) return serverRunning.id
    const statuses = statusByVariant[id] || {}
    const running = WF.find(s => statuses[s.id] === 'running' || statuses[s.id] === 'submitted')
    return running ? running.id : ''
  })

  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

  if (getCurrentInstance()) {
    onUnmounted(() => {
      unmounted = true
      for (const k of Object.keys(pollTokens)) pollTokens[k] += 1
    })
  }

  function statusFor(variantId, stepId) {
    if (variantId == null) return 'idle'
    return (statusByVariant[variantId] && statusByVariant[variantId][stepId]) || 'idle'
  }

  function setStatus(variantId, stepId, status) {
    if (variantId == null) return
    if (!statusByVariant[variantId]) statusByVariant[variantId] = {}
    statusByVariant[variantId][stepId] = status
  }

  function currentStepStatus(stepId) {
    const server = serverStepFor(stepId)
    if (server && server.status === 'running') return 'running'
    if (server && server.status === 'failed') return 'failed'
    if (server && server.status === 'done') return 'done'
    if (server && server.status === 'skipped') return 'done'
    if (server && server.status === 'blocked') return 'locked'
    return statusFor(workbench.currentVariantId, stepId)
  }

  function serverStepFor(stepId, variantId = workbench.currentVariantId) {
    const backendId = PIPELINE_STEP[stepId] || stepId
    const p = variantId == null ? null : pipelineByVariant[variantId]
    return ((p && p.steps) || []).find(s => s.id === backendId) || null
  }

  function runningFor(variantId) {
    const statuses = statusByVariant[variantId] || {}
    return WF.some(s => statuses[s.id] === 'running' || statuses[s.id] === 'submitted')
  }

  async function loadPipeline(variantId = workbench.currentVariantId) {
    if (variantId == null) return null
    try {
      const data = await api.draftPipeline(variantId)
      pipelineByVariant[variantId] = data
      return data
    } catch (err) {
      if (err && err.status === 404) pipelineByVariant[variantId] = null
      return null
    }
  }

  function isUnfinished(job) {
    const status = String((job && job.status) || '').toLowerCase()
    return !!status && status !== 'done' && status !== 'failed'
  }

  async function pollTextJob(variantId, jobId) {
    if (variantId == null) return
    const tokenKey = `${variantId}:content`
    const token = (pollTokens[tokenKey] || 0) + 1
    pollTokens[tokenKey] = token
    while (!unmounted && pollTokens[tokenKey] === token) {
      let job
      try {
        job = jobId ? await api.getTextJob(jobId) : await api.getLatestTextJob(variantId)
      } catch (err) {
        // 404：数据库里找不到该 job（可能已清库或 id 过期），直接退出轮询
        // 其他网络错误也退出，防止无限重试
        if (err && err.status === 404) {
          jobByVariant[variantId] = null
          if (workbench && workbench.setVariantTask) workbench.setVariantTask(variantId, null)
        }
        break
      }
      jobByVariant[variantId] = job
      if (workbench && workbench.setVariantTask) workbench.setVariantTask(variantId, job)
      const status = String((job && job.status) || '').toLowerCase()
      await loadPipeline(variantId)
      if (status === 'done') {
        await workbench.reload()
        if (store && store.loadDrafts) await store.loadDrafts()
        await loadPipeline(variantId)
        break
      }
      if (status === 'failed') break
      await sleep(2500)
    }
  }

  async function syncLatestTextJob(variantId) {
    if (variantId == null || runningFor(variantId)) return
    let job
    try {
      job = workbench && workbench.checkVariantTask
        ? await workbench.checkVariantTask(variantId)
        : await api.getLatestTextJob(variantId)
    } catch (err) {
      // 404：该 draft 从未提交过 text job，正常情况，静默退出
      if (err && err.status === 404) return
      // 其他错误也不要阻断 UI
      return
    }
    jobByVariant[variantId] = job || null
    const status = String((job && job.status) || '').toLowerCase()
    if (status === 'done') {
      await workbench.reload()
      if (store && store.loadDrafts) await store.loadDrafts()
      await loadPipeline(variantId)
      return
    }
    if (!isUnfinished(job)) return
    setStatus(variantId, 'content', 'submitted')
    try {
      await pollTextJob(variantId, job && (job.job_id || job.id))
    } finally {
      setStatus(variantId, 'content', 'idle')
    }
  }

  if (getCurrentInstance()) {
    watch(() => workbench.currentVariantId, (id) => {
      loadPipeline(id)
      syncLatestTextJob(id)
    }, { immediate: true })
  }

  function wfDepOk(stepId, variant) {
    const step = WF.find(s => s.id === stepId)
    if (!step) return false
    const flags = (variant && variant.steps) || {}
    return step.dep.every(d => flags[d])
  }

  function stepLocked(stepId) {
    const server = serverStepFor(stepId)
    if (server) {
      if (server.status === 'blocked' || server.status === 'running') return true
      return false
    }
    const step = WF.find(s => s.id === stepId)
    if (!step || !step.dep.length) return false
    const v = workbench.currentVariant
    if (!v) return false
    return !wfDepOk(stepId, v)
  }

  async function runStep(stepId) {
    const backendStep = PIPELINE_STEP[stepId]
    if (backendStep) {
      if (stepLocked(stepId)) return
      await retryPipelineStep(backendStep)
      return
    }
    if (!RUN_ONE[stepId]) return
    if (stepLocked(stepId)) return
    const id = workbench.currentVariantId
    if (id == null) return
    if (runningFor(id)) return
    setStatus(id, stepId, 'running')
    try {
      const result = await RUN_ONE[stepId](id)
      if (stepId === 'content') {
        setStatus(id, stepId, 'submitted')
        jobByVariant[id] = result || null
        if (workbench && workbench.setVariantTask) workbench.setVariantTask(id, result || null)
        await loadPipeline(id)
        const jobId = result && (result.job_id || result.id)
        await pollTextJob(id, jobId)
        return
      }
      await workbench.reload()
      if (store && store.loadDrafts) await store.loadDrafts()
      await loadPipeline(id)
    } finally {
      setStatus(id, stepId, 'idle')
    }
  }

  async function refreshAfterPipelineAction(variantId) {
    if (workbench && workbench.reload) await workbench.reload()
    if (store && store.loadDrafts) await store.loadDrafts()
    await loadPipeline(variantId)
  }

  async function retryPipelineStep(stepId) {
    const id = workbench.currentVariantId
    if (id == null) return
    const result = await api.draftPipelineRetry(id, stepId)
    const jobId = result && (result.job_id || result.id)
    if (stepId === 'ai_text' && jobId) {
      jobByVariant[id] = result || null
      await pollTextJob(id, jobId)
      return
    }
    await refreshAfterPipelineAction(id)
  }

  async function skipPipelineStep(stepId, reason = '') {
    const id = workbench.currentVariantId
    if (id == null) return
    await api.draftPipelineSkip(id, stepId, reason)
    await refreshAfterPipelineAction(id)
  }

  async function cancelPipelineStep(stepId, reason = '') {
    const id = workbench.currentVariantId
    if (id == null) return
    await api.draftPipelineCancel(id, stepId, reason)
    await loadPipeline(id)
  }

  async function runNextPipelineStep() {
    const p = pipeline.value
    const next = p && p.next
    const stepId = next && next.step_id
    if (!stepId) return
    if (next.action === 'run' || next.action === 'retry') {
      await retryPipelineStep(stepId)
    }
  }

  return {
    WF, stepStatus, batchRunningOp, textJob, pipeline, loadPipeline,
    wfDepOk, stepLocked, runStep, syncLatestTextJob,
    retryPipelineStep, skipPipelineStep, cancelPipelineStep, runNextPipelineStep,
  }
}
