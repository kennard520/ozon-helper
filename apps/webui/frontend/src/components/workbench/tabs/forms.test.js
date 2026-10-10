import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import InfoTab from './InfoTab.vue'
import PurchaseTab from './PurchaseTab.vue'

const stubs = { CategorySelect: true, BrandSelect: true }

function mountInfo(form) {
  return mount(InfoTab, { props: { form, draft: { offer_id: 'offer-1' } }, global: { plugins: [ElementPlus], stubs } })
}

describe('InfoTab', () => {
  it('renders core listing fields', () => {
    const form = {
      ozon_title: '保温杯',
      category_id: '1',
      type_id: '2',
      brand_id: null,
      brand_name: '',
      stock: 5,
      price: 38,
      old_price: 0,
      cost_cny: 0,
      weight_g: 0,
      length_mm: 0,
      width_mm: 0,
      height_mm: 0,
      description: '',
    }
    const w = mountInfo(form)
    expect(w.text()).toContain('Offer ID')
    expect(w.text()).toContain('offer-1')
    expect(w.find('input[placeholder]').exists()).toBe(true)
  })

  it('keeps the semantic field order and hides stock from listing info', () => {
    const form = {
      ozon_title: '保温杯',
      category_id: '1',
      type_id: '2',
      brand_id: null,
      brand_name: '',
      stock: 5,
      price: 38,
      old_price: 48,
      cost_cny: 0,
      weight_g: 300,
      length_mm: 0,
      width_mm: 0,
      height_mm: 0,
      description: '',
    }
    const w = mountInfo(form)
    const fields = w.findAll('.ifield').map((field) => field.find('label').text())
    expect(fields).toEqual([
      'Ozon 标题 (RU)',
      '类目',
      '货号 (Offer ID)',
      '品牌',
      '售价 (₽)',
      '划线价 (₽)',
      '尺寸 长 x 宽 x 高 (mm)',
      '重量 (g)',
    ])
    expect(w.text()).not.toContain('库存')
  })
})

describe('PurchaseTab', () => {
  it('renders purchase fields and keeps form binding', async () => {
    const form = { purchase_url: 'http://x', supplier: '厂A', cost_cny: 12, purchase_note: '' }
    const w = mount(PurchaseTab, { props: { form }, global: { plugins: [ElementPlus] } })
    expect(form.cost_cny).toBe(12)
    const input = w.find('input')
    await input.setValue('http://new')
    expect(form.purchase_url).toBe('http://new')
  })
})
