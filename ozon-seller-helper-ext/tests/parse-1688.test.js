// ozon-seller-helper-ext/tests/parse-1688.test.js
import { describe, it, expect } from 'vitest'
import OzonHelperParse1688 from '../common/parse-1688.js'
import OzonHelperMedia from '../common/media-upload.js'

const { extractOfferId } = OzonHelperParse1688
const { parseDetailImages } = OzonHelperParse1688
const { parseSkuRowsFromDom, mergeSkuDomRows } = OzonHelperParse1688

describe('extractOfferId', () => {
  it('从 detail.1688.com/offer/<id>.html 提取 offerId', () => {
    expect(extractOfferId('https://detail.1688.com/offer/795554901999.html?spm=a360q')).toBe('795554901999')
  })
  it('无 offer 段 → 空串', () => {
    expect(extractOfferId('https://www.1688.com/')).toBe('')
    expect(extractOfferId('')).toBe('')
    expect(extractOfferId(null)).toBe('')
  })
})

describe('parseDetailImages', () => {
  const html = '<div><p>详情</p>' +
    '<img src="https://cbu01.alicdn.com/img/ibank/a.jpg?x=1">' +
    "<img src='https://cbu01.alicdn.com/img/ibank/b.png'>" +
    '<img src="https://cbu01.alicdn.com/img/ibank/a.jpg?y=2">' +  // 与第1张去 query 后重复
    '<img src="data:image/gif;base64,R0lGOD">' +                  // 非 http，剔除
    '</div>'
  it('提取 http(s) 图、去 query、按序去重', () => {
    const imgs = parseDetailImages(html)
    expect(imgs).toEqual([
      'https://cbu01.alicdn.com/img/ibank/a.jpg',
      'https://cbu01.alicdn.com/img/ibank/b.png'
    ])
  })
  it('空/非字符串 → 空数组', () => {
    expect(parseDetailImages('')).toEqual([])
    expect(parseDetailImages(null)).toEqual([])
  })
})

const { buildRichContent } = OzonHelperParse1688
const { parseAttributes } = OzonHelperParse1688

describe('buildRichContent', () => {
  it('每张图一个 raShowcase block，结构含 content 数组', () => {
    const rcj = buildRichContent(['https://x/a.jpg', 'https://x/b.jpg'])
    expect(Array.isArray(rcj.content)).toBe(true)
    expect(rcj.content.length).toBe(2)
    expect(rcj.content[0].blocks[0].img.src).toBe('https://x/a.jpg')
    expect(rcj.content[0].blocks[0].img.srcMobile).toBe('https://x/a.jpg')
  })
  it('图能被现有媒体管线 collectMediaUrls 收集（保证发布时走 OSS）', () => {
    const rcj = buildRichContent(['https://x/a.jpg', 'https://x/b.jpg'])
    const urls = OzonHelperMedia.collectMediaUrls({ images: [], rich_content_json: rcj })
    expect(urls.sort()).toEqual(['https://x/a.jpg', 'https://x/b.jpg'])
  })
  it('空列表 → null（无富文本时不应产生空属性）', () => {
    expect(buildRichContent([])).toBe(null)
    expect(buildRichContent(null)).toBe(null)
  })
})

describe('parseAttributes', () => {
  const html = '<div class="module-od-product-attributes"><table><tbody>' +
    '<tr class="ant-descriptions-row">' +
      '<th class="ant-descriptions-item-label"><span>产地</span></th>' +
      '<td class="ant-descriptions-item-content"><span><span class="field-value">江苏</span></span></td>' +
      '<th class="ant-descriptions-item-label"><span>是否进口</span></th>' +
      '<td class="ant-descriptions-item-content"><span><span class="field-value">否</span></span></td>' +
    '</tr>' +
    '<tr class="ant-descriptions-row">' +
      '<th class="ant-descriptions-item-label"><span>金属材质</span></th>' +
      '<td class="ant-descriptions-item-content"><span><span class="field-value">白铁皮</span></span></td>' +
    '</tr>' +
    '</tbody></table></div>'
  it('提取 name/value 名值对', () => {
    expect(parseAttributes(html)).toEqual([
      { name: '产地', value: '江苏' },
      { name: '是否进口', value: '否' },
      { name: '金属材质', value: '白铁皮' }
    ])
  })
  it('空/无匹配 → 空数组', () => {
    expect(parseAttributes('')).toEqual([])
    expect(parseAttributes('<div>无属性</div>')).toEqual([])
  })
})

