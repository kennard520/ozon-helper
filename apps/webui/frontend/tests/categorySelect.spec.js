import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import CategorySelect from '../src/components/CategorySelect.vue'
import { api } from '../src/api.js'

const RESULTS = [
  {
    description_category_id: 1,
    type_id: 10,
    type_name: '收纳箱',
    path: '家居 / 收纳箱',
  },
  {
    description_category_id: 2,
    type_id: 20,
    type_name: '餐具',
    path: '厨房 / 餐具',
  },
]

function mountSelect(props = { modelValue: { cat: '', type: '' } }) {
  return mount(CategorySelect, {
    props,
    global: { plugins: [ElementPlus] },
  })
}

beforeEach(() => {
  vi.spyOn(api, 'categoryTree').mockResolvedValue({ tree: [] })
  vi.spyOn(api, 'categorySearch').mockResolvedValue({ results: RESULTS })
  vi.spyOn(api, 'categoryResolve').mockResolvedValue({ leaf: { path: '家居 / 收纳箱' } })
})

afterEach(() => vi.restoreAllMocks())

describe('CategorySelect remote search', () => {
  it('does not load the full category tree on mount', async () => {
    mountSelect()
    await flushPromises()

    expect(api.categoryTree).not.toHaveBeenCalled()
    expect(api.categorySearch).not.toHaveBeenCalled()
  })

  it('loads a small remote result set on search', async () => {
    const w = mountSelect()
    await w.vm.search('收纳')
    await flushPromises()

    expect(api.categorySearch).toHaveBeenCalledWith('收纳', 50)
    expect(w.vm.options).toHaveLength(2)
  })

  it('emits cat/type/path when a result is selected', async () => {
    const w = mountSelect()
    await w.vm.search('收纳')
    await flushPromises()
    await w.vm.onSelectChange('1-10')

    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual({ cat: '1', type: '10', path: '家居 / 收纳箱' })
  })

  it('clears cat/type/path', async () => {
    const w = mountSelect({ modelValue: { cat: '1', type: '10' } })
    await flushPromises()
    await w.vm.onSelectChange('')

    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual({ cat: '', type: '', path: '' })
  })
})
