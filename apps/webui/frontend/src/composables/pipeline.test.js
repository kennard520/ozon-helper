import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: 'G', count: 2,
    variants: [{ id: 1, steps: {}, done: 0 }, { id: 2, steps: {}, done: 0 }] }),
  draftPipeline: vi.fn().mockResolvedValue({ steps: [], next: { action: 'done', step_id: '', reason: '' } }),
  draftPipelineRetry: vi.fn().mockResolvedValue({ job_id: 10, status: 'queued' }),
  draftPipelineSkip: vi.fn().mockResolvedValue({}),
  draftPipelineCancel: vi.fn().mockResolvedValue({}),
  submitTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'queued' }),
  getTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'done', current_step: 'attrs' }),
  getLatestTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'done', current_step: 'attrs' }),
  designImagePlan: vi.fn().mockResolvedValue({}),
  imagePlan: vi.fn().mockResolvedValue({}),
  makeRichContent: vi.fn().mockResolvedValue({}),
} }))

import { api } from '../api.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import { usePipeline } from './usePipeline.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('usePipeline', () => {
  it('runStep(content) submits ai_text through backend pipeline and polls', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.variants[1].steps = { understand: true, category: true }
    const reload = vi.spyOn(wb, 'reload')
    const store = { loadDrafts: vi.fn() }
    const pipe = usePipeline(wb, store)

    await pipe.runStep('content')

    expect(api.draftPipelineRetry).toHaveBeenCalledWith(2, 'ai_text')
    expect(api.getTextJob).toHaveBeenCalledWith(10)
    expect(reload).toHaveBeenCalled()
    expect(store.loadDrafts).toHaveBeenCalled()
    expect(pipe.textJob.value.status).toBe('done')
  })

  it('runStep does nothing without current variant', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = null
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('content')
    expect(api.draftPipelineRetry).not.toHaveBeenCalled()
  })

  it('wfDepOk checks local workflow dependencies', () => {
    const wb = useWorkbenchStore()
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    expect(pipe.wfDepOk('content', { steps: { category: false } })).toBe(false)
    expect(pipe.wfDepOk('content', { steps: { category: true } })).toBe(true)
    expect(pipe.wfDepOk('images', { steps: { content: false } })).toBe(false)
    expect(pipe.wfDepOk('images', { steps: { content: true } })).toBe(true)
    expect(pipe.wfDepOk('understand', { steps: {} })).toBe(true)
  })

  it('wfDepOk does not require understand before category for WB drafts', () => {
    const wb = useWorkbenchStore()
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    expect(pipe.wfDepOk('category', { source_platform: 'wb', steps: { understand: false } })).toBe(true)
    expect(pipe.wfDepOk('category', { source_platform: '1688', steps: { understand: false } })).toBe(false)
  })

  it('stepLocked follows the current variant only', () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 1, steps: { category: false, content: false } }, { id: 2, steps: { category: true, content: true } }]
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    wb.currentVariantId = 1
    expect(pipe.stepLocked('content')).toBe(true)
    expect(pipe.stepLocked('images')).toBe(true)
    wb.currentVariantId = 2
    expect(pipe.stepLocked('content')).toBe(false)
    expect(pipe.stepLocked('images')).toBe(false)
    wb.currentVariantId = null
    expect(pipe.stepLocked('images')).toBe(false)
  })

  it('stepLocked allows WB category before understand', () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 1, source_platform: 'wb', steps: { understand: false, category: false } }]
    wb.currentVariantId = 1
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    expect(pipe.stepLocked('category')).toBe(false)
  })

  it('stepLocked treats backend skipped understand as satisfied for category', async () => {
    api.draftPipeline.mockResolvedValueOnce({
      steps: [
        { id: 'understand', status: 'skipped' },
        { id: 'category_recognition', status: 'pending' },
      ],
      next: { action: 'run', step_id: 'category_recognition' },
    })
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 1, steps: { understand: false, category: false } }]
    wb.currentVariantId = 1
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.loadPipeline(1)

    expect(pipe.stepLocked('category')).toBe(false)
    await pipe.runStep('category')
    expect(api.draftPipelineRetry).toHaveBeenCalledWith(1, 'category_recognition')
  })

  it('runStep(category) submits category_recognition through backend pipeline', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.variants[1].steps = { understand: true }
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })

    await pipe.runStep('category')

    expect(api.draftPipelineRetry).toHaveBeenCalledWith(2, 'category_recognition')
  })

  it('runStep(category) shows running and polls pipeline before retry returns', async () => {
    vi.useFakeTimers()
    let resolveRetry
    api.draftPipelineRetry.mockImplementationOnce(() => new Promise(resolve => {
      resolveRetry = resolve
    }))
    api.draftPipeline.mockResolvedValue({ steps: [{ id: 'category_recognition', status: 'running' }], next: { action: 'wait', step_id: 'category_recognition' } })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.variants[1].steps = { understand: true }
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })

    const pending = pipe.runStep('category')
    await Promise.resolve()

    expect(pipe.stepStatus.category).toBe('running')
    expect(pipe.batchRunningOp.value).toBe('category')
    expect(api.draftPipelineRetry).toHaveBeenCalledWith(2, 'category_recognition')

    await vi.advanceTimersByTimeAsync(700)

    expect(api.draftPipeline).toHaveBeenCalledWith(2)
    resolveRetry({ ok: true })
    await pending
  })

  it('runStep(category) shows local running even when previous pipeline snapshot is done', async () => {
    vi.useFakeTimers()
    let resolveRetry
    api.draftPipelineRetry.mockImplementationOnce(() => new Promise(resolve => {
      resolveRetry = resolve
    }))
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.variants[1].steps = { understand: true, category: true }
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    api.draftPipeline.mockResolvedValueOnce({
      steps: [{ id: 'category_recognition', status: 'done' }],
      next: { action: 'done', step_id: '' },
    })
    await pipe.loadPipeline(2)

    const pending = pipe.runStep('category')
    await Promise.resolve()

    expect(pipe.stepStatus.category).toBe('running')
    expect(pipe.batchRunningOp.value).toBe('category')

    resolveRetry({ ok: true })
    await pending
  })

  it('runStep(publish) submits publish through backend pipeline', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.variants[0].steps = { content: true, images: true, rich: true }
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('publish')
    expect(api.draftPipelineRetry).toHaveBeenCalledWith(1, 'publish')
  })

  it('runNextPipelineStep follows backend next action', async () => {
    api.draftPipeline.mockResolvedValueOnce({
      steps: [],
      next: { action: 'run', step_id: 'publish', reason: 'ready' },
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.loadPipeline(1)
    await pipe.runNextPipelineStep()
    expect(api.draftPipelineRetry).toHaveBeenCalledWith(1, 'publish')
  })

  it('runStep(content) exits polling after 404', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.variants[1].steps = { understand: true, category: true }
    api.draftPipelineRetry.mockResolvedValue({ job_id: 99, status: 'queued' })
    api.getTextJob.mockRejectedValue(Object.assign(new Error('text_job 99 not found'), { status: 404 }))
    const store = { loadDrafts: vi.fn() }
    const pipe = usePipeline(wb, store)

    await pipe.runStep('content')

    expect(api.getTextJob).toHaveBeenCalledTimes(1)
    expect(api.getTextJob).toHaveBeenCalledWith(99)
    expect(pipe.textJob.value).toBeNull()
    expect(store.loadDrafts).not.toHaveBeenCalled()
  })

  it('syncLatestTextJob refreshes stale local running cache from backend', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.setVariantTask(2, { job_id: 10, status: 'running' })
    api.getLatestTextJob.mockResolvedValueOnce({ job_id: 10, status: 'done', current_step: 'attrs' })
    const reload = vi.spyOn(wb, 'reload')
    const store = { loadDrafts: vi.fn() }
    const pipe = usePipeline(wb, store)

    await pipe.syncLatestTextJob(2)

    expect(api.getLatestTextJob).toHaveBeenCalledWith(2)
    expect(wb.variantTask(2).status).toBe('done')
    expect(reload).toHaveBeenCalled()
    expect(store.loadDrafts).toHaveBeenCalled()
  })

  it('syncLatestTextJob treats cancelled jobs as terminal and does not poll', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    wb.setVariantTask(2, { job_id: 10, status: 'running' })
    api.getLatestTextJob.mockResolvedValueOnce({
      job_id: 10,
      status: 'cancelled',
      current_step: 'understand',
      error: 'user stopped',
    })
    const store = { loadDrafts: vi.fn() }
    const pipe = usePipeline(wb, store)

    await pipe.syncLatestTextJob(2)

    expect(api.getTextJob).not.toHaveBeenCalled()
    expect(wb.variantTask(2).status).toBe('cancelled')
    expect(pipe.textJob.value.status).toBe('cancelled')
    expect(store.loadDrafts).not.toHaveBeenCalled()
  })
})
