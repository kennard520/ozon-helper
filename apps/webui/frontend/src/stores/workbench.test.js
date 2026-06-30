import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn(),
  getLatestTextJob: vi.fn().mockResolvedValue(null),
} }))
import { api } from '../api.js'
import { useWorkbenchStore } from './workbench.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('workbench store', () => {
  it('loadForDraft 填变体 + 默认全选 + 当前变体', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2,
      variants: [{ id: 1, spec: '雾灰·350ml', price: 1190, status: 'ready', image: 'a.jpg', current: true },
                 { id: 2, spec: '雾灰·500ml', price: 1290, status: 'ready', image: 'b.jpg', current: false }] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    expect(wb.groupKey).toBe('G')
    expect(wb.variants.length).toBe(2)
    expect(wb.currentVariantId).toBe(1)
    expect([...wb.selectedVariantIds].sort()).toEqual([1, 2])
    expect(wb.currentVariant.spec).toBe('雾灰·350ml')
  })
  it('单草稿无组退化', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: '', count: 0, variants: [] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(5)
    expect(wb.groupKey).toBe('')
    expect(wb.currentVariantId).toBe(5)
  })
  it('toggle/selectAll/clear/invert', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(1)
    wb.clearSelection(); expect(wb.selectedVariantIds.size).toBe(0)
    wb.toggleVariant(2); expect([...wb.selectedVariantIds]).toEqual([2])
    wb.invertSelection(); expect([...wb.selectedVariantIds].sort()).toEqual([1])
    wb.selectAll(); expect(wb.selectedVariantIds.size).toBe(2)
  })
  it('currentVariantIndex 给出当前变体下标', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }] })
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    expect(wb.currentVariantIndex).toBe(0)
    wb.setCurrentVariant(2)
    expect(wb.currentVariantIndex).toBe(1)
  })
  it('next/prevVariant 在 variants 里循环切当前变体', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 3,
      variants: [{ id: 1, spec: 'a' }, { id: 2, spec: 'b' }, { id: 3, spec: 'c' }] })
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    expect(wb.currentVariantId).toBe(1)
    wb.nextVariant(); expect(wb.currentVariantId).toBe(2)
    wb.nextVariant(); expect(wb.currentVariantId).toBe(3)
    wb.nextVariant(); expect(wb.currentVariantId).toBe(1)   // 循环回头
    wb.prevVariant(); expect(wb.currentVariantId).toBe(3)   // 循环到尾
    wb.prevVariant(); expect(wb.currentVariantId).toBe(2)
  })
  it('loadForDraft:传入草稿不在组里时默认聚焦第一个变体', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2,
      variants: [{ id: 10, spec: 'a' }, { id: 20, spec: 'b' }] })
    const wb = useWorkbenchStore()
    await wb.loadForDraft(999)   // 999 不在变体组里
    expect(wb.currentVariantId).toBe(10)
  })
  it('翻页对空 variants 安全(不抛错)', () => {
    const wb = useWorkbenchStore()
    expect(() => { wb.nextVariant(); wb.prevVariant() }).not.toThrow()
    expect(wb.currentVariantId).toBe(null)
  })

  it('stepProgress 聚合选中变体某步完成数', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2, variants: [
      { id: 1, steps: { copy: true, images: false }, done: 1 },
      { id: 2, steps: { copy: true, images: true }, done: 2 }] })
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    expect(wb.stepProgress('copy')).toEqual({ done: 2, total: 2 })
    expect(wb.stepProgress('images')).toEqual({ done: 1, total: 2 })
    wb.clearSelection(); wb.toggleVariant(1)
    expect(wb.stepProgress('images')).toEqual({ done: 0, total: 1 })
  })

  it('currentStepDone 按当前查看变体逐步判完成', async () => {
    api.variantGroup.mockResolvedValue({ ok: true, group: 'G', count: 2, variants: [
      { id: 1, steps: { understand: true, category: false }, done: 1 },
      { id: 2, steps: { understand: false, category: true }, done: 1 }] })
    const wb = useWorkbenchStore(); await wb.loadForDraft(1)
    expect(wb.currentStepDone('understand')).toBe(true)
    expect(wb.currentStepDone('category')).toBe(false)
    expect(wb.currentStepDone('missing')).toBe(false)   // 不存在的步 → false
    wb.setCurrentVariant(2)
    expect(wb.currentStepDone('understand')).toBe(false)
    expect(wb.currentStepDone('category')).toBe(true)
  })

  it('currentStepDone:无当前变体(null)时恒为 false', () => {
    const wb = useWorkbenchStore()
    expect(wb.currentVariant).toBe(null)
    expect(wb.currentStepDone('understand')).toBe(false)
  })
})

describe('workbench task cache', () => {
  it('checkVariantTask 缓存当前变体未完成任务', async () => {
    api.getLatestTextJob.mockResolvedValueOnce({ job_id: 10, status: 'running' })
    const wb = useWorkbenchStore()
    const job = await wb.checkVariantTask(7)
    expect(job.status).toBe('running')
    expect(wb.variantTask(7).job_id).toBe(10)
    expect(wb.variantTaskRunning(7)).toBe(true)
    expect(wb.variantTaskChecking(7)).toBe(false)
    wb.setVariantTask(7, { job_id: 10, status: 'done' })
    expect(wb.variantTaskRunning(7)).toBe(false)
  })
})
