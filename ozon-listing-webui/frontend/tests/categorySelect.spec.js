import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import CategorySelect from '../src/components/CategorySelect.vue'
import { api } from '../src/api.js'

const TREE = [{
  value: 'cat-1', label: '家居', disabled: true,
  children: [
    { value: '1-10', label: '收纳箱' },
    { value: '2-20', label: '餐具' },
  ],
}]

beforeEach(() => {
  vi.spyOn(api, 'categoryTree').mockResolvedValue({ tree: TREE })
  vi.spyOn(api, 'categoryResolve').mockResolvedValue({ leaf: { path: '家居 / 收纳箱' } })
})
afterEach(() => vi.restoreAllMocks())

describe('CategorySelect el-tree-select', () => {
  it('挂载拉取树', async () => {
    mount(CategorySelect, { props: { modelValue: { cat: '', type: '' } }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(api.categoryTree).toHaveBeenCalled()
  })

  it('选末级叶子 emit {cat,type}', async () => {
    const w = mount(CategorySelect, { props: { modelValue: { cat: '', type: '' } }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.onSelectChange('1-10')
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toMatchObject({ cat: '1', type: '10' })
  })

  it('清空 emit 空', async () => {
    const w = mount(CategorySelect, { props: { modelValue: { cat: '1', type: '10' } }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.onSelectChange('')
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual({ cat: '', type: '', path: '' })
  })
})
