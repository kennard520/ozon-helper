import { describe, it, expect } from 'vitest'
import OzonHelperListing from '../common/listing-util.js'

const { uniqueProductIds, cardHtml } = OzonHelperListing

describe('uniqueProductIds', () => {
  it('从一组 href 取唯一 product id（按出现顺序）', () => {
    expect(uniqueProductIds([
      '/product/krem-1700000123/',
      'https://www.ozon.ru/product/foo-1700000123/?x=1', // 同 id 去重
      '/product/bar-999/',
      '/category/dom-5/' // 非商品
    ])).toEqual(['1700000123', '999'])
  })
  it('空/坏输入 → []', () => {
    expect(uniqueProductIds([])).toEqual([])
    expect(uniqueProductIds(null)).toEqual([])
  })
})

describe('cardHtml', () => {
  it('loading 态：显示加载中 + 编辑上架按钮', () => {
    const h = cardHtml({ loading: true })
    expect(h).toContain('加载中')
    expect(h).toContain('ohl-edit')
  })
  it('有跟卖：显示家数 + 最低价', () => {
    const h = cardHtml({ summary: { followCount: 3, priceMin: 100, priceMax: 200 } })
    expect(h).toContain('跟卖')
    expect(h).toContain('3')
    expect(h).toContain('100')
    expect(h).toContain('ohl-edit')
  })
  it('0 跟卖：显示无跟卖', () => {
    expect(cardHtml({ summary: { followCount: 0, priceMin: null, priceMax: null } })).toContain('无跟卖')
  })
  it('error 态：显示未获取', () => {
    expect(cardHtml({ error: true })).toContain('未获取')
  })
  it('带估算销量：显示销量(估) + 万单位', () => {
    const h = cardHtml({ summary: { followCount: 2, priceMin: 50 }, estimate: { salesLow: 14286, salesHigh: 33333 } })
    expect(h).toContain('跟卖')
    expect(h).toContain('销量(估)')
    expect(h).toContain('万')
  })
  it('无估算时只显示跟卖、不出销量栏', () => {
    const h = cardHtml({ summary: { followCount: 1, priceMin: 9 } })
    expect(h).not.toContain('销量(估)')
  })
  it('带评分：显示 ★', () => {
    const h = cardHtml({ summary: { followCount: 2, priceMin: 50 }, rating: 4.7 })
    expect(h).toContain('★')
    expect(h).toContain('4.7')
  })
  it('无评分时不出 ★', () => {
    expect(cardHtml({ summary: { followCount: 1, priceMin: 9 } })).not.toContain('★')
  })
  it('无跟卖但有评论数据：仍显示销量(估) + 评分（不被"无跟卖"吞掉）', () => {
    const h = cardHtml({
      summary: { followCount: 0, priceMin: null, priceMax: null },
      estimate: { salesLow: 111929, salesHigh: 261167 }, rating: 4.8
    })
    expect(h).toContain('无跟卖')
    expect(h).toContain('销量(估)')
    expect(h).toContain('★')
    expect(h).toContain('4.8')
  })
  it('无跟卖且无评论数据：只剩无跟卖一行', () => {
    const h = cardHtml({ summary: { followCount: 0, priceMin: null, priceMax: null } })
    expect(h).toContain('无跟卖')
    expect((h.match(/class="ohl-line"/g) || []).length).toBe(1)
  })
  it('每个指标各占一行（ohl-line），不再用点号挤一行', () => {
    const h = cardHtml({
      summary: { followCount: 80, priceMin: 257 },
      estimate: { salesLow: 32000, salesHigh: 76000 }, rating: 4.9,
    })
    const lines = (h.match(/class="ohl-line"/g) || []).length
    expect(lines).toBe(4)            // 跟卖家数 / 最低价 / 销量(估) / 评分 各一行
    expect(h).not.toContain(' · ')   // 不再点号串一行
  })
  it('多变体(variantCount>1)才出「采集全部变体」按钮', () => {
    const multi = cardHtml({ summary: { followCount: 1, priceMin: 9 }, variantCount: 5 })
    expect(multi).toContain('ohl-variants')
    expect(multi).toContain('采集全部变体(5)')
    const single = cardHtml({ summary: { followCount: 1, priceMin: 9 }, variantCount: 1 })
    expect(single).not.toContain('ohl-variants')
    expect(cardHtml({ summary: { followCount: 1, priceMin: 9 } })).not.toContain('ohl-variants')  // 无变体数不出
  })
})
