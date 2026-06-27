import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

// mock api
vi.mock('../api.js', () => ({
  api: {
    analyticsDashboard: vi.fn(),
    analyticsTraffic: vi.fn(),
    analyticsKeywords: vi.fn(),
  }
}))

// mock app store
vi.mock('../stores/app.js', () => ({
  useAppStore: vi.fn(() => ({
    settings: {
      ozon_stores: [
        { client_id: 'c1', name: '店铺A', is_default: true },
        { client_id: 'c2', name: '店铺B', is_default: false },
      ]
    }
  }))
}))

import { api } from '../api.js'
import { useAnalytics } from './useAnalytics.js'

const DASH = {
  store: 'c1', date_from: '2026-05-28', date_to: '2026-06-27',
  grand_total: { sku_count: 2, exposure: 1000, sessions: 200, cart: 50, ordered_units: 10, revenue: 5000, conv_cart_pct: 5, sku_with_traffic: 2 },
  rows: [
    { sku: 101, offer_id: 'OFF1', title: '商品A', price: 100, stock: 5, exposure: 600, sessions: 120, cart: 30, conv_cart_pct: 4, ordered_units: 6, revenue: 600, diagnostics: [] },
    { sku: 102, offer_id: 'OFF2', title: '商品B', price: 200, stock: 0, exposure: 400, sessions: 80, cart: 20, conv_cart_pct: 6, ordered_units: 4, revenue: 800, diagnostics: ['缺货'] },
  ],
  degraded: false
}

const TRAFFIC = { rows: [{ sku: 101, day: '2026-06-27', hits_view: 50, session_view: 20, hits_tocart: 5, ordered_units: 1 }] }
const KEYWORDS = { by_sku: { '101': [{ query: '红杯', searches: 1000, ctr: 0.05, position: 3, orders: 10, gmv: 1000 }] } }

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  api.analyticsDashboard.mockResolvedValue(DASH)
  api.analyticsTraffic.mockResolvedValue(TRAFFIC)
  api.analyticsKeywords.mockResolvedValue(KEYWORDS)
})

describe('useAnalytics', () => {
  it('初始化：storeList 从 appStore.settings.ozon_stores', () => {
    const a = useAnalytics()
    expect(a.storeList.value.length).toBe(2)
    expect(a.storeList.value[0].name).toBe('店铺A')
  })

  it('load 调 analyticsDashboard 并填充 dashboard', async () => {
    const a = useAnalytics()
    await a.load()
    expect(api.analyticsDashboard).toHaveBeenCalledOnce()
    const args = api.analyticsDashboard.mock.calls[0][0]
    expect(args).toHaveProperty('date_from')
    expect(args).toHaveProperty('date_to')
    expect(a.dashboard.value).toEqual(DASH)
    expect(a.loading.value).toBe(false)
    expect(a.error.value).toBe('')
  })

  it('切 traffic tab 懒拉 analyticsTraffic', async () => {
    const a = useAnalytics()
    await a.load()
    expect(api.analyticsTraffic).not.toHaveBeenCalled()
    await a.loadTab('traffic')
    expect(api.analyticsTraffic).toHaveBeenCalledOnce()
    expect(a.traffic.value).toEqual(TRAFFIC)
    // 再切同一 tab 不重复拉
    await a.loadTab('traffic')
    expect(api.analyticsTraffic).toHaveBeenCalledOnce()
  })

  it('切 keyword tab 懒拉 analyticsKeywords', async () => {
    const a = useAnalytics()
    await a.load()
    await a.loadTab('keyword')
    expect(api.analyticsKeywords).toHaveBeenCalledOnce()
    expect(a.keywords.value).toEqual(KEYWORDS)
  })

  it('setRange 清空 traffic/keywords 并重拉 dashboard', async () => {
    const a = useAnalytics()
    await a.load()
    await a.loadTab('traffic')
    expect(a.traffic.value).toEqual(TRAFFIC)

    api.analyticsDashboard.mockResolvedValue({ ...DASH, date_from: '2026-06-20' })
    await a.setRange('7')

    expect(a.traffic.value).toBeNull()
    expect(a.keywords.value).toBeNull()
    expect(api.analyticsDashboard).toHaveBeenCalledTimes(2)
    expect(a.dateRange.value.preset).toBe('7')
  })

  it('缺凭证 400 → error 友好提示，dashboard 为 null', async () => {
    api.analyticsDashboard.mockRejectedValue(
      Object.assign(new Error('未配置 Ozon 店铺凭证'), { status: 400, data: { detail: '未配置 Ozon 店铺凭证' } })
    )
    const a = useAnalytics()
    await a.load()
    expect(a.dashboard.value).toBeNull()
    expect(a.error.value).toContain('Ozon 店铺凭证')
    expect(a.loading.value).toBe(false)
  })

  it('exportCsv 从 dashboard.rows 生成含表头 CSV', async () => {
    const a = useAnalytics()
    await a.load()
    // 捕获传给 Blob 的内容
    let capturedContent = ''
    const OrigBlob = globalThis.Blob
    vi.stubGlobal('Blob', class FakeBlob {
      constructor(parts) { capturedContent = parts.join('') }
      text() { return Promise.resolve(capturedContent) }
    })

    const mockA = { href: '', download: '', click: vi.fn() }
    vi.spyOn(document, 'createElement').mockReturnValue(mockA)
    vi.spyOn(document.body, 'appendChild').mockImplementation(() => {})
    vi.spyOn(document.body, 'removeChild').mockImplementation(() => {})
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:mock'),
      revokeObjectURL: vi.fn(),
    })

    a.exportCsv()

    // 验证下载触发
    expect(mockA.click).toHaveBeenCalled()
    expect(mockA.download).toContain('analytics_')
    expect(mockA.download).toContain('.csv')

    // 验证 CSV 内容
    expect(capturedContent).toContain('SKU')
    expect(capturedContent).toContain('商品名')
    expect(capturedContent).toContain('101')
    expect(capturedContent).toContain('商品A')
    expect(capturedContent).toContain('102')
    expect(capturedContent).toContain('缺货')

    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('activeTab 初始值为 product', () => {
    const a = useAnalytics()
    expect(a.activeTab.value).toBe('product')
  })
})
