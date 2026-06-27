import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  getDraft: vi.fn().mockResolvedValue({ id: 7, ozon_title: '杯', price: 38, stock: 5,
    category_id: '1', type_id: '2', source_raw: {}, attributes: [] }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7, ozon_title: '新杯' } }),
} }))
import { api } from '../api.js'
import { useDraftForm } from './useDraftForm.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('useDraftForm', () => {
  it('draftId 变 → 拉草稿填 form', async () => {
    const id = ref(7)
    const fm = useDraftForm(id)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(api.getDraft).toHaveBeenCalledWith(7)
    expect(fm.form.ozon_title).toBe('杯')
    expect(fm.form.price).toBe(38)
  })
  it('save 调 patchDraft(collectPatch)', async () => {
    const id = ref(7); const fm = useDraftForm(id)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    fm.form.ozon_title = '新杯'
    await fm.save()
    expect(api.patchDraft).toHaveBeenCalled()
    const patch = api.patchDraft.mock.calls[0][1]
    expect(patch.ozon_title).toBe('新杯')
    expect(patch.category_id).toBe('1')
  })
})
