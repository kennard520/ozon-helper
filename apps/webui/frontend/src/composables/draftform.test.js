import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  getDraft: vi.fn().mockResolvedValue({ draft: { id: 7, ozon_title: '杯', price: 38, stock: 5,
    category_id: '1', type_id: '2', source_raw: {}, attributes: [] } }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7, ozon_title: '新杯' } }),
} }))
import { api } from '../api.js'
import { useDraftForm } from './useDraftForm.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

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
  it('ignores an older detail response after switching to another variant', async () => {
    const oldReq = deferred()
    const newReq = deferred()
    api.getDraft.mockImplementation((draftId) => (
      Number(draftId) === 1428 ? oldReq.promise : newReq.promise
    ))
    const id = ref(1428)
    const fm = useDraftForm(id)
    await nextTick()

    id.value = 1417
    await nextTick()
    await vi.waitFor(() => expect(api.getDraft).toHaveBeenCalledWith(1417))

    newReq.resolve({ draft: { id: 1417, ozon_title: 'black title', price: 1, stock: 1, category_id: '1', type_id: '2', source_raw: {}, attributes: [] } })
    await vi.waitFor(() => expect(fm.draft.value && fm.draft.value.id).toBe(1417))
    expect(fm.form.ozon_title).toBe('black title')

    oldReq.resolve({ draft: { id: 1428, ozon_title: 'yellow title', price: 2, stock: 1, category_id: '1', type_id: '2', source_raw: {}, attributes: [] } })
    await oldReq.promise
    await Promise.resolve()
    await Promise.resolve()

    expect(fm.draft.value.id).toBe(1417)
    expect(fm.form.ozon_title).toBe('black title')
  })
})
