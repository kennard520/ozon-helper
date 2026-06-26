import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DraftDetail from '../src/components/DraftDetail.vue'
import { api } from '../src/api.js'

const draft = {
  id: 1, source_platform: '1688', source_title: '中文标题', ozon_title: '',
  category_id: '', type_id: '', price: '', stock: 0, images: [],
  weight_g: 0, length_mm: 0, width_mm: 0, height_mm: 0,
  supplier: '', offer_id: '', attributes: [], validation_errors: [],
}
beforeEach(() => setActivePinia(createPinia()))

describe('DraftDetail', () => {
  it('保存收集表单字段 PATCH 出去', async () => {
    const spy = vi.spyOn(api, 'patchDraft').mockResolvedValue({ draft: { ...draft, ozon_title: 'Коробка' } })
    vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], missing: [], errors: [] })
    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    w.vm.form.ozon_title = 'Коробка'
    w.vm.form.supplier = '四川某厂'
    await w.vm.save()
    const [id, patch] = spy.mock.calls[0]
    expect(id).toBe(1)
    expect(patch.ozon_title).toBe('Коробка')
    expect(patch.supplier).toBe('四川某厂')
  })

  it('images textarea 换行拆成数组', async () => {
    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    w.vm.imagesText = 'https://a.jpg\nhttps://b.jpg'
    expect(w.vm.collectPatch().images).toEqual(['https://a.jpg', 'https://b.jpg'])
  })

  it('attributes 为字典 {} 时不崩（后端默认值），归一成数组', async () => {
    // 后端 attributes_json 默认 {}（store.py loads_json 默认值），不是数组；
    // initFromDraft 的 for...of 旧实现会抛 "object is not iterable"。
    vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], missing: [], errors: [] })
    const dictDraft = { ...draft, attributes: {} }
    let w
    expect(() => {
      w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft: dictDraft } })
    }).not.toThrow()
    expect(w.vm.attributesText).toBe('[]')
    expect(w.vm.collectPatch().attributes).toEqual([])
  })

  it('空的非必填属性默认隐藏，展开未填项后才显示', async () => {
    vi.spyOn(api, 'requiredCheck').mockResolvedValue({
      required: [],
      missing: [],
      optional: [
        { id: 4191, name: '简介', dictionary_id: 0 },
        { id: 23171, name: '主题标签', dictionary_id: 0 },
        { id: 9048, name: '型号名称', dictionary_id: 0 },
      ],
    })
    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...draft, category_id: '1', type_id: '2' } },
    })
    await flushPromises()
    expect(w.text()).toContain('简介')        // 外置的简介行始终在
    expect(w.text()).toContain('主题标签')
    expect(w.text()).toContain('可选（0/1 已填）')
    // showOptional is true by default -> shows the empty optional attribute (型号名称)
    expect(w.findAll('.optional-list .req-attr-item')).toHaveLength(1)
    expect(w.findAll('.optional-list .req-attr-item').at(0).text()).toContain('型号名称')
    // Set to false to hide empty optional attributes
    w.vm.showOptional = false
    await flushPromises()
    expect(w.findAll('.optional-list .req-attr-item')).toHaveLength(0)
  })

  it('外部主题标签保存为 Ozon 属性 23171', () => {
    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    w.vm.form.tags = 'сумка, #кожа\nлетняя сумка'
    const patch = w.vm.collectPatch()
    const tagAttr = patch.attributes.find((a) => Number(a.id) === 23171)
    expect(tagAttr.values[0].value).toBe('#сумка #кожа #летняя_сумка')
    expect(patch.source_raw.tags).toEqual(['сумка', '#кожа', 'летняя сумка'])
  })
})
