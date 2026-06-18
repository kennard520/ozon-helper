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

describe('Collect.vue 发布目标店', () => {
  it('默认选中 last_publish_store（店2=222），确认发布时 api.publish 带 store_client_id=222', async () => {
    const store = useAppStore()
    store.settings = {
      ozon_client_id: '111',
      ozon_stores: [{ name: '店2', client_id: '222', api_key_saved: true }],
      last_publish_store: '222',
    }
    // 给 store 放一个 draft
    store.drafts = [{ id: 9, status: 'ready', ozon_title: 'T', source: '1688', offer_id: 'X' }]
    store.selectedId = 9

    const publishSpy = vi.spyOn(api, 'publish').mockResolvedValue({
      published: true, draft: { id: 9, status: 'published' }, errors: [], poll: {}, response: {}, task_id: null,
    })
    vi.spyOn(api, 'publishPreview').mockResolvedValue({ ok: true, errors: [], summary: {} })

    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    // 替换确认函数为自动确认
    w.vm.confirmFn = vi.fn().mockResolvedValue(true)

    await w.vm.doPublish(store.selectedDraft)
    await flushPromises()

    // publishPreview 应带上目标店 client_id
    expect(api.publishPreview).toHaveBeenCalledWith(9, '222')
    // publish 应带上目标店 client_id
    expect(publishSpy).toHaveBeenCalledWith(9, '222')
  })

  it('storeOptions 来自统一列表不重复，默认店标默认且默认选中', async () => {
    const store = useAppStore()
    store.settings = {
      ozon_client_id: '1',
      last_publish_store: '',
      ozon_stores: [
        { name: '主店', client_id: '1', is_default: true, api_key_saved: true },
        { name: '店2', client_id: '2', is_default: false, api_key_saved: true },
      ],
    }

    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    await flushPromises()

    const opts = w.vm.storeOptions
    expect(opts.length).toBe(2)
    expect(opts.map(o => o.value)).toEqual(['1', '2'])
    const def = opts.find(o => o.value === '1')
    expect(def.label).toContain('默认')
    expect(w.vm.selectedStore).toBe('1')
  })

  it('只有主店（无额外店）时下拉不影响，publish 仍正常调用（传主店或 undefined）', async () => {
    const store = useAppStore()
    store.settings = {
      ozon_client_id: '111',
      ozon_stores: [],
      last_publish_store: '',
    }
    store.drafts = [{ id: 5, status: 'ready', ozon_title: 'T', source: '1688', offer_id: 'Y' }]
    store.selectedId = 5

    const publishSpy = vi.spyOn(api, 'publish').mockResolvedValue({
      published: true, draft: { id: 5, status: 'published' }, errors: [], poll: {}, response: {}, task_id: null,
    })
    vi.spyOn(api, 'publishPreview').mockResolvedValue({ ok: true, errors: [], summary: {} })

    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    w.vm.confirmFn = vi.fn().mockResolvedValue(true)

    await w.vm.doPublish(store.selectedDraft)
    await flushPromises()

    // 只有主店时 selectedStore 为主店 id 或空，两种都可接受
    expect(publishSpy).toHaveBeenCalledWith(5, expect.anything())
  })
})
