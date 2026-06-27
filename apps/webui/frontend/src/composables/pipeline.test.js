import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: 'G', count: 2,
    variants: [{ id: 1, steps: {}, done: 0 }, { id: 2, steps: {}, done: 0 }] }),
  understand: vi.fn().mockResolvedValue({}), recognizeCategory: vi.fn().mockResolvedValue({}),
  aiGenerate: vi.fn().mockResolvedValue({}), aiProposalApply: vi.fn().mockResolvedValue({}),
  autoMap: vi.fn().mockResolvedValue({}), designImagePlan: vi.fn().mockResolvedValue({}),
  imagePlan: vi.fn().mockResolvedValue({}), makeRichContent: vi.fn().mockResolvedValue({}),
} }))
import { api } from '../api.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import { usePipeline } from './usePipeline.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('usePipeline', () => {
  it('runStep(understand) 对选中变体各调一次 + reload', async () => {
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    const reload = vi.spyOn(wb, 'reload')
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('understand')
    expect(api.understand).toHaveBeenCalledTimes(2)
    expect(reload).toHaveBeenCalled()
    expect(pipe.stepStatus.understand).toBe('idle')
  })
  it('runStep(copy) 每变体 aiGenerate + aiProposalApply', async () => {
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('copy')
    expect(api.aiGenerate).toHaveBeenCalledTimes(2)
    expect(api.aiProposalApply).toHaveBeenCalledTimes(2)
  })
  it('wfDepOk:attrs 依赖 category', () => {
    const wb = useWorkbenchStore()
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    expect(pipe.wfDepOk('attrs', { steps: { category: false } })).toBe(false)
    expect(pipe.wfDepOk('attrs', { steps: { category: true } })).toBe(true)
    expect(pipe.wfDepOk('understand', { steps: {} })).toBe(true)
  })
  it('runStep(publish) 不调任何 RUN_ONE(发布另走)', async () => {
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    const pipe = usePipeline(wb, { loadDrafts: vi.fn() })
    await pipe.runStep('publish')
    expect(api.understand).not.toHaveBeenCalled()
  })
})