const { parse1688Base } = OzonHelperParse1688
const { expandSkus } = OzonHelperParse1688

function mockData() {
  return {
    productTitle: { fields: { title: '加厚铁油桶汽油桶' } },
    mainPrice: { fields: { priceModel: { originalPriceDisplay: '18.79-141.63' } } },
    gallery: { fields: {
      offerImgList: ['https://cbu01.alicdn.com/m1.jpg', 'https://cbu01.alicdn.com/m2.jpg'],
      video: { coverUrl: 'https://img.alicdn.com/cover.jpg', videoId: 428131987474,
               videoUrl: 'https://cloud.video.taobao.com/play/x/428131987474.mp4' }
    } },
    productPackInfo: { fields: { pieceWeightScale: { pieceWeightScaleInfo: [] } } },
    Root: { fields: { dataJson: { skuModel: { skuProps: [], skuInfoMap: {} }, offerBaseInfo: {} } } }
  }
}
const DETAIL = '<div><img src="https://cbu01.alicdn.com/d1.jpg"><img src="https://cbu01.alicdn.com/d2.jpg"></div>'

function mockDataWithSku() {
  const d = mockData()
  d.Root.fields.dataJson.skuModel = {
    skuProps: [{ fid: 1234, prop: '规格', value: [
      { name: '摩托车专用款3升铝盖+油管', imageUrl: 'https://cbu01.alicdn.com/v3l.jpg' },
      { name: '标准加厚铁盖立式10L+油管', imageUrl: 'https://cbu01.alicdn.com/v10l.jpg' }
    ] }],
    skuInfoMap: {
      '摩托车专用款3升铝盖+油管': { specId: 's1', specAttrs: '摩托车专用款3升铝盖+油管', price: '18.79', discountPrice: '18.79', canBookCount: 9973, skuId: 5595723402563 },
      '标准加厚铁盖立式10L+油管': { specId: 's2', specAttrs: '标准加厚铁盖立式10L+油管', price: '35.50', discountPrice: '35.50', canBookCount: 100, skuId: 5595723402566 }
    }
  }
  d.productPackInfo.fields.pieceWeightScale.pieceWeightScaleInfo = [
    { sku1: '摩托车专用款3升铝盖+油管', skuId: 5595723402563, weight: 940, length: 310, width: 180, height: 110 },
    { sku1: '标准加厚铁盖立式10L+油管', skuId: 5595723402566, weight: 1600, length: 295, width: 130, height: 370 }
  ]
  return d
}

