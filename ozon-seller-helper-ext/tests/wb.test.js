import { describe, it, expect } from 'vitest'
import OzonHelperWb from '../common/wb.js'

const { nmFromUrl, isWbProductPage, priceCandidateUrls, parseWbPrice,
        volPart, imageUrls, parseCard, basketCardUrls, cardJsonUrlFromEntries,
        variantIds, productVideoUrl } = OzonHelperWb

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

  it('uses every WB gallery image to build rich content', () => {
    const card = {
      imt_name: 'WB item',
      description: 'WB description',
      media: { photo_count: 3 }
    }
    const d = parseCard(card, 'basket-05.wbbasket.ru', '95070213')
    const expectedImages = [
      'https://basket-05.wbbasket.ru/vol950/part95070/95070213/images/big/1.webp',
      'https://basket-05.wbbasket.ru/vol950/part95070/95070213/images/big/2.webp',
      'https://basket-05.wbbasket.ru/vol950/part95070/95070213/images/big/3.webp'
    ]

    expect(d.images).toEqual(expectedImages)
    expect(d.rich_content_json.version).toBe(0.3)
    expect(d.rich_content_json.content).toHaveLength(expectedImages.length)
    expectedImages.forEach((url, idx) => {
      const img = d.rich_content_json.content[idx].blocks[0].img
      expect(img.src).toBe(url)
      expect(img.srcMobile).toBe(url)
    })
    expect(d.source_raw.rich_content_json).toEqual(d.rich_content_json)
  })

  it('keeps WB sibling nm ids as variants and a stable variant_group', () => {
    const card = {
      imt_id: 1021418841,
      nm_id: 883887355,
      imt_name: 'Датчик температуры',
      slug: 'datchik-temperatury',
      subj_root_name: 'Умный дом и безопасность',
      vendor_code: 'СП-00075985',
      contents: 'Датчик, стикер для монтажа',
      data: { subject_id: 1532, subject_root_id: 6259, chrt_ids: [1333493136], tech_size: '0' },
      media: { photo_count: 1 },
      full_colors: [
        { nm_id: 374523268 },
        { nm_id: 884050191 },
        { nm_id: 883887355 }
      ],
      grouped_options: [{ group_name: 'Основная информация', options: [{ name: 'Цвет', value: 'белый' }] }],
      colors: [374523268, 884050191, 883887355]
    }
    const d = parseCard(card, 'basket-39.wildberries.cn', '883887355')
    expect(d.attributes).toContainEqual({ name: 'Артикул', value: '883887355' })
    expect(variantIds(card, '883887355')).toEqual(['374523268', '884050191', '883887355'])
    expect(d.variant_group).toBe('wb-1021418841')
    expect(d.variants).toEqual([
      { sku: '374523268', label: '374523268', link: 'https://www.wildberries.ru/catalog/374523268/detail.aspx', available: true },
      { sku: '884050191', label: '884050191', link: 'https://www.wildberries.ru/catalog/884050191/detail.aspx', available: true },
      { sku: '883887355', label: '883887355', link: 'https://www.wildberries.ru/catalog/883887355/detail.aspx', available: true }
    ])
    expect(d.source_raw.variant_group).toBe('wb-1021418841')
    expect(d.source_raw.variants.length).toBe(3)
    expect(d.source_raw.colors).toEqual(['374523268', '884050191', '883887355'])
    expect(d.source_raw.vendor_code).toBe('СП-00075985')
    expect(d.source_raw.contents).toBe('Датчик, стикер для монтажа')
    expect(d.source_raw.grouped_options).toEqual(card.grouped_options)
    expect(d.source_raw.data).toEqual(card.data)
  })

  it('uses grouped_options drawer features when top-level options are missing', () => {
    const card = {
      imt_name: 'Mini jet fan',
      description: 'Cordless blower',
      media: { photo_count: 1 },
      grouped_options: [{ group_name: 'Extra', options: [
        { name: 'Air speed', value: '62 m/s' },
        { name: 'Battery type', value: 'Li-Ion' }
      ] }]
    }
    const d = parseCard(card, 'mow-basket-cdn-20.geobasket.ru', '1015621667')
    expect(d.attributes).toContainEqual({ name: 'Air speed', value: '62 m/s' })
    expect(d.attributes).toContainEqual({ name: 'Battery type', value: 'Li-Ion' })
    expect(d.source_raw.options).toContainEqual({ name: 'Air speed', value: '62 m/s' })
    expect(d.source_raw.grouped_options).toEqual(card.grouped_options)
  })

  it('extracts WB video URLs when present in nested card payload fields', () => {
    const card = {
      imt_name: 'Mini printer',
      description: 'Test product',
      media: { has_video: true, photo_count: 1 },
      videos: [{ url: 'https://cdn.example.com/video.mp4' }]
    }
    const d = parseCard(card, 'basket-39.wbbasket.ru', '901539901')
    expect(d.video_url).toBe('https://cdn.example.com/video.mp4')
    expect(d.source_raw.has_video).toBe(true)
    expect(d.source_raw.video_url).toBe('https://cdn.example.com/video.mp4')
  })

  it('uses the already loaded WB mp4 resource when the page exposes one', () => {
    const card = {
      imt_name: 'Mini printer',
      description: 'Test product',
      media: { has_video: true, photo_count: 1 }
    }
    const savedPerformance = globalThis.performance
    globalThis.performance = {
      getEntriesByType: () => [
        { name: 'https://example.com/other.js' },
        { name: 'https://videonme-basket-11.wbbasket.ru/vol129/part90154/901541649/mp4/360p/1.mp4' },
        { name: 'https://mow-videofeedback-06-cdn-06.geobasket.ru/a496f298-917a-4230-ac69-03d77da254ca/preview.webp' }
      ]
    }
    try {
      const d = parseCard(card, 'basket-39.wbbasket.ru', '901541649')
      expect(d.video_url).toBe('https://videonme-basket-11.wbbasket.ru/vol129/part90154/901541649/mp4/360p/1.mp4')
      expect(d.source_raw.has_video).toBe(true)
      expect(d.source_raw.video_url).toBe('https://videonme-basket-11.wbbasket.ru/vol129/part90154/901541649/mp4/360p/1.mp4')
    } finally {
      globalThis.performance = savedPerformance
    }
  })

  it('builds the WB product mp4 URL when card only marks that video exists', () => {
    const card = {
      imt_name: 'Mini printer',
      description: 'Test product',
      media: { has_video: true, photo_count: 1 }
    }
    const savedPerformance = globalThis.performance
    globalThis.performance = { getEntriesByType: () => [] }
    try {
      const d = parseCard(card, 'basket-39.wbbasket.ru', '901541649')
      expect(d.video_url).toBe('https://videonme-basket-11.wbbasket.ru/vol129/part90154/901541649/mp4/360p/1.mp4')
      expect(d.video_url).toBe(productVideoUrl('901541649'))
      expect(d.source_raw.has_video).toBe(true)
      expect(d.source_raw.video_url).toBe(d.video_url)
    } finally {
      globalThis.performance = savedPerformance
    }
  })
})

