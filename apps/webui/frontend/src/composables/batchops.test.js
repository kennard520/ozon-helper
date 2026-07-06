import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api.js', () => ({ api: {
  listDrafts: vi.fn().mockResolvedValue({ drafts: [], total: 0, counts: {} }),
  listWarehouses: vi.fn().mockResolvedValue({ warehouses: [] }),
  deleteDraft: vi.fn().mockResolvedValue({ ids: [7] }),
  batchUpdateDrafts: vi.fn().mockResolvedValue({ updated: [1], errors: [] }),
} }))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true), alert: vi.fn().mockResolvedValue(true) },
}))
import { api } from '../api.js'
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
    expect(typeof ops.loadWarehouses).toBe('function')
    expect(ops.warehouses).toBeDefined()
  })
  it('doDelete 确认后按组调 api.deleteDraft + removeDraft', async () => {
    const store = useAppStore()
    store.drafts = [{ id: 7 }]
    const ops = useDraftBatchOps(store)
    await ops.doDelete([{ id: 7 }])
    expect(api.deleteDraft).toHaveBeenCalledWith(7, { scope: 'group' })
    expect(store.drafts.find(d => d.id === 7)).toBeFalsy()
  })
})
