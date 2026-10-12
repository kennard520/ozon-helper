import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn(),
  getLatestTextJob: vi.fn().mockResolvedValue(null),
} }))

import { api } from '../api.js'
import { useWorkbenchStore } from './workbench.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('workbench store', () => {
  it('loadForDraft sets variants and current variant', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [
        { id: 1, spec: '闆剧伆路350ml', price: 1190, status: 'ready', image: 'a.jpg', current: true },
        { id: 2, spec: '闆剧伆路500ml', price: 1290, status: 'ready', image: 'b.jpg', current: false },
      ],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.groupKey).toBe('G')
    expect(wb.variants.length).toBe(2)
    expect(wb.currentVariantId).toBe(1)
    expect([...wb.selectedVariantIds].sort()).toEqual([1, 2])
    expect(wb.currentVariant.spec).toBe('闆剧伆路350ml')
  })

  it('loadForDraft refreshes the whole variant group task cache', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [
        { id: 1, spec: 'a' },
        { id: 2, spec: 'b' },
      ],
    })
    const wb = useWorkbenchStore()
    wb.setVariantTask(1, { job_id: 10, status: 'running' })
    await wb.loadForDraft(1)
    expect(api.getLatestTextJob).toHaveBeenNthCalledWith(1, 1)
    expect(api.getLatestTextJob).toHaveBeenNthCalledWith(2, 2)
    expect(wb.variantTask(1)).toBeNull()
    expect(wb.variantTask(2)).toBeNull()
  })

  it('single draft without group still focuses itself', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: '', count: 0, variants: [] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(5)
    expect(wb.groupKey).toBe('')
    expect(wb.currentVariantId).toBe(5)
  })

  it('toggle/selectAll/clear/invert', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.clearSelection()
    expect(wb.selectedVariantIds.size).toBe(0)
    wb.toggleVariant(2)
    expect([...wb.selectedVariantIds]).toEqual([2])
    wb.invertSelection()
    expect([...wb.selectedVariantIds].sort()).toEqual([1])
    wb.selectAll()
    expect(wb.selectedVariantIds.size).toBe(2)
  })

  it('currentVariantIndex returns the current variant index', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.currentVariantIndex).toBe(0)
    wb.setCurrentVariant(2)
    expect(wb.currentVariantIndex).toBe(1)
  })

  it('next/prevVariant cycles within variants', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 3,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }, { id: 3, spec: 'c' }],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.currentVariantId).toBe(1)
    wb.nextVariant()
    expect(wb.currentVariantId).toBe(2)
    wb.nextVariant()
    expect(wb.currentVariantId).toBe(3)
    wb.nextVariant()
    expect(wb.currentVariantId).toBe(1)
    wb.prevVariant()
    expect(wb.currentVariantId).toBe(3)
    wb.prevVariant()
    expect(wb.currentVariantId).toBe(2)
  })

  it('loadForDraft prefers the passed draft when it is in the variant group', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [{ id: 10, spec: 'a' }, { id: 20, spec: 'b' }],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(999)
    expect(wb.currentVariantId).toBe(10)
  })
  it('loadForDraft 不覆盖加载中用户手动切换的当前变体', async () => {
    let resolveGroup
    api.variantGroup.mockReturnValue(new Promise((resolve) => { resolveGroup = resolve }))
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 1, spec: 'first' }, { id: 2, spec: 'second' }]
    wb.currentVariantId = 2
    const pending = wb.loadForDraft(2)

    wb.setCurrentVariant(1)
    resolveGroup({ ok: true, group: 'G', count: 2, variants: [{ id: 1, spec: 'first' }, { id: 2, spec: 'second' }] })
    await pending

    expect(wb.currentVariantId).toBe(1)
  })

  it('翻页对空 variants 安全(不抛错)', () => {
    const wb = useWorkbenchStore()
    expect(() => { wb.nextVariant(); wb.prevVariant() }).not.toThrow()
    expect(wb.currentVariantId).toBe(null)
  })

  it('stepProgress aggregates selected variant completion count', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [
        { id: 1, steps: { copy: true, images: false }, done: 1 },
        { id: 2, steps: { copy: true, images: true }, done: 2 },
      ],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.stepProgress('copy')).toEqual({ done: 2, total: 2 })
    expect(wb.stepProgress('images')).toEqual({ done: 1, total: 2 })
    wb.clearSelection()
    wb.toggleVariant(1)
    expect(wb.stepProgress('images')).toEqual({ done: 0, total: 1 })
  })

  it('currentStepDone checks the current variant only', async () => {
    api.variantGroup.mockResolvedValue({
      ok: true,
      group: 'G',
      count: 2,
      variants: [
        { id: 1, steps: { understand: true, category: false }, done: 1 },
        { id: 2, steps: { understand: false, category: true }, done: 1 },
      ],
    })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.currentStepDone('understand')).toBe(true)
    expect(wb.currentStepDone('category')).toBe(false)
    expect(wb.currentStepDone('missing')).toBe(false)
    wb.setCurrentVariant(2)
    expect(wb.currentStepDone('understand')).toBe(false)
    expect(wb.currentStepDone('category')).toBe(true)
  })

  it('currentStepDone returns false when there is no current variant', () => {
    const wb = useWorkbenchStore()
    expect(wb.currentVariant).toBe(null)
    expect(wb.currentStepDone('understand')).toBe(false)
  })

  it('loadForDraft clears stale variants while the new draft is loading', async () => {
    let resolveGroup
    api.variantGroup.mockReturnValue(new Promise((resolve) => { resolveGroup = resolve }))
    const wb = useWorkbenchStore()
    wb.groupKey = 'OLD'
    wb.variants = [{ id: 90, spec: 'old' }]
    wb.currentVariantId = 90
    wb.selectedVariantIds = new Set([90])

    const pending = wb.loadForDraft(7)

    expect(wb.loading).toBe(true)
    expect(wb.groupKey).toBe('')
    expect(wb.variants).toEqual([])
    expect(wb.currentVariantId).toBe(null)
    expect([...wb.selectedVariantIds]).toEqual([])

    resolveGroup({ ok: true, group: 'NEW', count: 1, variants: [{ id: 7, spec: 'new' }] })
    await pending
  })

  it('loadForDraft ignores stale responses when drafts are switched quickly', async () => {
    let resolveFirst
    let resolveSecond
    api.variantGroup
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve }))
    const wb = useWorkbenchStore()

    const first = wb.loadForDraft(1)
    const second = wb.loadForDraft(2)

    resolveSecond({ ok: true, group: 'SECOND', count: 1, variants: [{ id: 2, spec: 'second' }] })
    await second
    resolveFirst({ ok: true, group: 'FIRST', count: 1, variants: [{ id: 1, spec: 'first' }] })
    await first

    expect(wb.groupKey).toBe('SECOND')
    expect(wb.currentVariantId).toBe(2)
    expect(wb.variants).toEqual([{ id: 2, spec: 'second' }])
  })
})

describe('workbench task cache', () => {
  it('checkVariantTask caches unfinished task state', async () => {
    api.getLatestTextJob.mockResolvedValueOnce({ job_id: 10, status: 'running' })
    const wb = useWorkbenchStore()
    const job = await wb.checkVariantTask(7)
    expect(job.status).toBe('running')
    expect(wb.variantTask(7).job_id).toBe(10)
    expect(wb.variantTaskRunning(7)).toBe(true)
    expect(wb.variantTaskChecking(7)).toBe(false)
    wb.setVariantTask(7, { job_id: 10, status: 'done' })
    expect(wb.variantTaskRunning(7)).toBe(false)
    wb.setVariantTask(7, { job_id: 10, status: 'cancelled' })
    expect(wb.variantTaskRunning(7)).toBe(false)
  })
})
