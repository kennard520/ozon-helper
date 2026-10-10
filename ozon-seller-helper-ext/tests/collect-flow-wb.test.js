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
      applyRubToCny: (data, rate) => ({
        price: Math.round(Number(data.price) * rate * 100) / 100,
        old_price: Math.round(Number(data.old_price) * rate * 100) / 100
      })
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
      'https://www.wildberries.ru/catalog/374523268/detail.aspx?targetUrl=MI',
      'https://www.wildberries.ru/catalog/884050191/detail.aspx?targetUrl=MI',
      'https://www.wildberries.ru/catalog/883887355/detail.aspx?targetUrl=MI'
    ])
    expect(collected.map((p) => p.data.source_raw.sku_id)).toEqual(['374523268', '884050191', '883887355'])
    expect(collected.map((p) => p.data.variant_group)).toEqual(['wb-1021418841', 'wb-1021418841', 'wb-1021418841'])
    expect(collected[0].data.source_raw.variants.length).toBe(3)
    expect(collected[0].data.source_raw.variants.map((v) => v.sku)).toEqual(['374523268', '884050191', '883887355'])
    expect(collected[0].data.source_raw.variants.map((v) => v.link)).toEqual([
      'https://www.wildberries.ru/catalog/374523268/detail.aspx?targetUrl=MI',
      'https://www.wildberries.ru/catalog/884050191/detail.aspx?targetUrl=MI',
      'https://www.wildberries.ru/catalog/883887355/detail.aspx?targetUrl=MI'
    ])
    expect(collected.map((p) => p.data.price)).toEqual(['240', '240', '240'])
    expect(collected.map((p) => p.data.old_price)).toEqual(['720', '720', '720'])
    expect(collected.map((p) => p.data.source_raw.wb_price_rule)).toEqual([
      'cny_x3_sale_old_x3_v2',
      'cny_x3_sale_old_x3_v2',
      'cny_x3_sale_old_x3_v2'
    ])
  })

  it('applies WB pricing multiplier when collecting a single WB draft', async () => {
    const collected = []
    globalThis.OzonHelperBridge = {
      bgCall: vi.fn(async (type, payload) => {
        if (type === 'ping') return { ok: true, data: { rub_cny: 0.08 } }
        if (type === 'wbResolveCard') {
          return {
            ok: true,
            data: {
              card: { nm_id: payload.nm, imt_name: 'Door sensor', media: { photo_count: 1 } },
              host: 'basket-39.wildberries.cn'
            }
          }
        }
        if (type === 'collectParsed') {
          collected.push(payload)
          return { ok: true, data: { created: [{ id: 1 }] } }
        }
        return { ok: true, data: {} }
      })
    }
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ data: { products: [{ sizes: [{ price: { product: 100000, basic: 120000 } }] }] } })
    }))

    await globalThis.OzonHelperCollect.collectWbAndEdit(
      '883887355',
      'https://www.wildberries.ru/catalog/883887355/detail.aspx?targetUrl=MI'
    )

    expect(collected).toHaveLength(1)
    expect(collected[0].data.price).toBe('240')
    expect(collected[0].data.old_price).toBe('720')
    expect(collected[0].data.source_raw.wb_price_rule).toBe('cny_x3_sale_old_x3_v2')
  })

  it('stores only successfully resolved WB variant sku values in each collected draft', async () => {
    const cards = {
      439586877: {
        imt_id: 357187556,
        nm_id: 439586877,
        imt_name: 'Bag black',
        media: { photo_count: 1 },
        colors: [415891827, 898474694, 907694946, 539200399, 439586877, 1179847618]
      },
      415891827: { imt_id: 357187556, nm_id: 415891827, imt_name: 'Bag white', media: { photo_count: 1 } },
      898474694: { imt_id: 357187556, nm_id: 898474694, imt_name: 'Bag red', media: { photo_count: 1 } },
      539200399: { imt_id: 357187556, nm_id: 539200399, imt_name: 'Bag green', media: { photo_count: 1 } }
    }
    const collected = []
    globalThis.OzonHelperBridge = {
      bgCall: vi.fn(async (type, payload) => {
        if (type === 'ping') return { ok: true, data: { rub_cny: 0.08 } }
        if (type === 'wbResolveCard') {
          const card = cards[payload.nm]
          return card ? { ok: true, data: { card, host: 'basket-39.wildberries.cn' } } : { ok: false, error: 'missing' }
        }
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
      'https://www.wildberries.ru/catalog/439586877/detail.aspx?targetUrl=MI',
      { spacingMs: 0 }
    )

    expect(res).toEqual({ collected: 4, stopped: false })
    expect(collected.map((p) => p.data.source_raw.sku_id)).toEqual(['415891827', '898474694', '539200399', '439586877'])
    for (const payload of collected) {
      expect(payload.data.source_raw.variants.map((v) => v.sku)).toEqual(['415891827', '898474694', '539200399', '439586877'])
      expect(payload.data.source_raw.variants.map((v) => v.link)).toEqual([
        'https://www.wildberries.ru/catalog/415891827/detail.aspx?targetUrl=MI',
        'https://www.wildberries.ru/catalog/898474694/detail.aspx?targetUrl=MI',
        'https://www.wildberries.ru/catalog/539200399/detail.aspx?targetUrl=MI',
        'https://www.wildberries.ru/catalog/439586877/detail.aspx?targetUrl=MI'
      ])
    }
  })
})
