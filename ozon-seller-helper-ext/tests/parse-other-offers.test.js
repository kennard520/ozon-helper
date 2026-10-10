import { describe, it, expect } from 'vitest'
import OzonHelperParse from '../common/parse-other-offers.js'
import sample from './fixtures/other-offers-sample.json'

const { extractProductId, parseReviewCount, parseRating, estimateSales } = OzonHelperParse

describe('extractProductId', () => {
  it('从带 slug 的商品 URL 取末尾数字 id', () => {
    expect(
      extractProductId('https://www.ozon.ru/product/krem-dlya-ruk-1700000123/?asb=1')
    ).toBe('1700000123')
  })

  it('支持纯数字路径', () => {
    expect(extractProductId('https://www.ozon.ru/product/1700000123/')).toBe('1700000123')
  })

  it('非商品页返回 null', () => {
    expect(extractProductId('https://www.ozon.ru/category/dom-12345/')).toBeNull()
  })

  it('空/坏输入返回 null', () => {
    expect(extractProductId('')).toBeNull()
    expect(extractProductId(null)).toBeNull()
  })

  it('slug 中间含数字时仍取末尾 id', () => {
    expect(
      extractProductId('https://www.ozon.ru/product/krem-2-v-1-1700000123/')
    ).toBe('1700000123')
  })

  it('有 query 但无末尾斜杠', () => {
    expect(
      extractProductId('https://www.ozon.ru/product/krem-1700000123?asb=1')
    ).toBe('1700000123')
  })
})

describe('parseReviewCount', () => {
  it('从评分 widget 的 reviewsCount 取评论数', () => {
    const json = {
      widgetStates: {
        'webSingleProductScore-1-x': JSON.stringify({ totalScore: 4.8, reviewsCount: 1234 })
      }
    }
    expect(parseReviewCount(json)).toBe(1234)
  })

  it('reviewsCount 为带千分位文本也能解析', () => {
    const json = {
      widgetStates: { 'webReviewProductScore-2-x': JSON.stringify({ reviewsCount: '1 234' }) }
    }
    expect(parseReviewCount(json)).toBe(1234)
  })

  it('深层嵌套 commentsCount 也能命中', () => {
    const json = {
      widgetStates: {
        'webScore-3-x': JSON.stringify({ score: { summary: { commentsCount: 56 } } })
      }
    }
    expect(parseReviewCount(json)).toBe(56)
  })

  it('无评论数据返回 null', () => {
    expect(parseReviewCount({ widgetStates: { 'webGallery-1-x': JSON.stringify({ images: [] }) } })).toBeNull()
    expect(parseReviewCount(null)).toBeNull()
    expect(parseReviewCount({})).toBeNull()
  })
})

describe('parseRating', () => {
  it('取 0–5 评分(totalScore)', () => {
    const json = { widgetStates: { 'webSingleProductScore-1-x': JSON.stringify({ totalScore: 4.8, reviewsCount: 1234 }) } }
    expect(parseRating(json)).toBe(4.8)
  })
  it('逗号小数评分也能解析', () => {
    const json = { widgetStates: { 'webScore-2-x': JSON.stringify({ rating: '4,5' }) } }
    expect(parseRating(json)).toBe(4.5)
  })
  it('超出 0–5 的值(如评论数)不会被当评分', () => {
    const json = { widgetStates: { 'webFoo-3-x': JSON.stringify({ score: 1234 }) } }
    expect(parseRating(json)).toBeNull()
  })
  it('无评分返回 null', () => {
    expect(parseRating(null)).toBeNull()
    expect(parseRating({ widgetStates: {} })).toBeNull()
  })
})

// 2026-06 Ozon 改版：评分/评论数字字段被置空，只剩 webSingleProductScore.text 里一段文字
// 实测 pid 3825780477：webReviewProductScore.score=null，webSingleProductScore.text="4.9 • 6 365 отзывов"
describe('parseRating/parseReviewCount —— 新版只在文字串里', () => {
  const NEW = {
    widgetStates: {
      'webReviewProductScore-3132021-default-1': JSON.stringify({
        cellTrackingInfo: {}, url: '/product/gardex-100-ml-3825780477/reviews/', score: null, reviewsCount: null
      }),
      'webSingleProductScore-3386432-default-1': JSON.stringify({
        icon: 'ic_s_star_filled', iconColor: 'graphicRating',
        text: '4.9 • 6 365 отзывов', textColor: 'textSecondary',
        link: '/product/gardex-100-ml-3825780477/reviews/'
      })
    }
  }

  it('从 "4.9 • 6 365 отзывов" 取评分 4.9', () => {
    expect(parseRating(NEW)).toBe(4.9)
  })

  it('从 "4.9 • 6 365 отзывов" 取评论数 6365（去俄式空格千分位）', () => {
    expect(parseReviewCount(NEW)).toBe(6365)
  })

  it('整数评分 + "оценок" 文案也能解析', () => {
    const j = { widgetStates: { 'webSingleProductScore-x': JSON.stringify({ text: '5 • 42 оценок' }) } }
    expect(parseRating(j)).toBe(5)
    expect(parseReviewCount(j)).toBe(42)
  })

  it('非评分类 widget 里以数字开头的文字不会被误当评分', () => {
    const j = { widgetStates: { 'webDelivery-x': JSON.stringify({ text: '3 дня доставка' }) } }
    expect(parseRating(j)).toBeNull()
  })
})

