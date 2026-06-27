import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  requiredCheck: vi.fn().mockResolvedValue({
    aspects: [{ id: 10, name: '颜色', is_required: true, is_aspect: true, is_collection: false, dictionary_id: 5 }],
    required: [{ id: 20, name: '材料', is_required: true, is_aspect: false, is_collection: false, dictionary_id: 7 }],
    optional: [{ id: 30, name: '备注', is_required: false, is_aspect: false, is_collection: false, dictionary_id: 0 }],
    missing: [{ id: 20, name: '材料' }], errors: [],
  }),
  attributeOptions: vi.fn().mockResolvedValue({ values: [{ id: 101, value: '红' }], oversized: false }),
  attributeValues: vi.fn().mockResolvedValue({ result: [{ id: 999, value: '搜到的' }] }),
  aiFillAttributes: vi.fn().mockResolvedValue({ draft: { id: 7, category_id: '1', type_id: '2',
    attributes: [{ id: 20, values: [{ dictionary_value_id: 701, value: '棉' }] }] }, mapped_count: 1 }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
} }))
import { api } from '../api.js'
import { useAttributes } from './useAttributes.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks(); vi.useFakeTimers() })

function mkDraft(attrs = []) {
  return ref({ id: 7, category_id: '1', type_id: '2', attributes: attrs })
}

describe('useAttributes', () => {
  it('从 draft.attributes 建 values + 拉 defs 分组', async () => {
    const d = mkDraft([{ id: 10, values: [{ dictionary_value_id: 101, value: '红' }] }])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(api.requiredCheck).toHaveBeenCalledWith(7, 'ZH_HANS')
    expect(a.groups.value.aspects.length).toBe(1)
    expect(a.groups.value.required.length).toBe(1)
    expect(a.values[10]).toEqual([{ dictionary_value_id: 101, value: '红' }])
  })

  it('missingIds：required 空算缺、填了不缺', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(a.missingIds.value).toContain(20)        // 材料(required) 未填
    a.setValue(20, [{ dictionary_value_id: 701, value: '棉' }])
    await nextTick()
    expect(a.missingIds.value).not.toContain(20)
  })

  it('setValue 后防抖 patchDraft({attributes})', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    a.setValue(20, [{ dictionary_value_id: 701, value: '棉' }])
    vi.advanceTimersByTime(350)
    await Promise.resolve()
    expect(api.patchDraft).toHaveBeenCalled()
    const patch = api.patchDraft.mock.calls[0][1]
    expect(patch.attributes).toEqual([{ id: 20, values: [{ dictionary_value_id: 701, value: '棉' }] }])
  })

  it('aiFill 调 api 并用返回 draft 重建 values', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    await a.aiFill()
    expect(api.aiFillAttributes).toHaveBeenCalledWith(7)
    expect(a.values[20]).toEqual([{ dictionary_value_id: 701, value: '棉' }])
  })

  it('ensureOptions 拉全量选项；oversized 标记', async () => {
    const d = mkDraft([])
    const a = useAttributes(d)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    await a.ensureOptions({ id: 10, dictionary_id: 5 })
    expect(api.attributeOptions).toHaveBeenCalledWith('1', '2', 10, 'ZH_HANS')
    expect(a.optionsOf(10)).toEqual([{ id: 101, value: '红' }])
  })
})
