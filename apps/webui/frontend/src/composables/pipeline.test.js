import { describe, it, expect, vi, beforeEach } from 'vitest'
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

describe('usePipeline', () => {
  it('runStep(content) submits ai_text through backend pipeline and polls', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
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
    expect(pipe.wfDepOk('images', { steps: { content: false } })).toBe(false)
    expect(pipe.wfDepOk('images', { steps: { content: true } })).toBe(true)
    expect(pipe.wfDepOk('content', { steps: {} })).toBe(true)
  })

  it('stepLocked follows the current variant only', () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 1, steps: { content: false } }, { id: 2, steps: { content: true } }]
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    wb.currentVariantId = 1
    expect(pipe.stepLocked('images')).toBe(true)
    wb.currentVariantId = 2
    expect(pipe.stepLocked('images')).toBe(false)
    expect(pipe.stepLocked('content')).toBe(false)
    wb.currentVariantId = null
    expect(pipe.stepLocked('images')).toBe(false)
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
})
