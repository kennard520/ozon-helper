import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Settings from '../src/views/Settings.vue'
import { api } from '../src/api.js'

beforeEach(() => setActivePinia(createPinia()))

describe('Settings 翻译模式', () => {
  it('保存固定带 translate_mode=ai（已去掉手动/词表选择器）', async () => {
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = { contract_currency: 'CNY' }
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await w.vm.$nextTick()
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {}, status: {}, paths: {} })
    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    expect(payload.translate_mode).toBe('ai')
  })
})
