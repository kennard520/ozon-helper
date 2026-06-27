import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Settings from '../src/views/Settings.vue'
import { api } from '../src/api.js'

beforeEach(() => setActivePinia(createPinia()))

describe('Settings.vue', () => {
  it('保存调用 api.saveSettings 且带 contract_currency', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {}, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    w.vm.form.contract_currency = 'CNY'
    await w.vm.save()
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ contract_currency: 'CNY' }))
  })

  it('rub_cny 为 0 时不发送，避免抹掉已存汇率', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {}, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    w.vm.form.rub_cny = 0
    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    expect('rub_cny' in payload).toBe(false)          // 0 → 不发
    expect(payload.contract_currency).toBe('CNY')     // 有效值照常发
  })

  it('文本 AI(ai_text)：回填 platform/model，key 只在非空时发送', async () => {
    // 当前实现：ai_text 用 platform+model 而非 engine+api_base+api_key
    // 平台级别管理 base 和 key；ai_text 只存 platform 名 + model + multimodal
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = {
      ai_platforms: [{ name: 'openai-plat', base: 'https://x/v1', key_saved: true }],
      ai_text: { platform: 'openai-plat', model: 'm' },
      contract_currency: 'CNY',
    }
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await w.vm.$nextTick()
    // 回填：平台列表和用途选择
    expect(w.vm.aiPlatforms[0].base).toBe('https://x/v1')
    expect(w.vm.aiUses.text.platform).toBe('openai-plat')
    expect(w.vm.aiUses.text.model).toBe('m')
    // 平台 key 设为非空时，保存时发送到 ai_platforms[].key
    w.vm.aiPlatforms[0].key = 'sk-1'
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {}, status: {}, paths: {} })
    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    // 平台 key 非空时发送
    expect(payload.ai_platforms[0].key).toBe('sk-1')
    // ai_text 包含 platform 和 model
    expect(payload.ai_text.platform).toBe('openai-plat')
    expect(payload.ai_text.model).toBe('m')
  })

  it('保存时带 ai_auto_apply', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    w.vm.form.ai_auto_apply = true
    await w.vm.save()
    expect(spy.mock.calls[0][0].ai_auto_apply).toBe(true)
  })

  it('保存时带 auto_publish', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    w.vm.form.auto_publish = true
    await w.vm.save()
    expect(spy.mock.calls[0][0].auto_publish).toBe(true)
  })

  it('回填 auto_publish', async () => {
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = { auto_publish: true, contract_currency: 'CNY' }
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await w.vm.$nextTick()
    expect(w.vm.form.auto_publish).toBe(true)
  })

  it('settings 异步到达后回填 form（防止竞态导致空表）', async () => {
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = {}  // 挂载时还没数据
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    expect(w.vm.form.rub_cny).toBe(0)
    // loadState 之后才到达
    store.settings = { rub_cny: 0.09, contract_currency: 'RUB' }
    await w.vm.$nextTick()
    expect(w.vm.form.rub_cny).toBeCloseTo(0.09)
    expect(w.vm.form.contract_currency).toBe('RUB')
  })
})
