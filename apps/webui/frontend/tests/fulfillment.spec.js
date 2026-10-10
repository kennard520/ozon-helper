import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Fulfillment from '../src/views/Fulfillment.vue'
import { api } from '../src/api.js'

const PROCUREMENT_ROW = {
  id: 1,
  posting_number: 'P-1',
  offer_id: 'SKU-1',
  qty: 2,
  purchase_state: '待采购',
  supplier: '厂A',
  purchase_url: 'u',
  cost_cny: 10,
  note: '',
}
const PROCUREMENT_RESP = { procurement: [PROCUREMENT_ROW] }

beforeEach(() => setActivePinia(createPinia()))

describe('Fulfillment.vue', () => {
  it('onMounted 加载备货板', async () => {
    vi.spyOn(api, 'fbsProcurement').mockResolvedValue(PROCUREMENT_RESP)
    const w = mount(Fulfillment, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(api.fbsProcurement).toHaveBeenCalled()
    expect(w.vm.procurement).toHaveLength(1)
  })

  it('doPull 调用 fbsPull 并刷新 procurement', async () => {
    vi.spyOn(api, 'fbsProcurement').mockResolvedValue(PROCUREMENT_RESP)
    vi.spyOn(api, 'fbsPull').mockResolvedValue({ synced: 2, procurement: [PROCUREMENT_ROW] })
    const w = mount(Fulfillment, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.doPull()
    await flushPromises()
    expect(api.fbsPull).toHaveBeenCalled()
    expect(w.vm.procurement).toHaveLength(1)
  })

  it('changeState 调用 fbsSetState', async () => {
    vi.spyOn(api, 'fbsProcurement').mockResolvedValue(PROCUREMENT_RESP)
    vi.spyOn(api, 'fbsSetState').mockResolvedValue(PROCUREMENT_RESP)
    const w = mount(Fulfillment, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    await w.vm.changeState(1, '已下单')
    await flushPromises()
    expect(api.fbsSetState).toHaveBeenCalledWith(1, '已下单', '', expect.anything())
  })

  it('doShip 经过 confirmFn 后调用 fbsShip', async () => {
    vi.spyOn(api, 'fbsProcurement').mockResolvedValue(PROCUREMENT_RESP)
    vi.spyOn(api, 'fbsShip').mockResolvedValue({ result: ['P-1'], shipped: true })
    const w = mount(Fulfillment, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    w.vm.confirmFn = vi.fn().mockResolvedValue(true)
    await w.vm.doShip({ posting_number: 'P-1', id: 1 })
    await flushPromises()
    expect(w.vm.confirmFn).toHaveBeenCalled()
    expect(api.fbsShip).toHaveBeenCalledWith('P-1', expect.anything())
  })

  it('changeState 失败后回滚 purchase_state 并报错', async () => {
    vi.spyOn(api, 'fbsProcurement').mockResolvedValue(PROCUREMENT_RESP)
    vi.spyOn(api, 'fbsSetState').mockRejectedValue(new Error('boom'))
    const w = mount(Fulfillment, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    // Row starts at '待采购'. Call changeState(1, '已下单') — simulates el-select @change
    // firing BEFORE v-model has updated the row (the prior value is still '待采购' at call time).
    await w.vm.changeState(1, '已下单')
    await flushPromises()
    expect(w.vm.procurement.find(r => r.id === 1).purchase_state).toBe('待采购')
  })

  it('doShip 取消后不调 fbsShip', async () => {
    vi.spyOn(api, 'fbsProcurement').mockResolvedValue(PROCUREMENT_RESP)
    vi.spyOn(api, 'fbsShip').mockResolvedValue({ result: ['P-1'], shipped: true })
    const w = mount(Fulfillment, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    w.vm.confirmFn = vi.fn().mockRejectedValue('cancel')
    await w.vm.doShip({ posting_number: 'P-1' })
    await flushPromises()
    expect(api.fbsShip).not.toHaveBeenCalled()
  })
})
