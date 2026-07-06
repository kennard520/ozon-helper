import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Settings from '../src/views/Settings.vue'
import { api } from '../src/api.js'
import { useAppStore } from '../src/stores/app.js'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('Settings.vue', () => {
  it('renders current settings sections', async () => {
    const store = useAppStore()
    store.settings = {
      rub_cny: 0.09,
      contract_currency: 'CNY',
      ai_platforms: [{ name: 'GPTPlus5', base: 'https://example.test/v1', key_saved: true }],
    }
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('System Settings')
    expect(text).toContain('AI')
    expect(text).toContain('realFBS')
  })

  it('save sends base preferences and AI platform config', async () => {
    const store = useAppStore()
    store.settings = { rub_cny: 0.1, contract_currency: 'CNY', ai_platforms: [] }
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({
      settings: { rub_cny: 0.11, contract_currency: 'RUB', ai_platforms: [] },
      status: {},
      paths: {},
    })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    w.vm.form.contract_currency = 'RUB'
    w.vm.form.rub_cny = 0.11
    w.vm.aiPlatforms.push({ name: 'P1', base: 'https://ai.test/v1', key: 'KEY', key_saved: false })
    await w.vm.save()
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({
      contract_currency: 'RUB',
      rub_cny: 0.11,
      ai_platforms: [expect.objectContaining({ name: 'P1', base: 'https://ai.test/v1', key: 'KEY' })],
    }))
    expect(store.settings.contract_currency).toBe('RUB')
  })
})
