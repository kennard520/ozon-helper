import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Warehouses from '../src/views/Warehouses.vue'
import { api } from '../src/api.js'

const FAKE_WAREHOUSE = { warehouse_id: 111, name: 'FBS-Москва', is_rfbs: true, status: 'created', is_default: false }
const FAKE_WAREHOUSES = [FAKE_WAREHOUSE]

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('Warehouses.vue', () => {
  it('onMounted 后 warehouses 有 1 条', async () => {
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.vm.warehouses).toHaveLength(1)
    expect(w.vm.warehouses[0].warehouse_id).toBe(111)
  })

  it('doSync 调 api.syncWarehouses 并刷新列表', async () => {
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const syncSpy = vi.spyOn(api, 'syncWarehouses').mockResolvedValue({ synced: 1, warehouses: FAKE_WAREHOUSES })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.doSync()
    expect(syncSpy).toHaveBeenCalled()
  })

  it('makeDefault(111) 调 api.setDefaultWarehouse(111)', async () => {
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const defaultSpy = vi.spyOn(api, 'setDefaultWarehouse').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.makeDefault(111)
    expect(defaultSpy).toHaveBeenCalledWith(111, expect.anything())
  })
})
