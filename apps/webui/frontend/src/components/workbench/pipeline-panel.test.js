import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import PipelinePanel from './PipelinePanel.vue'
import { useWorkbenchStore } from '../../stores/workbench.js'

function setup() {
  setActivePinia(createPinia())
  const wb = useWorkbenchStore()
  wb.variants = [{ id: 1, steps: { understand: true, copy: true }, done: 2 },
                 { id: 2, steps: { understand: true, copy: false }, done: 1 }]
  wb.selectedVariantIds = new Set([1, 2]); wb.currentVariantId = 1
  const w = mount(PipelinePanel, { global: { plugins: [ElementPlus] } })
  return { w, wb }
}
describe('PipelinePanel', () => {
  it('渲染 7 步 + 一键跑完(已选数)', () => {
    const { w } = setup()
    expect(w.text()).toContain('图文理解'); expect(w.text()).toContain('AI文案')
    expect(w.text()).toContain('发布')
    expect(w.text()).toContain('2')  // 已选 2
  })
  it('聚合进度:understand 2/2、copy 1/2', () => {
    const { w } = setup()
    // understand 两个变体都 true → 2/2;copy 只 1 个 → 1/2
    expect(w.text()).toContain('2/2')
    expect(w.text()).toContain('1/2')
  })
})
