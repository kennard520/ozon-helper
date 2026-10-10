import { describe, expect, it } from 'vitest'
import Card from '../common/wb-card.js'

describe('WB page identity', () => {
  it('extracts nm_id only from a WB product detail URL', () => {
    expect(Card.nmFromUrl('https://www.wildberries.ru/catalog/331107205/detail.aspx')).toBe('331107205')
    expect(Card.nmFromUrl('https://www.wildberries.ru/catalog/platya')).toBeNull()
    expect(Card.isProductPage('https://www.wildberries.ru/catalog/331107205/detail.aspx?targetUrl=GP')).toBe(true)
    expect(Card.isProductPage('https://www.wildberries.ru/catalog/0/search.aspx?search=test')).toBe(false)
  })

  it('derives vol and part from nm_id', () => {
    expect(Card.volPart('331107205')).toEqual({ vol: 3311, part: 331107 })
  })
})

describe('WB card resolution', () => {
  it('prefers a page-loaded card URL that belongs to the same nm_id', () => {
    const entries = [
      'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575807/info/ru/card.json',
      'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
    ]
    expect(Card.cardJsonUrlFromEntries(entries, '1190575806')).toBe(entries[1])
  })

  it('ignores non-HTTPS page-loaded card URLs', () => {
    const entries = [
      'http://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json',
      'ftp://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
    ]
    expect(Card.cardJsonUrlFromEntries(entries, '1190575806')).toBeNull()
  })

  it('accepts only HTTPS WB card URLs with an exact nm_id path', () => {
    const valid = 'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
    expect(Card.isAllowedCardUrl(valid, '1190575806')).toBe(true)
    expect(Card.isAllowedCardUrl(valid, '119057580')).toBe(false)
    expect(Card.isAllowedCardUrl(valid.replace('https:', 'http:'), '1190575806')).toBe(false)
    expect(Card.isAllowedCardUrl(valid.replace('geobasket.ru', 'geobasket.ru.example.com'), '1190575806')).toBe(false)
  })

  it('generates deterministic WB basket card candidates', () => {
    const candidates = Card.basketCardUrls('1190575806')
    expect(candidates.slice(0, 3)).toEqual([
      {
        host: 'mow-basket-cdn-23.geobasket.ru',
        url: 'https://mow-basket-cdn-23.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
      },
      {
        host: 'mow-basket-cdn-22.geobasket.ru',
        url: 'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
      },
      {
        host: 'mow-basket-cdn-24.geobasket.ru',
        url: 'https://mow-basket-cdn-24.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
      }
    ])
    expect(new Set(candidates.map(({ host }) => host)).size).toBe(candidates.length)
  })

  it('discovers and de-duplicates every color variant while retaining current nm_id', () => {
    const card = {
      full_colors: [{ nm_id: 399656234 }, { nm_id: 737964991 }, { nm_id: 1190575807 }],
      colors: [399656234, 1190575807, 1190575806]
    }
    expect(Card.variantIds(card, '1190575806')).toEqual([
      '399656234', '737964991', '1190575807', '1190575806'
    ])
  })

  it('resolves the validated hint before generated fallback candidates', async () => {
    const calls = []
    const hint = 'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
    const result = await Card.resolveCard('1190575806', hint, async (url) => {
      calls.push(url)
      return { nm_id: 1190575806, imt_id: 1390661929, nm_colors_names: 'черный' }
    })
    expect(calls).toEqual([hint])
    expect(result.host).toBe('mow-basket-cdn-22.geobasket.ru')
    expect(Card.variantLabel(result.card, 0)).toBe('черный')
  })

  it('uses a stable fallback label when the card has no color name', () => {
    expect(Card.variantLabel({}, 2)).toBe('变体03')
  })
})
