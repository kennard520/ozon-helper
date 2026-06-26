import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import DraftDetail from '../src/components/DraftDetail.vue'
import { api } from '../src/api.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], optional: [], missing: [], errors: [] })
})
afterEach(() => vi.restoreAllMocks())

const draft = {
  id: 7, category_id: '1', type_id: '2', ozon_title: 'T', description: 'd',
  images: ['https://img/a.jpg'], local_images: [], attributes: [], ai_proposal: null,
}

describe('DraftDetail ChatGPT 图片提示词', () => {
  it('生成提示词：调对 api、渲染 main + 卖点', async () => {
    vi.spyOn(api, 'aiImagePrompts').mockResolvedValue({
      ok: true, main: 'MAIN PROMPT', selling_points: ['s1', 's2', 's3'],
      source_images: ['https://img/a.jpg'], local_images: [],
    })
    const w = mount(DraftDetail, { props: { draft }, global: { plugins: [ElementPlus] } })
    w.vm.imgGenN = 3
    await w.vm.doImagePrompts()
    await flushPromises()
    expect(api.aiImagePrompts).toHaveBeenCalledWith(7, 3)
    expect(w.vm.imgPrompts.main).toBe('MAIN PROMPT')
    expect(w.vm.imgPrompts.selling_points).toHaveLength(3)
  })

  it('复制全部文本含主图、卖点、远程图URL和详情图URL', async () => {
    vi.spyOn(api, 'aiImagePrompts').mockResolvedValue({
      ok: true, main: 'M', selling_points: ['a', 'b'],
      source_images: ['https://ir.ozone.ru/x.jpg'], local_images: ['/media/k/00.jpg'],
      detail_images: ['https://cbu01.alicdn.com/d1.jpg'],
    })
    const w = mount(DraftDetail, { props: { draft }, global: { plugins: [ElementPlus] } })
    await w.vm.doImagePrompts()
    const txt = w.vm.allImgPromptsText
    expect(txt).toContain('主图: M')
    expect(txt).toContain('卖点图1: a')
    expect(txt).toContain('卖点图2: b')
    expect(txt).toContain('https://ir.ozone.ru/x.jpg')        // 主图参考远程 URL
    expect(txt).toContain('https://cbu01.alicdn.com/d1.jpg')  // 详情图 URL
    expect(txt).not.toContain('/media/k/00.jpg')               // 本地路径不附
  })

  it('copyText 调用 clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.assign(navigator, { clipboard: { writeText } })
    const w = mount(DraftDetail, { props: { draft }, global: { plugins: [ElementPlus] } })
    await w.vm.copyText('hello')
    expect(writeText).toHaveBeenCalledWith('hello')
  })
})
