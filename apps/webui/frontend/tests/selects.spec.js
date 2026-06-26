import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi } from 'vitest'
import CategorySelect from '../src/components/CategorySelect.vue'
import BrandSelect from '../src/components/BrandSelect.vue'
import { api } from '../src/api.js'

describe('CategorySelect', () => {
  it('选末级类型 emit update:modelValue', async () => {
    vi.spyOn(api, 'categoryTree').mockResolvedValue({ tree: [
      { value: 'cat-1', label: '收纳', disabled: true, children: [{ value: '1-2', label: '箱' }] }] })
    vi.spyOn(api, 'categoryResolve').mockResolvedValue({ leaf: { path: '收纳 / 箱' } })
    const w = mount(CategorySelect, { global: { plugins: [ElementPlus] }, props: { modelValue: { cat: '', type: '' } } })
    await flushPromises()
    await w.vm.onSelectChange('1-2')
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toMatchObject({ cat: '1', type: '2' })
  })
})

describe('BrandSelect', () => {
  it('清空时 emit 空品牌（P1-4）', () => {
    const w = mount(BrandSelect, { global: { plugins: [ElementPlus] }, props: { cat: 1, type: 2, modelValue: { brand_id: 9, brand_name: 'X' } } })
    w.vm.onSelectChange(null)
    expect(w.emitted()['update:modelValue'][0][0]).toEqual({ brand_id: null, brand_name: '' })
  })
})