describe('expandSkus', () => {
  it('每个 SKU 一条，含价/库存/克重尺寸/变体图', () => {
    const data = mockDataWithSku()
    const base = parse1688Base(data, DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    const list = expandSkus(data, base)
    expect(list.length).toBe(2)
    const a = list[0]
    expect(a.variant_label).toBe('摩托车专用款3升铝盖+油管')
    expect(a.price).toBe('18.79')
    expect(a.weight_g).toBe(940)              // 克：两边一致，不换算
    expect(a.length_mm).toBe(310)             // 1688 本就毫米，草稿列统一毫米 → 直存
    expect(a.width_mm).toBe(180)
    expect(a.height_mm).toBe(110)
    expect(a.images[0]).toBe('https://cbu01.alicdn.com/v3l.jpg')   // 变体图置顶
    expect(a.images).toContain('https://cbu01.alicdn.com/m1.jpg')  // 含主图
    expect(a.source_raw.sku_id).toBe(5595723402563)
    expect(a.source_raw.stock).toBe(9973)
    expect(a.rich_content_json.content.length).toBe(2)             // 富文本共用
  })
  it('无 SKU → 单条，价取区间最贵那档', () => {
    const data = mockData()  // skuInfoMap 空
    const base = parse1688Base(data, DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    const list = expandSkus(data, base)
    expect(list.length).toBe(1)
    expect(list[0].price).toBe('141.63')   // 来自 originalPriceDisplay "18.79-141.63" 取最贵
  })
  it('单轴 → selected_aspects 含该轴的命中值', () => {
    const data = mockDataWithSku()
    const base = parse1688Base(data, DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    const list = expandSkus(data, base)
    expect(list[0].selected_aspects).toEqual([{ axis: '规格', value: '摩托车专用款3升铝盖+油管' }])
  })
  it('多轴(颜色+规格) → 按轴各取命中值（取最长子串最精确）', () => {
    const d = mockData()
    d.Root.fields.dataJson.skuModel = {
      skuProps: [
        { prop: '颜色', value: [{ name: '哑光白' }, { name: '薄荷绿' }] },
        { prop: '规格', value: [{ name: '5L' }, { name: '15L' }] }
      ],
      skuInfoMap: {
        '哑光白&5L': { specId: 's1', specAttrs: '哑光白&5L', skuId: 1, canBookCount: 5 },
        '薄荷绿&15L': { specId: 's2', specAttrs: '薄荷绿&15L', skuId: 2, canBookCount: 5 }
      }
    }
    const base = parse1688Base(d, DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    const list = expandSkus(d, base)
    expect(list[0].selected_aspects).toEqual([{ axis: '颜色', value: '哑光白' }, { axis: '规格', value: '5L' }])
    expect(list[1].selected_aspects).toEqual([{ axis: '颜色', value: '薄荷绿' }, { axis: '规格', value: '15L' }])
  })
})

describe('parse1688Base', () => {
  it('主图优先 mainImage(干净主图)而非 offerImgList(全量含变体缩略图)', () => {
    const d = mockData()
    d.gallery.fields.mainImage = ['https://cbu01.alicdn.com/hero1.jpg', 'https://cbu01.alicdn.com/hero2.jpg']
    const b = parse1688Base(d, DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    expect(b.images).toEqual(['https://cbu01.alicdn.com/hero1.jpg', 'https://cbu01.alicdn.com/hero2.jpg'])
  })
  it('无 mainImage 时兜底用 offerImgList', () => {
    const b = parse1688Base(mockData(), DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    expect(b.images).toEqual(['https://cbu01.alicdn.com/m1.jpg', 'https://cbu01.alicdn.com/m2.jpg'])
  })
  it('标题/主图/视频/富文本/source_raw', () => {
    const b = parse1688Base(mockData(), DETAIL, '', 'https://detail.1688.com/offer/795554901999.html')
    expect(b.source_platform).toBe('1688')
    expect(b.title).toBe('加厚铁油桶汽油桶')
    expect(b.images).toEqual(['https://cbu01.alicdn.com/m1.jpg', 'https://cbu01.alicdn.com/m2.jpg'])
    expect(b.video_url).toBe('https://cloud.video.taobao.com/play/x/428131987474.mp4')
    expect(b.rich_content_json.content.length).toBe(2)        // 2 张详情图
    expect(b.source_raw.offer_id).toBe('795554901999')
    expect(b.source_raw.price_display).toBe('18.79-141.63')
  })
  it('缺字段不抛错，降级为空', () => {
    const b = parse1688Base({}, '', '', '')
    expect(b.title).toBe('')
    expect(b.images).toEqual([])
    expect(b.video_url).toBe('')
    expect(b.rich_content_json).toBe(null)
  })
})

const { variantSourceUrl } = OzonHelperParse1688
describe('variantSourceUrl', () => {
  it('带 skuId → 拼 #sku= 唯一化', () => {
    expect(variantSourceUrl('https://detail.1688.com/offer/795554901999.html', 5595723402563))
      .toBe('https://detail.1688.com/offer/795554901999.html#sku=5595723402563')
  })
  it('spec text fallback is converted to a stable ascii fragment', () => {
    const url = variantSourceUrl('https://detail.1688.com/offer/971518922897.html', '3pc火花塞套筒（卡装）')
    expect(url).toMatch(/^https:\/\/detail\.1688\.com\/offer\/971518922897\.html#sku=spec-[a-z0-9]+$/)
    expect(url).toBe(variantSourceUrl('https://detail.1688.com/offer/971518922897.html', '3pc火花塞套筒（卡装）'))
  })
  it('无 skuId → 原样', () => {
    expect(variantSourceUrl('https://x/o.html', null)).toBe('https://x/o.html')
    expect(variantSourceUrl('https://x/o.html', '')).toBe('https://x/o.html')
  })
})

describe('parseSkuRowsFromDom / mergeSkuDomRows', () => {
  function cell(text) {
    return { innerText: text, textContent: text }
  }
  function row(text, cells, img) {
    return {
      innerText: text,
      textContent: text,
      querySelectorAll(sel) {
        if (sel === 'td, th, [role="cell"]') return cells.map(cell)
        if (sel === 'img') return img ? [{ getAttribute: (name) => (name === 'src' ? img : '') }] : []
        return []
      }
    }
  }
  function container(text) {
    return {
      innerText: text,
      textContent: text,
      querySelectorAll() { return [] }
    }
  }
  it('uses visible 1688 sku rows to add variants missing from skuInfoMap', () => {
    const doc = {
      querySelectorAll() {
        return [
          row('产品规格 价格 | 库存(套) 进货数量', ['产品规格', '价格 | 库存(套)', '进货数量']),
          row('3pc火花塞套筒（卡装） ¥5.7 | 123102 0 +', ['3pc火花塞套筒（卡装）', '¥5.7 | 123102', '0 +'], 'https://img.example/3pc.jpg'),
          row('5pc火花塞套筒（卡装） ¥8.8 | 124962 0 +', ['5pc火花塞套筒（卡装）', '¥8.8 | 124962', '0 +'], 'https://img.example/5pc.jpg')
        ]
      }
    }
    const domRows = parseSkuRowsFromDom(doc)
    expect(domRows).toHaveLength(2)
    const base = { images: ['https://img.example/base.jpg'], source_raw: { price_display: '5.7-8.8' } }
    const parsed = [{
      price: '8.8',
      variant_label: '5pc火花塞套筒（卡装）',
      images: [],
      source_raw: { sku_id: 6089030811095, spec_attrs: '5pc火花塞套筒（卡装）' }
    }]
    const merged = mergeSkuDomRows(parsed, domRows, base)
    expect(merged.map((v) => v.source_raw.spec_attrs)).toEqual(['5pc火花塞套筒（卡装）', '3pc火花塞套筒（卡装）'])
    expect(merged[1].price).toBe('5.7')
    expect(merged[1].source_raw.stock).toBe(123102)
  })
  it('does not treat aggregate sku containers or promo blocks as extra variants', () => {
    const doc = {
      querySelectorAll() {
        return [
          container('产品规格 单个装 ¥5.7 | 123102 推荐代发 ¥8.8 铺货分销'),
          row('单个装 ¥5.7 | 123102 0 +', ['单个装', '¥5.7 | 123102', '0 +'])
        ]
      }
    }
    const domRows = parseSkuRowsFromDom(doc)
    expect(domRows).toHaveLength(1)
    const base = { images: [], source_raw: { price_display: '5.7' } }
    const parsed = [{ price: '5.7', variant_label: '单个装', images: [], source_raw: { sku_id: 1, spec_attrs: '单个装' } }]
    expect(mergeSkuDomRows(parsed, domRows, base)).toHaveLength(1)
  })
})

describe('expandSkus 区间价（乱序取最贵）', () => {
  it('price_display 乱序也取最贵那档', () => {
    const list = expandSkus(mockData(), { source_raw: { price_display: '141.63-18.79' }, images: [] })
    expect(list.length).toBe(1)
    expect(list[0].price).toBe('141.63')
  })
})

// 2026-06 1688 改版：价从 mainPrice.fields.finalPriceModel.tradeWithoutPromotion 取；SKU 常不带单价
describe('1688 改版价格路径 (finalPriceModel)', () => {
  function mockNewPrice() {
    const d = mockData()
    delete d.mainPrice.fields.priceModel
    d.mainPrice.fields.finalPriceModel = {
      tradeWithoutPromotion: { offerPriceDisplay: '143.00-159.00', offerMaxPrice: '159.00' }
    }
    d.Root.fields.dataJson.skuModel = {
      skuProps: [],
      skuInfoMap: { 哑光白: { specId: 's1', specAttrs: '哑光白', canBookCount: 488, skuId: 6254336483671 } }
    }
    return d
  }
  it('price_display 取 finalPriceModel.offerPriceDisplay', () => {
    const b = parse1688Base(mockNewPrice(), DETAIL, '', 'https://detail.1688.com/offer/1.html')
    expect(b.source_raw.price_display).toBe('143.00-159.00')
  })
  it('SKU 无单价 → 用整品区间最贵那档兜底', () => {
    const d = mockNewPrice()
    const base = parse1688Base(d, DETAIL, '', 'https://detail.1688.com/offer/1.html')
    const list = expandSkus(d, base)
    expect(list.length).toBe(1)
    expect(list[0].price).toBe('159.00')
  })
})

// 「商品件重尺」HTML 表(长宽高 cm + 重量 g)——Ozon 必填，尺寸优先源
const { parsePackInfo } = OzonHelperParse1688
const PACK_HTML = '<div class="module-od-product-pack-info"><table>' +
  '<thead><tr><th class="field-value">颜色</th><th class="field-value">规格</th>' +
  '<th class="field-value">长(cm)</th><th class="field-value">宽(cm)</th><th class="field-value">高(cm)</th>' +
  '<th class="field-value">体积(cm³)</th><th class="field-value">重量(g)</th></tr></thead><tbody>' +
  '<tr><td class="field-value">哑光白</td><td class="field-value">可视款无304不锈钢盆</td>' +
  '<td class="field-value">20.50</td><td class="field-value">20.50</td><td class="field-value">30.50</td>' +
  '<td class="field-value">12817.625</td><td class="field-value">1800</td></tr>' +
  '<tr><td class="field-value">薄荷绿</td><td class="field-value">可视款无304不锈钢盆</td>' +
  '<td class="field-value">21.00</td><td class="field-value">21.00</td><td class="field-value">31.00</td>' +
  '<td class="field-value">13000</td><td class="field-value">1850</td></tr></tbody></table></div>'

describe('parsePackInfo (商品件重尺表)', () => {
  it('每行解析 颜色/长宽高(cm)/重量(g)', () => {
    const rows = parsePackInfo(PACK_HTML)
    expect(rows.length).toBe(2)
    expect(rows[0]).toMatchObject({ color: '哑光白', length_cm: 20.5, width_cm: 20.5, height_cm: 30.5, weight_g: 1800 })
    expect(rows[1].color).toBe('薄荷绿')
    expect(rows[1].weight_g).toBe(1850)
  })
  it('空/无表 → []', () => {
    expect(parsePackInfo('')).toEqual([])
    expect(parsePackInfo(null)).toEqual([])
  })
})

describe('expandSkus 用包装表尺寸(cm 直填，优先于 pieceWeightScaleInfo)', () => {
  it('按颜色匹配包装行，长宽高用 cm 取整直填(不再 ÷10)', () => {
    const d = mockDataWithSku()
    d.Root.fields.dataJson.skuModel.skuInfoMap = {
      白: { specId: 's1', specAttrs: '哑光白>可视款', skuId: 1, canBookCount: 5 },
      绿: { specId: 's2', specAttrs: '薄荷绿>可视款', skuId: 2, canBookCount: 5 }
    }
    const base = parse1688Base(d, DETAIL, '', 'https://x/o.html')
    const list = expandSkus(d, base, PACK_HTML)
    expect(list[0].length_mm).toBe(205)  // 哑光白 20.5cm → 毫米 205（cm×10）
    expect(list[0].weight_g).toBe(1800)
    expect(list[1].length_mm).toBe(210)  // 薄荷绿 21.0cm → 210mm
    expect(list[1].weight_g).toBe(1850)  // 按颜色匹配到薄荷绿那行
  })
  it('无 packHtml → 回退 pieceWeightScaleInfo（毫米直存）', () => {
    const d = mockDataWithSku()
    const base = parse1688Base(d, DETAIL, '', 'https://x/o.html')
    const list = expandSkus(d, base)        // 不传 packHtml
    expect(list[0].length_mm).toBe(310)     // 310mm 直存（pieceWeightScaleInfo 兜底）
  })
})
