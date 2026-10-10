import { describe, it, expect } from 'vitest'
import OzonHelperSite from '../common/site.js'

const { detectSite, currencyOf } = OzonHelperSite

describe('detectSite', () => {
  it('ozon', () => {
    expect(detectSite('www.ozon.ru')).toBe('ozon')
    expect(detectSite('ozon.ru')).toBe('ozon')
    expect(detectSite('seller.ozon.ru')).toBe('ozon')
  })
  it('1688', () => {
    expect(detectSite('detail.1688.com')).toBe('1688')
    expect(detectSite('www.1688.com')).toBe('1688')
  })
  it('拼多多 (yangkeduo / pinduoduo)', () => {
    expect(detectSite('mobile.yangkeduo.com')).toBe('pdd')
    expect(detectSite('mobile.pinduoduo.com')).toBe('pdd')
  })
  it('wildberries (apex / www / 子域)', () => {
    expect(detectSite('www.wildberries.ru')).toBe('wb')
    expect(detectSite('wildberries.ru')).toBe('wb')
    expect(detectSite('m.wildberries.ru')).toBe('wb')
  })
  it('其它站点 / 空 → null', () => {
    expect(detectSite('example.com')).toBeNull()
    expect(detectSite('')).toBeNull()
    expect(detectSite(null)).toBeNull()
  })
  it('防子串/伪造域名', () => {
    expect(detectSite('fake-ozon.ru')).toBeNull()
    expect(detectSite('notozon.ru.evil.com')).toBeNull()
  })
})

describe('currencyOf', () => {
  it('俄区站(Ozon/WB) → RUB', () => {
    expect(currencyOf('ozon')).toBe('RUB')
    expect(currencyOf('wb')).toBe('RUB')
  })
  it('国内站(1688/拼多多) → CNY', () => {
    expect(currencyOf('1688')).toBe('CNY')
    expect(currencyOf('pdd')).toBe('CNY')
  })
  it('未知/空 → null', () => {
    expect(currencyOf(null)).toBeNull()
    expect(currencyOf('example')).toBeNull()
  })
})
