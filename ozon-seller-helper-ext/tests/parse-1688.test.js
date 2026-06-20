// ozon-seller-helper-ext/tests/parse-1688.test.js
import { describe, it, expect } from 'vitest'
import OzonHelperParse1688 from '../common/parse-1688.js'

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
