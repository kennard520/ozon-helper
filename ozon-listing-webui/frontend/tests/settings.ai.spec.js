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
    const store = useAppStore()
    store.settings = {
      ozon_stores: [],
      ai_text: { engine: 'openai', api_base: 'B', model: 'M', api_key_saved: true },
      ai_image: { engine: 'agnes', api_base: '', model: '', api_key_saved: false },
      ai_video: { engine: 'agnes', api_base: '', model: '', api_key_saved: false },
      translate_mode: 'ai',
    }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: store.settings, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    w.vm.aiText.model = 'deepseek-chat'
    await w.vm.save()
    await flushPromises()
    const payload = spy.mock.calls.at(-1)[0]
    expect(payload.ai_text).toMatchObject({ engine: 'openai', model: 'deepseek-chat' })
    expect(payload).toHaveProperty('ai_image')
    expect(payload).toHaveProperty('ai_video')
  })

  it('文本 AI 模态：回填 + 保存带 ai_text.multimodal', async () => {
    const store = useAppStore()
    store.settings = {
      ozon_stores: [],
      ai_text: { engine: 'agnes', api_base: 'B', model: 'M', api_key_saved: true, multimodal: true },
      ai_image: { engine: 'agnes', api_base: '', model: '', api_key_saved: false },
      ai_video: { engine: 'agnes', api_base: '', model: '', api_key_saved: false },
    }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: store.settings, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.vm.aiText.multimodal).toBe(true)
    await w.vm.save()
    await flushPromises()
    expect(spy.mock.calls.at(-1)[0].ai_text.multimodal).toBe(true)
  })
})
