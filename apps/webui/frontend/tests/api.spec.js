import { describe, it, expect, vi, beforeEach } from 'vitest'
import { api } from '../src/api.js'

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ drafts: [] }) }))
})

describe('api', () => {
  it('listDrafts 打 GET /api/drafts', async () => {
    const r = await api.listDrafts()
    expect(global.fetch).toHaveBeenCalledWith('/api/drafts', expect.objectContaining({ method: 'GET' }))
    expect(r).toEqual({ drafts: [] })
  })

  it('patchDraft 打 PATCH 且带 JSON body', async () => {
    await api.patchDraft(7, { stock: 5 })
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/drafts/7')
    expect(opts.method).toBe('PATCH')
    expect(JSON.parse(opts.body)).toEqual({ stock: 5 })
    expect(opts.headers['Content-Type']).toBe('application/json')
  })

  it('categorySearch 带 query 编码', async () => {
    await api.categorySearch('收纳 箱', 50)
    expect(global.fetch.mock.calls[0][0]).toBe('/api/category/search?q=%E6%94%B6%E7%BA%B3%20%E7%AE%B1&limit=50')
  })

  it('categoryTree 打 GET /api/category/tree', async () => {
    await api.categoryTree()
    expect(global.fetch).toHaveBeenCalledWith('/api/category/tree', expect.objectContaining({ method: 'GET' }))
  })
})
