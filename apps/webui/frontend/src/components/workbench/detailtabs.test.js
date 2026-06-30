import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api.js', () => ({ api: {
  getDraft: vi.fn().mockResolvedValue({ id: 7, ozon_title: '杯子', source_raw: {}, attributes: [] }),
  patchDraft: vi.fn().mockResolvedValue({ draft: {} }),
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: 'G', count: 2, variants: [] }),
  copyImagesTo: vi.fn().mockResolvedValue({ ok: true }),
  uploadMedia: vi.fn().mockResolvedValue({ url: '/media/x.jpg' }),
  galleryAdd: vi.fn().mockResolvedValue({}),
  galleryRemove: vi.fn().mockResolvedValue({}),
  galleryReorder: vi.fn().mockResolvedValue({}),
  deleteImage: vi.fn().mockResolvedValue({}),
  aiImagePrompts: vi.fn().mockResolvedValue({ main: 'p', selling_points: [] }),
  aiImage: vi.fn().mockResolvedValue({ ok: true }),
  whitenMain: vi.fn().mockResolvedValue({ ok: true }),
  localizeImage: vi.fn().mockResolvedValue({ ok: true }),
  sceneImage: vi.fn().mockResolvedValue({ ok: true }),
  regenImage: vi.fn().mockResolvedValue({ ok: true }),
} }))

import { api } from '../../api.js'
import DetailTabs from './DetailTabs.vue'
import { useWorkbenchStore } from '../../stores/workbench.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

async function tick() {
  await new Promise(r => setTimeout(r, 0))
}

describe('DetailTabs', () => {
  it('currentVariantId 有值时渲染 6 个 tab', async () => {
    const wb = useWorkbenchStore()
    wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await tick()
    expect(w.text()).toContain('商品信息')
    expect(w.text()).toContain('特征')
    expect(w.text()).toContain('图片')
    expect(w.text()).toContain('采购信息')
  })

  it('切到特征 tab 显示 AttributesTab', async () => {
    const wb = useWorkbenchStore()
    wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await tick()
    const tab = w.findAll('.s-tabs__item').find(t => t.text().includes('特征'))
    await tab.trigger('click')
    expect(w.find('.attrs-tab').exists()).toBe(true)
  })

  it('数据就绪时点亮 tab 旁绿点', async () => {
    api.getDraft.mockResolvedValueOnce({
      id: 7,
      ozon_title: '杯子',
      video_url: 'http://v/x.mp4',
      source_raw: { rich_content_json: { content: [] } },
      attributes: [{ id: 7700, values: [{ value: 'x' }] }],
      materials: [{ id: 1, in_gallery: 1 }],
    })
    const wb = useWorkbenchStore()
    wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await tick()
    expect(w.findAll('.s-tabs__dot').length).toBe(4)
  })

  it('系统属性不点亮特征绿点', async () => {
    api.getDraft.mockResolvedValueOnce({
      id: 7,
      ozon_title: '杯子',
      source_raw: {},
      attributes: [{ id: 23171, values: [{ value: 'tag' }] }],
    })
    const wb = useWorkbenchStore()
    wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await tick()
    expect(w.findAll('.s-tabs__dot').length).toBe(0)
  })

  it('显示详情头、编辑范围和右侧刷新按钮，不再渲染变体切换器', async () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 7, spec: '雾灰 350ml' }, { id: 8, spec: '雾灰 500ml' }]
    wb.currentVariantId = 7
    const w = mount(DetailTabs)
    await tick()
    expect(w.find('.dt-head').exists()).toBe(true)
    expect(w.text()).toContain('变体详情')
    expect(w.text()).toContain('雾灰 350ml')
    expect(w.text()).toContain('1/2')
    expect(w.find('.dt-refresh').exists()).toBe(true)
    expect(w.find('.dt-pager').exists()).toBe(false)
  })

  it('点击刷新会重新加载详情并刷新工作台', async () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 7, spec: '雾灰 350ml' }]
    wb.currentVariantId = 7
    wb.reload = vi.fn().mockResolvedValue()
    const w = mount(DetailTabs)
    await tick()
    await w.find('.dt-refresh').trigger('click')
    await tick()
    expect(api.getDraft).toHaveBeenCalledTimes(2)
    expect(wb.reload).toHaveBeenCalled()
  })

  it('currentVariantId 为 null 时显示空态且不渲染 tab', () => {
    const wb = useWorkbenchStore()
    wb.currentVariantId = null
    const w = mount(DetailTabs)
    expect(w.find('.s-tabs__item').exists()).toBe(false)
    expect(w.find('.dt--empty').exists()).toBe(true)
    expect(w.text()).toContain('选择至少一个变体查看详情')
  })
})
