import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Settings from '../src/views/Settings.vue'
import { api } from '../src/api.js'
import { useAppStore } from '../src/stores/app.js'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('Settings.vue 店铺管理', () => {
  it('渲染已有店铺：name、client_id 末4位、已配', async () => {
    const store = useAppStore()
    store.settings = {
      ozon_client_id: '111',
      ozon_stores: [{ name: '店2', client_id: '2222', is_default: true, api_key_saved: true }],
    }
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await w.vm.$nextTick()
    const text = w.text()
    expect(text).toContain('店2')
    expect(text).toMatch(/2{3,4}/)  // 末4位包含 '2222'
    expect(text).toContain('已配')
  })

  it('点添加按钮调用 api.saveSettings，包含新店且首店设默认', async () => {
    const store = useAppStore()
    store.settings = { ozon_client_id: '', ozon_stores: [] }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({
      settings: {
        ozon_stores: [{ name: '店A', client_id: '333', is_default: true, api_key_saved: true }],
      },
      status: {}, paths: {},
    })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    w.vm.newStore.name = '店A'
    w.vm.newStore.client_id = '333'
    w.vm.newStore.api_key = 'SK-A'
    await w.vm.addStore()
    await flushPromises()
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({
        ozon_stores: expect.arrayContaining([
          expect.objectContaining({ name: '店A', client_id: '333', api_key: 'SK-A', is_default: true }),
        ]),
      }),
    )
    expect(w.vm.newStore.name).toBe('')  // 添加后清空输入框
  })

  it('设为默认：调用 saveSettings，目标店 is_default=true 其余 false', async () => {
    const store = useAppStore()
    store.settings = { ozon_stores: [
      { name: 'A', client_id: '1', is_default: true, api_key_saved: true },
      { name: 'B', client_id: '2', is_default: false, api_key_saved: true } ] }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: store.settings, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.setDefaultStore('2')
    await flushPromises()
    const sent = spy.mock.calls.at(-1)[0].ozon_stores
    expect(sent.find(s => s.client_id === '2').is_default).toBe(true)
    expect(sent.find(s => s.client_id === '1').is_default).toBe(false)
  })

  it('删除店铺：发送剩余列表(不含被删)', async () => {
    const store = useAppStore()
    store.settings = { ozon_stores: [
      { name: 'A', client_id: '1', is_default: true, api_key_saved: true },
      { name: 'B', client_id: '2', is_default: false, api_key_saved: true } ] }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: store.settings, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.removeStore('1')
    await flushPromises()
    const sent = spy.mock.calls.at(-1)[0].ozon_stores
    expect(sent.map(s => s.client_id)).toEqual(['2'])
  })
})
