import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Warehouses from '../src/views/Warehouses.vue'
import { api } from '../src/api.js'

const FAKE_WAREHOUSE = { warehouse_id: 111, name: 'FBS Moscow', is_rfbs: true, status: 'created', is_default: false }
const FAKE_WAREHOUSES = [FAKE_WAREHOUSE]

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('Warehouses.vue', () => {
  it('loads warehouses on mount', async () => {
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.vm.warehouses).toHaveLength(1)
    expect(w.vm.warehouses[0].warehouse_id).toBe(111)
  })

  it('syncs warehouses and refreshes the list', async () => {
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const syncSpy = vi.spyOn(api, 'syncWarehouses').mockResolvedValue({ synced: 1, warehouses: FAKE_WAREHOUSES })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.doSync()
    expect(syncSpy).toHaveBeenCalled()
  })

  it('sets the default warehouse', async () => {
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const defaultSpy = vi.spyOn(api, 'setDefaultWarehouse').mockResolvedValue({ warehouses: FAKE_WAREHOUSES })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.makeDefault(111)
    expect(defaultSpy).toHaveBeenCalledWith(111, expect.anything())
  })

  it('groups PUDO and Courier variants like the Ozon seller UI', async () => {
    const warehouse = {
      warehouse_id: 111,
      name: 'Chengdu',
      is_rfbs: true,
      status: 'created',
      delivery_methods: [
        { delivery_method_id: 1, warehouse_id: 111, name: 'ZTO Standard Small Chengdu PUDO', provider_id: 1289, dropoff_code: 'StSDGP' },
        { delivery_method_id: 2, warehouse_id: 111, name: 'ZTO Standard Small Chengdu Courier', provider_id: 1289, dropoff_code: 'StSDGP' },
        { delivery_method_id: 3, warehouse_id: 111, name: 'China Post to OZON Economy China Post to OZON Economy PUDO Chengdu', provider_id: 1595, dropoff_code: '61010104' },
        { delivery_method_id: 4, warehouse_id: 111, name: 'ZTO Economy Premium Big Chengdu Courier', provider_id: 1387, dropoff_code: 'EcoPBXM' },
        { delivery_method_id: 5, warehouse_id: 111, name: 'ZTO Economy Premium Big Chengdu PUDO', provider_id: 1387, dropoff_code: 'EcoPBXM' },
        { delivery_method_id: 6, warehouse_id: 111, name: 'China Post ePacket Economy Track CIS Kazakhstan Chengdu', provider_id: 1081, dropoff_code: '61002126' },
        { delivery_method_id: 7, warehouse_id: 111, name: 'ZTO Economy Premium Small Chengdu Courier', provider_id: 1293, dropoff_code: 'EcoPSDGP' },
        { delivery_method_id: 8, warehouse_id: 111, name: 'ZTO Economy Premium Small Chengdu PUDO', provider_id: 1293, dropoff_code: 'EcoPSDGP' },
        { delivery_method_id: 9, warehouse_id: 111, name: 'CEL Economy Budget Chengdu Courier', provider_id: 1165, dropoff_code: 'CEL0012ECONBUDGET' },
        { delivery_method_id: 10, warehouse_id: 111, name: 'CEL Economy Budget Chengdu PUDO', provider_id: 1165, dropoff_code: 'CEL0012ECONBUDGET' },
        { delivery_method_id: 11, warehouse_id: 111, name: 'CEL Economy Big Chengdu Courier', provider_id: 1171, dropoff_code: 'CEL0012ECONBIG' },
        { delivery_method_id: 12, warehouse_id: 111, name: 'CEL Economy Big Chengdu PUDO', provider_id: 1171, dropoff_code: 'CEL0012ECONBIG' },
      ],
    }
    vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: [warehouse] })
    const w = mount(Warehouses, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const methods = w.vm.deliveryMethodsOf(warehouse)
    expect(methods).toHaveLength(7)
    expect(methods.map(m => m.display_name)).toContain('ZTO Standard Small Chengdu')
    expect(w.vm.deliveryMethodTotal([warehouse])).toBe(7)
  })
})