describe('basketCardUrls', () => {
  it('生成有序候选(估算起点优先) + 路径正确', () => {
    const cands = basketCardUrls('123456789')
    expect(cands.length).toBeGreaterThan(50)
    expect(cands[0].url).toMatch(/^https:\/\/basket-\d{2}\.wbbasket\.ru\/vol1234\/part123456\/123456789\/info\/ru\/card\.json$/)
  })
  it('prefers current geobasket card.json CDN for high nm ids', () => {
    const cands = basketCardUrls('1104961760')
    expect(cands[0]).toEqual({
      host: 'mow-basket-cdn-22.geobasket.ru',
      url: 'https://mow-basket-cdn-22.geobasket.ru/vol11049/part1104961/1104961760/info/ru/card.json'
    })
    expect(cands.some((c) => c.host === 'basket-50.wbbasket.ru')).toBe(true)
  })

  it('prefers the legacy basket host used by older WB vol ranges', () => {
    const cands = basketCardUrls('95070213')
    expect(cands[0]).toEqual({
      host: 'basket-05.wbbasket.ru',
      url: 'https://basket-05.wbbasket.ru/vol950/part95070/95070213/info/ru/card.json'
    })
    expect(cands.filter((c) => c.host === 'basket-05.wbbasket.ru')).toHaveLength(1)
  })
})

describe('cardJsonUrlFromEntries', () => {
  it('finds the real card.json URL loaded by the current WB page', () => {
    const entries = [
      { name: 'https://static-basket-01.wb.ru/x.js' },
      { name: 'https://mow-basket-cdn-22.geobasket.ru/vol11049/part1104961/1104961760/info/ru/card.json' }
    ]
    expect(cardJsonUrlFromEntries(entries, '1104961760')).toBe(
      'https://mow-basket-cdn-22.geobasket.ru/vol11049/part1104961/1104961760/info/ru/card.json'
    )
  })

  it('does not match card.json URLs for other nm ids', () => {
    const entries = [
      { name: 'https://mow-basket-cdn-22.geobasket.ru/vol11049/part1104961/1104961760/info/ru/card.json' }
    ]
    expect(cardJsonUrlFromEntries(entries, '1104961759')).toBeNull()
  })

  it('ignores failed English card.json probes and keeps the Russian payload URL', () => {
    const entries = [
      { name: 'https://basket-05.wbbasket.ru/vol950/part95070/95070213/info/en/card.json' },
      { name: 'https://basket-05.wbbasket.ru/vol950/part95070/95070213/info/ru/card.json' }
    ]
    expect(cardJsonUrlFromEntries(entries, '95070213')).toBe(
      'https://basket-05.wbbasket.ru/vol950/part95070/95070213/info/ru/card.json'
    )
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
