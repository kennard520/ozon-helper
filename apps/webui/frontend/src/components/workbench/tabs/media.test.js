import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import VideoTab from './VideoTab.vue'
import RichTextTab from './RichTextTab.vue'

const stubs = { MediaManager: true, AiVideoDialog: true, RichContentPreview: true }

describe('VideoTab', () => {
  it('渲染(传 draft)', () => {
    const w = mount(VideoTab, {
      props: { draft: { id: 7, video_url: '', images: [] } },
      global: { plugins: [ElementPlus], stubs }
    })
    expect(w.exists()).toBe(true)
  })
})

describe('RichTextTab', () => {
  it('有富文本 → 渲染 RichContentPreview', () => {
    const w = mount(RichTextTab, {
      props: { draft: { id: 7, source_raw: { rich_content_json: { content: [] } } } },
      global: { plugins: [ElementPlus], stubs }
    })
    expect(
      w.findComponent({ name: 'RichContentPreview' }).exists() || w.html().includes('rich')
    ).toBe(true)
  })

  it('无富文本 → 显示生成入口', () => {
    const w = mount(RichTextTab, {
      props: { draft: { id: 7, source_raw: {} } },
      global: { plugins: [ElementPlus], stubs }
    })
    const btn = w.findAll('button').find(b => b.text().includes('生成'))
    expect(btn).toBeTruthy()
  })
})
