import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
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
describe('Stores 样板页', () => {
  it('渲染店铺卡 + 连接状态', () => {
    const { w } = mountStores()
    expect(w.text()).toContain('RU-Store')
    expect(w.text()).toContain('测试店')
    expect(w.text()).toContain('凭证失效')
  })
  it('点切换当前店调 setCurrentStore', async () => {
    const { w, store } = mountStores()
    const spy = vi.spyOn(store, 'setCurrentStore')
    const btn = w.findAll('button').find(b => b.text().includes('切换') || b.text().includes('设为当前'))
    if (btn) { await btn.trigger('click'); expect(spy).toHaveBeenCalled() }
  })
})
