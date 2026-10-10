import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import VariantList from '../src/components/VariantList.vue'

const VARIANTS = [
  {
    sku: '111',
    label: 'Белый',
    aspect: 'Цвет',
    link: 'https://www.ozon.ru/product/test-111/',
    price: 4274,
    cover: 'https://ir.ozone.ru/s3/img/white.jpg',
    available: true,
    active: true,
  },
  {
    sku: '222',
    label: 'Чёрный',
    aspect: 'Цвет',
    link: 'https://www.ozon.ru/product/test-222/',
    price: 3999,
    cover: 'https://ir.ozone.ru/s3/img/black.jpg',
    available: false,
    active: false,
  },
  {
    sku: '333',
    label: 'Синий',
    aspect: 'Цвет',
    link: 'https://www.ozon.ru/product/test-333/',
    price: null,
    cover: '',
    available: true,
    active: false,
  },
]

describe('VariantList', () => {
  it('renders 3 variant cells for 3-item array', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    expect(w.findAll('.variant-cell').length).toBe(3)
  })

  it('active variant has class "active"', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    const cells = w.findAll('.variant-cell')
    expect(cells[0].classes()).toContain('active')
    expect(cells[1].classes()).not.toContain('active')
    expect(cells[2].classes()).not.toContain('active')
  })

  it('unavailable variant has class "off" and shows 缺货', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    const cells = w.findAll('.variant-cell')
    expect(cells[1].classes()).toContain('off')
    expect(cells[1].find('.variant-off').text()).toBe('缺货')
    // available cell does not have off class
    expect(cells[0].classes()).not.toContain('off')
    expect(cells[0].find('.variant-off').exists()).toBe(false)
  })

  it('variant without cover shows 无图 placeholder', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    const cells = w.findAll('.variant-cell')
    // cell[2] has empty cover
    expect(cells[2].find('img').exists()).toBe(false)
    expect(cells[2].find('.variant-img-empty').text()).toBe('无图')
    // cell[0] has cover → img element
    expect(cells[0].find('img').exists()).toBe(true)
  })

  it('variant cell <a> href equals variant link', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    const cells = w.findAll('.variant-cell')
    expect(cells[0].attributes('href')).toBe('https://www.ozon.ru/product/test-111/')
    expect(cells[1].attributes('href')).toBe('https://www.ozon.ru/product/test-222/')
  })

  it('shows label text in .variant-label', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    const cells = w.findAll('.variant-cell')
    expect(cells[0].find('.variant-label').text()).toBe('Белый')
    expect(cells[1].find('.variant-label').text()).toBe('Чёрный')
  })

  it('shows price when non-null', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    const cells = w.findAll('.variant-cell')
    expect(cells[0].find('.variant-meta').text()).toContain('4274')
    // cell[2] has null price → no price text shown
    expect(cells[2].find('.variant-meta').text()).not.toContain('₽')
  })

  it('shows group key in header', () => {
    const w = mount(VariantList, { props: { variants: VARIANTS, group: '111' } })
    expect(w.find('.variant-group').text()).toContain('111')
  })

  it('renders nothing when variants is empty array', () => {
    const w = mount(VariantList, { props: { variants: [], group: '' } })
    expect(w.find('.variant-list').exists()).toBe(false)
  })

  it('renders nothing when variants prop is omitted (default)', () => {
    const w = mount(VariantList)
    expect(w.find('.variant-list').exists()).toBe(false)
  })
})
