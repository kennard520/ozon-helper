import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: {
  listDrafts: vi.fn().mockResolvedValue({ drafts: [], total: 0, counts: {} }),
  listWarehouses: vi.fn().mockResolvedValue({ warehouses: [] }),
  deleteDraft: vi.fn().mockResolvedValue({ ids: [7] }),
  batchUpdateDrafts: vi.fn().mockResolvedValue({ updated: [1], errors: [] }),
  publishPreview: vi.fn().mockResolvedValue({ ok: true, errors: [], warnings: [], summary: {} }),
  publish: vi.fn().mockResolvedValue({ published: true, draft: { id: 9 }, errors: [] }),
  publishGroup: vi.fn().mockResolvedValue({ published: true, count: 3, variant_group: 'G-1' }),
} }))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true), alert: vi.fn().mockResolvedValue(true) },
}))
import { api } from '../api.js'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app.js'
import { useDraftBatchOps } from './useDraftBatchOps.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

describe('useDraftBatchOps', () => {
  it('暴露批量/发布接口', () => {
    const store = useAppStore()
    const ops = useDraftBatchOps(store)
    expect(typeof ops.doBatchUpdate).toBe('function')
    expect(typeof ops.doBatchPublish).toBe('function')
    expect(typeof ops.doDelete).toBe('function')
    expect(typeof ops.doPublishGroup).toBe('function')
    expect(typeof ops.loadWarehouses).toBe('function')
    expect(ops.warehouses).toBeDefined()
  })
  it('doPublishGroup 确认后按当前店铺发布整组并刷新列表', async () => {
    const store = useAppStore()
    store.settings = { ozon_client_id: 'store-1', ozon_stores: [] }
    store.loadDrafts = vi.fn().mockResolvedValue(undefined)
    const ops = useDraftBatchOps(store)

    const result = await ops.doPublishGroup('G-1', 3)

    expect(ops.confirmFn.value).toBeDefined()
    expect(api.publishGroup).toHaveBeenCalledWith('G-1', 'store-1')
    expect(store.loadDrafts).toHaveBeenCalledTimes(1)
    expect(result).toMatchObject({ published: true, count: 3 })
    expect(ops.groupPublishResult.value).toMatchObject({ published: true, count: 3 })
    expect(ops.groupPublishing.value).toBe(false)
  })
  it('doPublishGroup 运行中忽略重复点击', async () => {
    let resolvePublish
    api.publishGroup.mockReturnValueOnce(new Promise((resolve) => { resolvePublish = resolve }))
    const store = useAppStore()
    store.settings = { ozon_client_id: 'store-1', ozon_stores: [] }
    store.loadDrafts = vi.fn()
    const ops = useDraftBatchOps(store)

    const first = ops.doPublishGroup('G-1', 3)
    await vi.waitFor(() => expect(ops.groupPublishing.value).toBe(true))
    await ops.doPublishGroup('G-1', 3)
    await vi.waitFor(() => expect(api.publishGroup).toHaveBeenCalledTimes(1))
    expect(api.publishGroup).toHaveBeenCalledTimes(1)
    resolvePublish({ published: true, count: 3 })
    await first
  })
  it('doPublishGroup 取消确认时不请求接口', async () => {
    const store = useAppStore()
    store.settings = { ozon_client_id: 'store-1', ozon_stores: [] }
    const ops = useDraftBatchOps(store)
    ops.confirmFn.value = vi.fn().mockRejectedValueOnce(new Error('cancel'))

    await ops.doPublishGroup('G-1', 3)

    expect(api.publishGroup).not.toHaveBeenCalled()
  })
  it('doPublishGroup 失败时提示且恢复按钮状态', async () => {
    const store = useAppStore()
    store.settings = { ozon_client_id: 'store-1', ozon_stores: [] }
    api.publishGroup.mockRejectedValueOnce(new Error('group down'))
    const ops = useDraftBatchOps(store)

    await ops.doPublishGroup('G-1', 3)

    expect(ElMessage.error).toHaveBeenCalledWith('整组发布失败：group down')
    expect(ops.groupPublishing.value).toBe(false)
  })
  it('doDelete 确认后按组调 api.deleteDraft + removeDraft', async () => {
    const store = useAppStore()
    store.drafts = [{ id: 7 }]
    const ops = useDraftBatchOps(store)
    await ops.doDelete([{ id: 7 }])
    expect(api.deleteDraft).toHaveBeenCalledWith(7, { scope: 'group' })
    expect(store.drafts.find(d => d.id === 7)).toBeFalsy()
  })
  it('doPublish 预览失败时给出可见错误提示', async () => {
    const store = useAppStore()
    store.settings = { ozon_client_id: 'store-1', ozon_stores: [] }
    api.publishPreview.mockRejectedValueOnce(new Error('preview down'))
    const ops = useDraftBatchOps(store)
    await ops.doPublish({ id: 9 })
    expect(ElMessage.error).toHaveBeenCalledWith('发布预览失败：preview down')
    expect(ops.publishResult.value.errors).toEqual(['预览失败: preview down'])
  })
})
