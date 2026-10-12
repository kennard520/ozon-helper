import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('../api.js', () => ({ api: {
  performanceCampaigns: vi.fn().mockResolvedValue({
    campaigns: [
      { id: '11', title: 'CPC 活动', is_search_promo: false, products_count: 2 },
      { id: '22', title: '搜索推广', is_search_promo: true, products_count: 1 },
    ],
  }),
  performanceCampaignProducts: vi.fn().mockResolvedValue({
    products: [
      { sku: '1001', offer_id: 'A-1', title: '商品 A' },
      { sku: '1002', offer_id: 'A-2', title: '商品 B' },
    ],
  }),
  performanceProductPromotions: vi.fn().mockResolvedValue({
    summary: { total: 2, reviews_promo_enabled: 1 },
    products: [
      { sku: '1001', offer_id: 'A-1', title: '商品 A', reviews_promo_enabled: true },
      { sku: '1002', offer_id: 'A-2', title: '商品 B', reviews_promo_enabled: false },
    ],
  }),
  performanceOperationPreview: vi.fn().mockResolvedValue({
    operation: 'remove_products',
    campaign_id: '11',
    count: 1,
    items: [{ sku: '1001', offer_id: 'A-1' }],
    warnings: [],
  }),
  performanceOperationCommit: vi.fn().mockResolvedValue({ results: [] }),
  performanceDisableReviewsPromo: vi.fn().mockResolvedValue({ results: [] }),
} }))

import { api } from '../api.js'
import PerformanceCampaigns from './PerformanceCampaigns.vue'
import { useAppStore } from '../stores/app.js'

async function tick() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

function mountPage() {
  setActivePinia(createPinia())
  const store = useAppStore()
  store.settings = { ozon_stores: [{ name: 'RU-Store', client_id: '2841057', is_default: true }] }
  store.currentStore = '2841057'
  const w = mount(PerformanceCampaigns, { global: { plugins: [ElementPlus] } })
  return { w, store }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PerformanceCampaigns 页面', () => {
  it('加载活动和商品，并能预览普通活动批量取消商品', async () => {
    const { w } = mountPage()
    await tick()
    await tick()

    expect(api.performanceCampaigns).toHaveBeenCalledWith('2841057')
    expect(api.performanceProductPromotions).toHaveBeenCalledWith('2841057', 1000)
    expect(w.text()).toContain('CPC 活动')
    expect(w.text()).toContain('快速收集评论')

    await w.vm.selectCampaign({ id: '11', title: 'CPC 活动', is_search_promo: false })
    await tick()
    expect(api.performanceCampaignProducts).toHaveBeenCalledWith('11', '2841057', '')

    w.vm.selectedProducts = [{ sku: '1001', offer_id: 'A-1', title: '商品 A' }]
    await w.vm.previewRemoveSelected()
    expect(api.performanceOperationPreview).toHaveBeenCalledWith({
      operation: 'remove_products',
      campaign_id: '11',
      campaign_title: 'CPC 活动',
      items: [{ sku: '1001', offer_id: 'A-1' }],
    }, '2841057')
    expect(w.text()).toContain('确认执行')
  })

  it('renders seller preview links for promotion product SKU and title', async () => {
    const { w } = mountPage()
    await tick()
    await tick()

    const links = w.findAll('.promotion-panel a.product-preview-link')
    expect(links).toHaveLength(4)
    expect(links[0].attributes('href')).toBe('https://seller.ozon.ru/app/products/1001/edit/preview')
    expect(links[0].attributes('target')).toBe('_blank')
    expect(links[0].attributes('rel')).toBe('noopener noreferrer')
    expect(links[0].text()).toBe('1001')
    expect(links[1].attributes('href')).toBe('https://seller.ozon.ru/app/products/1001/edit/preview')
    expect(links[1].text()).toBe('商品 A')
  })
})
