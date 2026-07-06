import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OzonHelperWb from '../common/wb.js'
import '../common/collect-flow.js'

describe('collectAllWbVariants', () => {
  const old = {}

  beforeEach(() => {
    old.fetch = globalThis.fetch
    old.OzonHelperWb = globalThis.OzonHelperWb
    old.OzonHelperBridge = globalThis.OzonHelperBridge
    old.OzonHelperProduct = globalThis.OzonHelperProduct
    old.OzonHelperSite = globalThis.OzonHelperSite
    old.location = globalThis.location

    globalThis.OzonHelperWb = OzonHelperWb
    globalThis.OzonHelperProduct = {
      applyRubToCny: (data) => data
    }
    globalThis.OzonHelperSite = {
      detectSite: () => 'wb',
      currencyOf: () => 'RUB'
    }
    globalThis.location = { hostname: 'www.wildberries.ru' }
  })

  afterEach(() => {
    globalThis.fetch = old.fetch
    globalThis.OzonHelperWb = old.OzonHelperWb
    globalThis.OzonHelperBridge = old.OzonHelperBridge
    globalThis.OzonHelperProduct = old.OzonHelperProduct
    globalThis.OzonHelperSite = old.OzonHelperSite
    globalThis.location = old.location
    vi.restoreAllMocks()
  })

  it('collects each WB full_colors nm id as a separate draft in one variant_group', async () => {
    const cards = {
      883887355: {
        imt_id: 1021418841,
        nm_id: 883887355,
        imt_name: 'Current sensor',
        media: { photo_count: 1 },
        full_colors: [{ nm_id: 374523268 }, { nm_id: 884050191 }, { nm_id: 883887355 }]
      },
      374523268: { imt_id: 1021418841, nm_id: 374523268, imt_name: 'Door sensor', media: { photo_count: 1 } },
      884050191: { imt_id: 1021418841, nm_id: 884050191, imt_name: 'Window sensor', media: { photo_count: 1 } }
    }
    const collected = []
    globalThis.OzonHelperBridge = {
      bgCall: vi.fn(async (type, payload) => {
        if (type === 'ping') return { ok: true, data: { rub_cny: 0.08 } }
        if (type === 'wbResolveCard') return { ok: true, data: { card: cards[payload.nm], host: 'basket-39.wildberries.cn' } }
        if (type === 'collectParsed') {
          collected.push(payload)
          return { ok: true, data: { created: [{ id: collected.length }] } }
        }
        return { ok: true, data: {} }
      })
    }
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ data: { products: [{ sizes: [{ price: { product: 100000, basic: 120000 } }] }] } })
    }))

    const res = await globalThis.OzonHelperCollect.collectAllWbVariants(
      'https://www.wildberries.ru/catalog/883887355/detail.aspx?targetUrl=MI',
      { spacingMs: 0 }
    )

    expect(res).toEqual({ collected: 3, stopped: false })
    expect(collected.map((p) => p.url)).toEqual([
      'https://www.wildberries.ru/catalog/374523268/detail.aspx',
      'https://www.wildberries.ru/catalog/884050191/detail.aspx',
      'https://www.wildberries.ru/catalog/883887355/detail.aspx'
    ])
    expect(collected.map((p) => p.data.variant_group)).toEqual(['wb-1021418841', 'wb-1021418841', 'wb-1021418841'])
    expect(collected[0].data.source_raw.variants.length).toBe(3)
  })
})
