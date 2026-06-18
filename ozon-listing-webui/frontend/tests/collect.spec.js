import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Collect from '../src/views/Collect.vue'
import { api } from '../src/api.js'
import { useAppStore } from '../src/stores/app.js'

beforeEach(() => {
  setActivePinia(createPinia())
  // onMounted 会 loadWarehouses；默认桩成空，需要数据的用例自行覆盖。
  vi.spyOn(api, 'listWarehouses').mockResolvedValue({ warehouses: [] })
  // onMounted 还会 store.loadDrafts()→listDrafts；默认桩，避免打真实 fetch 报 unhandled rejection。
  vi.spyOn(api, 'listDrafts').mockResolvedValue({ drafts: [], total: 0, counts: {} })
})
afterEach(() => vi.restoreAllMocks())

describe('Collect.vue', () => {
  it('删除已发布草稿只清本地并提示不会删除 Ozon 线上商品', async () => {
    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    const confirmSpy = vi.fn().mockResolvedValue(true)
    w.vm.confirmFn = confirmSpy
    vi.spyOn(api, 'deleteDraft').mockResolvedValue({ deleted: true, ozon_deleted: false, drafts: [] })
    await w.vm.doDelete([{ id: 1, status: 'published' }])
    expect(confirmSpy.mock.calls[0][0]).toContain('不会删除 Ozon 线上商品')
    expect(api.deleteDraft).toHaveBeenCalledWith(1)
  })

  it('批量设置库存/仓库：调 batchUpdateDrafts 并刷新草稿', async () => {
    vi.spyOn(api, 'batchUpdateDrafts').mockResolvedValue({ updated: [{ id: 1 }, { id: 2 }], errors: [] })
    vi.spyOn(api, 'listDrafts').mockResolvedValue({ drafts: [] })
    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    await w.vm.doBatchUpdate({ ids: [1, 2], patch: { stock: 50 } })
    expect(api.batchUpdateDrafts).toHaveBeenCalledWith([1, 2], { stock: 50 })
    expect(api.listDrafts).toHaveBeenCalled()
  })

  it('批量发布：确认后调 batchPublish 并刷新草稿', async () => {
    vi.spyOn(api, 'batchPublish').mockResolvedValue({ published: 2, failed: 0, results: [] })
    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    w.vm.confirmFn = vi.fn().mockResolvedValue(true)
    await w.vm.doBatchPublish([1, 2])
    expect(api.batchPublish).toHaveBeenCalled()
    expect(api.batchPublish.mock.calls[0][0]).toEqual([1, 2])
  })

  it('挂载时加载仓库列表', async () => {
    api.listWarehouses.mockResolvedValue({ warehouses: [{ warehouse_id: 7, name: '成都仓' }] })
    const w = mount(Collect, { global: { plugins: [ElementPlus] } })
    await w.vm.loadWarehouses()
    expect(api.listWarehouses).toHaveBeenCalled()
    expect(w.vm.warehouses).toHaveLength(1)
  })
})
