import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../../api.js', () => ({ api: {
  getDraft: vi.fn().mockResolvedValue({ id: 7, ozon_title: '杯', source_raw: {}, attributes: [] }),
  patchDraft: vi.fn().mockResolvedValue({ draft: {} }),
} }))
import DetailTabs from './DetailTabs.vue'
import { useWorkbenchStore } from '../../stores/workbench.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('DetailTabs', () => {
  it('currentVariantId 有值时渲染 6 个 tab 头', async () => {
    const wb = useWorkbenchStore(); wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await new Promise(r => setTimeout(r, 0))
    expect(w.text()).toContain('商品信息'); expect(w.text()).toContain('特征')
    expect(w.text()).toContain('图片'); expect(w.text()).toContain('采购信息')
  })
  it('切到特征 tab 显 AttributesTab', async () => {
    const wb = useWorkbenchStore(); wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await new Promise(r => setTimeout(r, 0))
    const tab = w.findAll('.s-tabs__item').find(t => t.text().includes('特征'))
    await tab.trigger('click')
    // AttributesTab 已接线，占位已替换
    expect(w.find('.attrs-tab').exists()).toBe(true)
  })
  it('currentVariantId 为 null 不渲染 tab', () => {
    const wb = useWorkbenchStore(); wb.currentVariantId = null
    const w = mount(DetailTabs)
    expect(w.find('.dt').exists()).toBe(false)
  })
})
