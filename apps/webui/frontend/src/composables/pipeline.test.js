import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: 'G', count: 2,
    variants: [{ id: 1, steps: {}, done: 0 }, { id: 2, steps: {}, done: 0 }] }),
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
  it('runStep(content) 提交当前变体 job 并轮询到完成后刷新', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    const reload = vi.spyOn(wb, 'reload')
    const store = { loadDrafts: vi.fn() }
    const pipe = usePipeline(wb, store)

    await pipe.runStep('content')

    expect(api.submitTextJob).toHaveBeenCalledWith(2)
    expect(api.getTextJob).toHaveBeenCalledWith(10)
    expect(reload).toHaveBeenCalled()
    expect(store.loadDrafts).toHaveBeenCalled()
    expect(pipe.textJob.value.status).toBe('done')
    expect(pipe.stepStatus.content).toBe('idle')
  })

  it('runStep: 无当前变体则不调 api', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = null
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('content')
    expect(api.submitTextJob).not.toHaveBeenCalled()
  })

  it('wfDepOk: images 依赖 content', () => {
    const wb = useWorkbenchStore()
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    expect(pipe.wfDepOk('images', { steps: { content: false } })).toBe(false)
    expect(pipe.wfDepOk('images', { steps: { content: true } })).toBe(true)
    expect(pipe.wfDepOk('content', { steps: {} })).toBe(true)
  })

  it('stepLocked: 只看当前变体的前置步骤', () => {
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

  it('runStep(publish) 不调任何 RUN_ONE', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('publish')
    expect(api.submitTextJob).not.toHaveBeenCalled()
  })

  it('runStep(content) keeps running state isolated per variant', async () => {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    let releaseFirstPoll
    api.getTextJob.mockImplementationOnce(() => new Promise(resolve => {
      releaseFirstPoll = () => resolve({ job_id: 10, status: 'done', current_step: 'attrs' })
    }))
    api.getTextJob.mockResolvedValue({ job_id: 11, status: 'done', current_step: 'attrs' })

    wb.currentVariantId = 1
    const firstRun = pipe.runStep('content')
    await Promise.resolve()
    await Promise.resolve()
    expect(['running', 'submitted']).toContain(pipe.stepStatus.content)

    wb.currentVariantId = 2
    expect(pipe.stepStatus.content).toBe('idle')
    await pipe.runStep('content')

    expect(api.submitTextJob).toHaveBeenNthCalledWith(1, 1)
    expect(api.submitTextJob).toHaveBeenNthCalledWith(2, 2)
    releaseFirstPoll()
    await firstRun
  it('runStep(content) 遇到 404 时退出轮询不重试', async () =\u003e {
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.currentVariantId = 2
    // submit 成功，但 poll 时 job_id 在数据库不存在（404）
    api.submitTextJob.mockResolvedValue({ job_id: 99, status: 'queued' })
    const notFound = Object.assign(new Error('text_job 99 not found'), { status: 404 })
    api.getTextJob.mockRejectedValue(notFound)
    const store = { loadDrafts: vi.fn() }
    const pipe = usePipeline(wb, store)

    await pipe.runStep('content')

    // getTextJob 应被调用一次（404 后退出，不重试）
    expect(api.getTextJob).toHaveBeenCalledTimes(1)
    expect(api.getTextJob).toHaveBeenCalledWith(99)
    // 状态恢复 idle，job 置 null
    expect(pipe.stepStatus.content).toBe('idle')
    expect(pipe.textJob.value).toBeNull()
    // reload 不应该被调用（任务没完成）
    expect(store.loadDrafts).not.toHaveBeenCalled()
  })
})
