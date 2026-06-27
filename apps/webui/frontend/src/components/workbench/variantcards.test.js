import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import VariantCardsPane from './VariantCardsPane.vue'
import { useWorkbenchStore } from '../../stores/workbench.js'

function setup() {
  setActivePinia(createPinia())
  const wb = useWorkbenchStore()
  wb.variants = [{ id: 1, spec: '雾灰·350ml', price: 1190, status: 'ready', image: 'a.jpg' },
                 { id: 2, spec: '雾灰·500ml', price: 1290, status: 'ready', image: 'b.jpg' }]
  wb.selectedVariantIds = new Set([1, 2]); wb.currentVariantId = 1
  const w = mount(VariantCardsPane, { global: { plugins: [ElementPlus] } })
  return { w, wb }
}
describe('VariantCardsPane', () => {
  it('渲染变体卡 + 已选数', () => {
    const { w } = setup()
    expect(w.text()).toContain('雾灰·350ml'); expect(w.text()).toContain('1190')
    expect(w.text()).toContain('已选 2')
  })
  it('点卡设当前变体', async () => {
    const { w, wb } = setup()
    const cards = w.findAll('.vcard')
    await cards[1].trigger('click')
    expect(wb.currentVariantId).toBe(2)
  })
  it('清空选择', async () => {
    const { w, wb } = setup()
    const btn = w.findAll('button').find(b => b.text().includes('清空'))
    await btn.trigger('click')
    expect(wb.selectedVariantIds.size).toBe(0)
  })
})
