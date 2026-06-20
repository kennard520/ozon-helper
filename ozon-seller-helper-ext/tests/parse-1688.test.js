// ozon-seller-helper-ext/tests/parse-1688.test.js
import { describe, it, expect } from 'vitest'
import OzonHelperParse1688 from '../common/parse-1688.js'
import OzonHelperMedia from '../common/media-upload.js'

const { extractOfferId } = OzonHelperParse1688
const { parseDetailImages } = OzonHelperParse1688

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

describe('parse1688Base', () => {
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
