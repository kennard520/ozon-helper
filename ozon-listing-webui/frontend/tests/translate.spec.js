import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DraftDetail from '../src/components/DraftDetail.vue'
import Settings from '../src/views/Settings.vue'
import { api } from '../src/api.js'

const draft = {
  id: 7, source_platform: '1688', source_title: '收纳箱', ozon_title: '收纳箱',
  category_id: '', type_id: '', price: '', stock: 0, images: [],
  weight_g: 0, length_mm: 0, width_mm: 0, height_mm: 0,
  supplier: '', offer_id: '', attributes: [], validation_errors: [],
}

beforeEach(() => setActivePinia(createPinia()))

describe('DraftDetail 翻译', () => {
  it('doTranslate 调用接口并把译文回填到 form', async () => {
    vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], missing: [], errors: [] })
    vi.spyOn(api, 'patchDraft').mockResolvedValue({ draft: { ...draft } })
    const spy = vi.spyOn(api, 'translateDraft').mockResolvedValue({
      draft: { ...draft, ozon_title: 'Коробка для хранения' },
      engine: 'glossary',
      still_cjk: false,
    })
    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    await w.vm.doTranslate()
    expect(spy).toHaveBeenCalledWith(7)
    expect(w.vm.form.ozon_title).toBe('Коробка для хранения')
  })
})

describe('DraftDetail doTranslate 先保存再翻译', () => {
  it('doTranslate 调用 patchDraft(含unsaved描述) BEFORE translateDraft', async () => {
    vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], missing: [], errors: [] })
    const patchSpy = vi.spyOn(api, 'patchDraft').mockResolvedValue({ draft: { ...draft } })
    const translateSpy = vi.spyOn(api, 'translateDraft').mockResolvedValue({
      draft: { ...draft, ozon_title: 'Коробка' },
      engine: 'glossary',
      still_cjk: false,
    })
    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    w.vm.form.description = '新描述'
    await w.vm.doTranslate()
    expect(patchSpy).toHaveBeenCalled()
    expect(patchSpy.mock.calls[0][1]).toMatchObject({ description: '新描述' })
    // patchDraft must be invoked before translateDraft
    expect(patchSpy.mock.invocationCallOrder[0]).toBeLessThan(translateSpy.mock.invocationCallOrder[0])
    expect(w.vm.form.ozon_title).toBe('Коробка')
  })
})

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