describe('estimateSales', () => {
  it('按 3-7% 评论率给出销量范围', () => {
    const est = estimateSales(100)
    expect(est.reviews).toBe(100)
    expect(est.salesLow).toBe(Math.round(100 / 0.07)) // 1429
    expect(est.salesHigh).toBe(Math.round(100 / 0.03)) // 3333
    expect(est.salesLow).toBeLessThan(est.salesHigh)
  })

  it('0 评论 → 0 销量范围', () => {
    expect(estimateSales(0)).toEqual({ reviews: 0, salesLow: 0, salesHigh: 0 })
  })

  it('无评论数(null/非法)返回 null', () => {
    expect(estimateSales(null)).toBeNull()
    expect(estimateSales(undefined)).toBeNull()
    expect(estimateSales(-1)).toBeNull()
    expect(estimateSales(NaN)).toBeNull()
  })
})

const { parseRubPrice, summarizeOtherOffers } = OzonHelperParse

describe('parseRubPrice', () => {
  it('普通空格分隔 + ₽', () => {
    expect(parseRubPrice('1 290 ₽')).toBe(1290)
  })
  it('不间断空格(nbsp)分隔', () => {
    expect(parseRubPrice('1 290 ₽')).toBe(1290)
  })
  it('纯数字', () => {
    expect(parseRubPrice('1290')).toBe(1290)
  })
  it('占位/空 → null', () => {
    expect(parseRubPrice('—')).toBeNull()
    expect(parseRubPrice('')).toBeNull()
    expect(parseRubPrice(null)).toBeNull()
  })
  it('俄式小数逗号(戈比)四舍五入', () => {
    expect(parseRubPrice('1 290,50 ₽')).toBe(1291)
    expect(parseRubPrice('99,50 ₽')).toBe(100)
  })
  it('逗号千分位也不被误读成小数', () => {
    expect(parseRubPrice('1,290 ₽')).toBe(1290)
  })
})

describe('summarizeOtherOffers', () => {
  it('从 webSellerList 抽出跟卖卖家（含划线价/发货地/送达）', () => {
    const r = summarizeOtherOffers(sample)
    expect(r.followCount).toBe(4)
    expect(r.priceMin).toBe(3100)
    expect(r.priceMax).toBe(4626)
    expect(r.sellers[0]).toEqual({
      name: 'Юмитой',
      price: 3322,
      originalPrice: null,
      link: 'https://www.ozon.ru/product/a-730554241/',
      origin: 'ru',
      mode: 'FBO',
      deliver: 'Доставим 20 июня'
    })
    // Корица：哈萨克地址 → foreign，且有划线价
    expect(r.sellers[1].origin).toBe('foreign')
    expect(r.sellers[1].price).toBe(3657)
    expect(r.sellers[1].originalPrice).toBe(4200)
    // B0063：拼音地址 → foreign
    expect(r.sellers[2].origin).toBe('foreign')
    // МедПокупки：Россия → ru
    expect(r.sellers[3].origin).toBe('ru')
  })

  it('发货地分类：俄标记/西里尔→ru，哈萨克/拼音/拉丁→foreign，无信息→unknown', () => {
    const mk = (creds) => ({ widgetStates: { 'webSellerList-x': { sellers: [{ name: 'x', credentials: creds, price: { cardPrice: { price: '1 ₽' } } }] } } })
    const origin = (creds) => summarizeOtherOffers(mk(creds)).sellers[0].origin
    expect(origin(['ИП Иванов', '620078, Екатеринбург, область'])).toBe('ru')
    expect(origin(['Корица', 'Astana, Almaty'])).toBe('foreign')
    expect(origin(['B', 'yu lin shi zhen cun'])).toBe('foreign')
    expect(origin(['X', 'Ponomarenko 35A'])).toBe('foreign')
    expect(origin([])).toBe('unknown')
  })

  it('旧/备用结构(sellerName + price.price + 仅卖家link)也能解析', () => {
    const obj = {
      widgetStates: {
        'webSellerList-1-x': { sellers: [{ sellerName: 'A', link: '/seller/a-1/', price: { price: '500 ₽' } }] }
      }
    }
    const r = summarizeOtherOffers(obj)
    expect(r.followCount).toBe(1)
    expect(r.sellers[0]).toEqual({ name: 'A', price: 500, originalPrice: null, link: 'https://www.ozon.ru/seller/a-1/', origin: 'unknown', mode: '', deliver: '' })
  })

  it('履约模式：国外→FBS，本地→FBO，未知→空', () => {
    const r = summarizeOtherOffers(sample)
    expect(r.sellers[0].mode).toBe('FBO') // Юмитой 本地
    expect(r.sellers[1].mode).toBe('FBS') // Корица 哈萨克
    expect(r.sellers[2].mode).toBe('FBS') // B0063 拼音
    expect(r.sellers[3].mode).toBe('FBO') // МедПокупки 俄罗斯
  })

  it('没有 webSellerList → 0 跟卖', () => {
    expect(summarizeOtherOffers({ widgetStates: {} })).toEqual({
      followCount: 0, priceMin: null, priceMax: null, sellers: []
    })
  })

  it('坏输入 → 0 跟卖不抛异常', () => {
    expect(summarizeOtherOffers(null).followCount).toBe(0)
    expect(summarizeOtherOffers({}).followCount).toBe(0)
  })
  it('多次空结果返回的是各自独立对象(不共享引用)', () => {
    const a = summarizeOtherOffers({ widgetStates: {} })
    a.sellers.push('x')
    const b = summarizeOtherOffers({ widgetStates: {} })
    expect(b.sellers).toEqual([])
  })
})
