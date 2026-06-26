import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Collect from '../src/views/Collect.vue'
import { api } from '../src/api.js'
import { useAppStore } from '../src/stores/app.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: [] })
  vi.spyOn(api, 'listDrafts').mockResolvedValue({ drafts: [], total: 0, counts: {} })
})
afterEach(() => vi.restoreAllMocks())

describe('Collect.vue 发布缺必填属性警告', () => {
  it('preview 有 warnings → 确认弹窗 HTML 列出警告，且用户确认后仍发布', async () => {
    const store = useAppStore()
    store.settings = { ozon_client_id: '111', ozon_stores: [], last_publish_store: '' }
    store.drafts = [{ id: 7, status: 'ready', ozon_title: 'T', source: '1688', offer_id: 'Z' }]
    store.selectedId = 7

    vi.spyOn(api, 'publishPreview').mockResolvedValue({
      ok: true, errors: [], warnings: ['缺必填属性：Цвет товара'], summary: { offer_id: 'Z' },
    })
    const publishSpy = vi.spyOn(api, 'publish').mockResolvedValue({
      published: true, draft: { id: 7, status: 'published' }, errors: [], warnings: [], poll: {}, response: {}, task_id: null,
    })

    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    const confirmSpy = vi.fn().mockResolvedValue(true)
    w.vm.confirmFn = confirmSpy

    await w.vm.doPublish(store.selectedDraft)
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalled()
    const html = confirmSpy.mock.calls[0][0]
    expect(html).toContain('缺必填属性：Цвет товара')
    expect(publishSpy).toHaveBeenCalled()   // 警告不拦，确认后照发
  })
})
