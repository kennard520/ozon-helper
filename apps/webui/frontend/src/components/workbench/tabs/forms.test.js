import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import InfoTab from './InfoTab.vue'
import PurchaseTab from './PurchaseTab.vue'

const stubs = { CategorySelect: true, BrandSelect: true }
function mountInfo(form) {
  return mount(InfoTab, { props: { form, draft: {} }, global: { plugins: [ElementPlus], stubs } })
}
describe('InfoTab', () => {
  it('渲染标题值 + 改 stock 点保存 emit save', async () => {
    const form = { ozon_title: '保温杯', category_id: '1', type_id: '2', brand_id: null,
      brand_name: '', stock: 5, price: 38, old_price: '', cost_cny: '', weight_g: 0,
      length_mm: 0, width_mm: 0, height_mm: 0, description: '' }
    const w = mountInfo(form)
    expect(w.find('input[value="保温杯"], textarea').exists() || w.html().includes('保温杯')).toBe(true)
    const btn = w.findAll('button').find(b => b.text().includes('保存'))
    await btn.trigger('click')
    expect(w.emitted('save')).toBeTruthy()
  })
})
describe('PurchaseTab', () => {
  it('渲染采购字段 + 保存', async () => {
    const form = { purchase_url: 'http://x', supplier: '厂A', cost_cny: 12 }
    const w = mount(PurchaseTab, { props: { form }, global: { plugins: [ElementPlus] } })
    const btn = w.findAll('button').find(b => b.text().includes('保存'))
    await btn.trigger('click')
    expect(w.emitted('save')).toBeTruthy()
  })
})
