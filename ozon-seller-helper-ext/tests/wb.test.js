import { describe, it, expect } from 'vitest'
import OzonHelperWb from '../common/wb.js'

const { nmFromUrl, isWbProductPage, priceCandidateUrls, parseWbPrice,
        volPart, imageUrls, parseCard, basketCardUrls } = OzonHelperWb

describe('volPart', () => {
  it('nm → vol/part', () => {
    expect(volPart('123456789')).toEqual({ vol: 1234, part: 123456 })
  })
})

describe('imageUrls', () => {
  it('按 photo_count 生成 big webp 列表', () => {
    const urls = imageUrls('basket-19.wbbasket.ru', 1234, 123456, '123456789', 3)
    expect(urls.length).toBe(3)
    expect(urls[0]).toBe('https://basket-19.wbbasket.ru/vol1234/part123456/123456789/images/big/1.webp')
  })
  it('photo_count 0/空 → 至少 1 张', () => {
    expect(imageUrls('h', 1, 1, '1', 0).length).toBe(1)
  })
})

describe('parseCard', () => {
  it('card.json → collect-parsed data（俄语直用，options 进 source_raw，克重尺寸换算）', () => {
    const card = {
      imt_name: 'Сумка женская',
      description: 'Отличная сумка',
      media: { photo_count: 2 },
      selling: { brand_name: 'NoName' },
      subj_name: 'Сумки',
      options: [
        { name: 'Вес товара с упаковкой (г)', value: '0,5 кг' },
        { name: 'Длина упаковки', value: '30 см' },
        { name: 'Ширина упаковки', value: '20 см' },
        { name: 'Высота упаковки', value: '10 см' },
        { name: 'Цвет', value: 'чёрный' }
      ]
    }
    const d = parseCard(card, 'basket-19.wbbasket.ru', '123456789')
    expect(d.source_platform).toBe('wb')
    expect(d.title).toBe('Сумка женская')        // 后端据此填 source_title+ozon_title
    expect(d.description).toBe('Отличная сумка')
    expect(d.weight_g).toBe(500)                   // 0.5 кг → 500 g
    expect(d.length_mm).toBe(300)                  // 30 см → 300 mm
    expect(d.width_mm).toBe(200)
    expect(d.height_mm).toBe(100)
    expect(d.images.length).toBe(2)
    expect(d.source_raw.options.length).toBe(5)    // 5 个名值对喂 auto-map
    expect(d.source_raw.brand_name).toBe('NoName')
    expect(d.price).toBe('')                        // 价后续就地取
  })
})

describe('basketCardUrls', () => {
  it('生成有序候选(估算起点优先) + 路径正确', () => {
    const cands = basketCardUrls('123456789')
    expect(cands.length).toBeGreaterThan(50)
    expect(cands[0].url).toMatch(/^https:\/\/basket-\d{2}\.wbbasket\.ru\/vol1234\/part123456\/123456789\/info\/ru\/card\.json$/)
  })
})

describe('nmFromUrl', () => {
  it('从 /catalog/<数字>/ 提 nmId', () => {
    expect(nmFromUrl('https://www.wildberries.ru/catalog/284168971/detail.aspx?targetUrl=MI')).toBe('284168971')
  })
  it('无 catalog → null', () => {
    expect(nmFromUrl('https://www.wildberries.ru/')).toBeNull()
    expect(nmFromUrl('')).toBeNull()
  })
})

describe('isWbProductPage', () => {
  it('detail.aspx 商品页 → true', () => {
    expect(isWbProductPage('/catalog/284168971/detail.aspx')).toBe(true)
  })
  it('首页/类目页 → false', () => {
    expect(isWbProductPage('/')).toBe(false)
    expect(isWbProductPage('/catalog/elektronika')).toBe(false)
  })
})

describe('priceCandidateUrls', () => {
  it('v4 最前、都含 nm、默认 dest', () => {
    const us = priceCandidateUrls('284168971')
    expect(us.length).toBe(4)
    expect(us[0]).toContain('/cards/v4/detail')
    expect(us[0]).toContain('nm=284168971')
    expect(us[0]).toContain('dest=-1257786')
    expect(us[3]).toContain('/cards/v1/detail')
  })
})

describe('parseWbPrice', () => {
  const j = { data: { products: [{ rating: 5, feedbacks: 70, sizes: [{ price: { basic: 1144000, product: 772200 } }] }] } }
  it('product/100=售价, basic/100=划线价, 带评分/评论', () => {
    expect(parseWbPrice(j)).toEqual({ price_rub: 7722, old_rub: 11440, rating: 5, feedbacks: 70 })
  })
  it('兼容顶层 products[]', () => {
    const j2 = { products: [{ feedbacks: 3, sizes: [{ price: { product: 100000 } }] }] }
    expect(parseWbPrice(j2).price_rub).toBe(1000)
    expect(parseWbPrice(j2).old_rub).toBe('')
  })
  it('basic<=product → 划线价留空', () => {
    const j3 = { products: [{ sizes: [{ price: { basic: 500000, product: 772200 } }] }] }
    expect(parseWbPrice(j3).old_rub).toBe('')
  })
  it('无 product / 无 products / null → null', () => {
    expect(parseWbPrice({ products: [] })).toBeNull()
    expect(parseWbPrice({ products: [{ sizes: [{ price: {} }] }] })).toBeNull()
    expect(parseWbPrice(null)).toBeNull()
  })
})
