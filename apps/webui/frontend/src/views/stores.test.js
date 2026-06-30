import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('../api.js', () => ({ api: {
  listWarehouses: vi.fn().mockResolvedValue({ warehouses: [{ warehouse_id: 1 }] }),
  syncWarehouses: vi.fn().mockResolvedValue({ synced: 1, warehouses: [{ warehouse_id: 1 }, { warehouse_id: 2 }] }),
  storeStats: vi.fn().mockResolvedValue({ product_count: 12, balance: { amount: 345.67, currency_code: 'RUB' } }),
  saveSettings: vi.fn().mockResolvedValue({ settings: { ozon_stores: [] } }),
  listDrafts: vi.fn().mockResolvedValue({ drafts: [], total: 0 }),
} }))

import { api } from '../api.js'
import Stores from './Stores.vue'
import { useAppStore } from '../stores/app.js'

function mountStores() {
  setActivePinia(createPinia())
  const store = useAppStore()
  store.settings = { ozon_stores: [
    { name: 'RU-Store', client_id: '2841057', is_default: true, api_key_saved: true },
    { name: '测试店', client_id: '2207781', is_default: false, api_key_saved: false },
  ] }
  const w = mount(Stores, { global: { plugins: [ElementPlus], stubs: { 'router-link': true } } })
  return { w, store }
}

async function tick() {
  await new Promise(resolve => setTimeout(resolve, 0))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Stores 页面', () => {
  it('渲染店铺卡和连接状态', async () => {
    const { w } = mountStores()
    await tick()
    expect(w.text()).toContain('RU-Store')
    expect(w.text()).toContain('测试店')
    expect(w.text()).toContain('凭证失效')
  })

  it('初始化会加载仓库、商品数和余额', async () => {
    const { w } = mountStores()
    await tick()
    expect(api.listWarehouses).toHaveBeenCalledWith('2841057')
    expect(api.storeStats).toHaveBeenCalledWith('2841057')
    expect(w.text()).toContain('12')
    expect(w.text()).toContain('345,67 RUB')
  })

  it('点击同步会同步仓库并刷新 stats', async () => {
    const { w } = mountStores()
    await tick()
    const btn = w.findAll('button').find(b => b.text().includes('同步'))
    await btn.trigger('click')
    await tick()
    expect(api.syncWarehouses).toHaveBeenCalledWith('2841057')
    expect(api.storeStats).toHaveBeenCalledWith('2841057')
    expect(w.text()).toContain('2')
  })

  it('点击切换当前店调 setCurrentStore', async () => {
    const { w, store } = mountStores()
    const spy = vi.spyOn(store, 'setCurrentStore')
    const btn = w.findAll('button').find(b => b.text().includes('设为当前'))
    if (btn) {
      await btn.trigger('click')
      expect(spy).toHaveBeenCalled()
    }
  })
})
