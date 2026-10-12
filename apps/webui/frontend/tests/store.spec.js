import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { useAppStore } from '../src/stores/app.js'
import { api } from '../src/api.js'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

beforeEach(() => { setActivePinia(createPinia()) })

describe('app store', () => {
  it('loadDrafts 拉取当前页并写入分页元数据', async () => {
    vi.spyOn(api, 'listDrafts').mockResolvedValue({
      drafts: [{ id: 1, status: 'ready' }], total: 1, page: 1, page_size: 20,
      counts: { all: 1, ready: 1, invalid: 0, failed: 0, published: 0 },
    })
    const s = useAppStore()
    await s.loadDrafts()
    expect(s.drafts).toHaveLength(1)
    expect(s.total).toBe(1)
    expect(s.counts.ready).toBe(1)
  })

  it('filteredDrafts 直接返回当前页（后端已过滤）', async () => {
    const s = useAppStore()
    s.drafts = [{ id: 1, status: 'ready' }, { id: 2, status: 'invalid' }]
    expect(s.filteredDrafts).toHaveLength(2)
  })

  it('counts 走后端 serverCounts', () => {
    const s = useAppStore()
    s.serverCounts = { all: 3, ready: 2, published: 1, invalid: 0, failed: 0 }
    expect(s.counts.ready).toBe(2)
    expect(s.counts.all).toBe(3)
  })

  it('setFilter 重置到第 1 页并重新加载', async () => {
    const spy = vi.spyOn(api, 'listDrafts').mockResolvedValue({ drafts: [], total: 0, counts: {} })
    const s = useAppStore()
    s.page = 3
    await s.setFilter('published')
    expect(s.filter).toBe('published')
    expect(s.page).toBe(1)
    expect(spy).toHaveBeenCalledWith({ status: 'published', page: 1, page_size: 20, store_client_id: '' })
  })

  it('setPage / setPageSize 触发加载', async () => {
    const spy = vi.spyOn(api, 'listDrafts').mockResolvedValue({ drafts: [], total: 0, counts: {} })
    const s = useAppStore()
    await s.setPage(2)
    expect(s.page).toBe(2)
    await s.setPageSize(50)
    expect(s.pageSize).toBe(50)
    expect(s.page).toBe(1)  // 改页大小回到第 1 页
    expect(spy).toHaveBeenCalled()
  })

  it('切店后忽略旧店晚到的草稿列表响应', async () => {
    const oldStoreResponse = deferred()
    const newStoreResponse = deferred()
    const spy = vi.spyOn(api, 'listDrafts')
      .mockImplementationOnce(() => oldStoreResponse.promise)
      .mockImplementationOnce(() => newStoreResponse.promise)
    const s = useAppStore()
    s.currentStore = 'store-7'

    const oldLoad = s.loadDrafts()
    s.setCurrentStore('store-8')

    expect(spy.mock.calls[0][0].store_client_id).toBe('store-7')
    expect(spy.mock.calls[1][0].store_client_id).toBe('store-8')

    newStoreResponse.resolve({
      drafts: [{ id: 99, store_client_id: 'store-8' }],
      total: 1,
      page: 1,
      page_size: 20,
      counts: { all: 1, ready: 1, invalid: 0, failed: 0, published: 0 },
    })
    await flushPromises()
    expect(s.drafts).toEqual([{ id: 99, store_client_id: 'store-8' }])

    oldStoreResponse.resolve({
      drafts: [{ id: 42, store_client_id: 'store-7' }],
      total: 1,
      page: 1,
      page_size: 20,
      counts: { all: 1, ready: 0, invalid: 0, failed: 0, published: 1 },
    })
    await oldLoad

    expect(s.currentStore).toBe('store-8')
    expect(s.drafts).toEqual([{ id: 99, store_client_id: 'store-8' }])
    expect(s.counts.ready).toBe(1)
  })

  it('upsertDraft 命中页内则就地更新并返回 true', () => {
    const s = useAppStore()
    s.drafts = [{ id: 1, ozon_title: 'A' }, { id: 2, ozon_title: 'B' }]
    const hit = s.upsertDraft({ id: 2, ozon_title: 'B2' })
    expect(hit).toBe(true)
    expect(s.drafts[1].ozon_title).toBe('B2')
    expect(s.drafts).toHaveLength(2)
  })

  it('upsertDraft 未命中不插入（后端分页：新草稿交给 loadDrafts），返回 false', () => {
    const s = useAppStore()
    s.drafts = [{ id: 1, ozon_title: 'A' }]
    const hit = s.upsertDraft({ id: 99, ozon_title: 'NEW' })
    expect(hit).toBe(false)
    expect(s.drafts).toHaveLength(1)   // 不撑破当前页
  })
})
