import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Settings from '../src/views/Settings.vue'
import { api } from '../src/api.js'
import { useAppStore } from '../src/stores/app.js'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('Settings.vue 三套 AI 配置', () => {
  it('保存发送 ai_text/ai_image/ai_video 三块', async () => {
    // 当前实现：ai_text/ai_image/ai_video 各是 { platform, model }，ai_text 还带 multimodal
    const store = useAppStore()
    store.settings = {
      ozon_stores: [],
      ai_platforms: [{ name: 'myplat', base: 'https://base/v1', key_saved: true }],
      ai_text: { platform: 'myplat', model: 'old-model' },
      ai_image: { platform: 'myplat', model: 'img-model' },
      ai_video: { platform: 'myplat', model: 'vid-model' },
      translate_mode: 'ai',
    }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: store.settings, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    // 修改文本 AI 模型
    w.vm.aiUses.text.model = 'deepseek-chat'
    await w.vm.save()
    await flushPromises()
    const payload = spy.mock.calls.at(-1)[0]
    // 三套用途块都存在
    expect(payload.ai_text).toMatchObject({ platform: 'myplat', model: 'deepseek-chat' })
    expect(payload).toHaveProperty('ai_image')
    expect(payload).toHaveProperty('ai_video')
  })

  it('文本 AI 模态：回填 + 保存带 ai_text.multimodal', async () => {
    // ai_text.multimodal 通过 aiUses.text.multimodal 回填并保存
    const store = useAppStore()
    store.settings = {
      ozon_stores: [],
      ai_platforms: [{ name: 'myplat', base: 'B', key_saved: true }],
      ai_text: { platform: 'myplat', model: 'M', multimodal: true },
      ai_image: { platform: 'myplat', model: '' },
      ai_video: { platform: 'myplat', model: '' },
    }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: store.settings, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    // multimodal 通过 aiUses.text.multimodal 回填
    expect(w.vm.aiUses.text.multimodal).toBe(true)
    await w.vm.save()
    await flushPromises()
    // 保存时 ai_text.multimodal 正确包含
    expect(spy.mock.calls.at(-1)[0].ai_text.multimodal).toBe(true)
  })
})
