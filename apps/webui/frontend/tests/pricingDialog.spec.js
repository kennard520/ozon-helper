import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi } from 'vitest'
import PricingDialog from '../src/components/PricingDialog.vue'
import { api } from '../src/api.js'

describe('PricingDialog', () => {
  it('应用时 emit apply 带 price/oldPrice 并存佣金映射+汇率', async () => {
    vi.spyOn(api, 'saveCommissionMap').mockResolvedValue({ ok: true })
    vi.spyOn(api, 'saveSettings').mockResolvedValue({})
    // length_mm 等列实存厘米(历史名)：20×15×10 cm 小件，能匹配 realFBS 线路
    const draft = { id: 1, cost_cny: 30, weight_g: 600, length_mm: 20, width_mm: 15, height_mm: 10, category_id: '1', type_id: '2' }
    const w = mount(PricingDialog, { global: { plugins: [ElementPlus] }, props: { modelValue: true, draft } })
    await flushPromises()
    w.vm.recompute()
    expect(w.vm.result.targetRub).toBeGreaterThan(0)
    await w.vm.apply()
    const ev = w.emitted().apply[0][0]
    expect(Number(ev.price)).toBeGreaterThan(0)
    expect(api.saveCommissionMap).toHaveBeenCalled()
    expect(api.saveSettings).toHaveBeenCalled()
  })
})
