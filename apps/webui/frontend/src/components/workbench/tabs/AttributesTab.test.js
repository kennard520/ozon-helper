import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
vi.mock('../../../api.js', () => ({ api: {
  requiredCheck: vi.fn().mockResolvedValue({
    aspects: [{ id: 10, name: '颜色', is_required: true, is_aspect: true, dictionary_id: 5 }],
    required: [{ id: 20, name: '材料', is_required: true, is_aspect: false, dictionary_id: 7 }],
    optional: [{ id: 30, name: '备注', is_required: false, is_aspect: false, dictionary_id: 0 }],
    missing: [{ id: 20, name: '材料' }], errors: [],
  }),
  attributeOptions: vi.fn().mockResolvedValue({ values: [], oversized: false }),
  attributeValues: vi.fn().mockResolvedValue({ result: [] }),
  aiFillAttributes: vi.fn().mockResolvedValue({ draft: { id: 7, category_id: '1', type_id: '2', attributes: [] }, mapped_count: 2 }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
} }))
import { api } from '../../../api.js'
import AttributesTab from './AttributesTab.vue'
import AttrField from '../AttrField.vue'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function factory() {
  return mount(AttributesTab, {
    props: { draft: { id: 7, category_id: '1', type_id: '2', attributes: [] } },
    global: {
      stubs: {
        teleport: true,
        // Stub AttrField so ElSelect doesn't trigger recursive updates in tests
        AttrField: { name: 'AttrField', template: '<div class="attr-field-stub"></div>', props: ['def', 'modelValue', 'options', 'loading', 'oversized', 'missing'] },
      },
    },
  })
}

describe('AttributesTab', () => {
  it('渲三组 + missing banner', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await nextTick()
    expect(api.requiredCheck).toHaveBeenCalled()
    // aspects(1) + required(1) 先可见，optional 默认折叠未渲染
    // 展开 optional 使总数变 3
    const optBtn = w.findAll('button').find(b => b.text().includes('展开'))
    if (optBtn) await optBtn.trigger('click')
    await nextTick()
    // 用 component stub name 查找
    expect(w.findAllComponents({ name: 'AttrField' }).length).toBe(4)
    expect(w.text()).toContain('缺')   // missing banner 文案含「缺」
    expect(w.text()).toContain('简介')
    expect(w.text()).toContain('标签')
    expect(w.text()).toContain('原产国 / 制造国')
  })

  it('tab 内不再放 AI 填充/保存按钮（操作在顶部流程区，改动自动保存）', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    const labels = w.findAll('button').map((b) => b.text())
    expect(labels.some((t) => t.includes('AI 填充'))).toBe(false)
    expect(labels.some((t) => t === '保存')).toBe(false)
  })
})
