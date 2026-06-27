import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: { variantGroup: vi.fn() } }))
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
})
