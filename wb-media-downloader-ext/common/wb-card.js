;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbMediaCard = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function nmFromUrl(url) {
    const match = String(url || '').match(/^https:\/\/www\.wildberries\.ru\/catalog\/(\d+)\/detail\.aspx(?:[?#]|$)/i)
    return match ? match[1] : null
  }

  function isProductPage(url) {
    return nmFromUrl(url) !== null
  }

  function volPart(nm) {
    const value = Number.parseInt(nm, 10)
    return { vol: Math.floor(value / 100000), part: Math.floor(value / 1000) }
  }

  function variantIds(card, currentNm) {
    const out = []
    const seen = new Set()
    const add = (value) => {
      const raw = value && typeof value === 'object' ? (value.nm_id || value.id || value.nm) : value
      const id = String(raw || '').trim()
      if (!/^\d+$/.test(id) || seen.has(id)) return
      seen.add(id)
      out.push(id)
    }
    ;((card && card.full_colors) || []).forEach(add)
    ;((card && card.colors) || []).forEach(add)
    add(currentNm || (card && card.nm_id))
    return out
  }

  function variantLabel(card, index) {
    const value = String((card && card.nm_colors_names) || '').trim()
    return value || `变体${String(index + 1).padStart(2, '0')}`
  }

  function isAllowedCardUrl(raw, nm) {
    try {
      const url = new URL(raw)
      return url.protocol === 'https:' &&
        /\.(?:wbbasket|geobasket|wb)\.ru$/i.test(url.hostname) &&
        url.pathname.endsWith(`/${String(nm || '')}/info/ru/card.json`)
    } catch (_) {
      return false
    }
  }

  function cardJsonUrlFromEntries(entries, nm) {
    const id = String(nm || '')
    for (let index = (entries || []).length - 1; index >= 0; index--) {
      const raw = typeof entries[index] === 'string' ? entries[index] : entries[index] && entries[index].name
      if (isAllowedCardUrl(raw, id)) return new URL(raw).href
    }
    return null
  }

  function legacyBasketByVol(vol) {
    const ranges = [
      [143, 1], [287, 2], [431, 3], [719, 4], [1007, 5],
      [1061, 6], [1115, 7], [1169, 8], [1313, 9], [1601, 10],
      [1655, 11], [1919, 12], [2045, 13], [2189, 14], [2405, 15],
      [2621, 16], [2837, 17], [3053, 18], [3269, 19]
    ]
    for (const [maxVol, basket] of ranges) {
      if (vol <= maxVol) return basket
    }
    return null
  }

  function basketCardUrls(nm) {
    const n = Number.parseInt(nm, 10)
    const { vol, part } = volPart(n)
    const max = 100
    const out = []
    const seen = new Set()
    const add = (host) => {
      if (!host || seen.has(host)) return
      seen.add(host)
      out.push({ host, url: `https://${host}/vol${vol}/part${part}/${n}/info/ru/card.json` })
    }
    if (vol >= 10000) {
      const cdn = Math.max(1, Math.floor(vol / 500))
      ;[cdn, cdn - 1, cdn + 1].forEach((basket) => {
        if (basket >= 1 && basket <= max) add(`mow-basket-cdn-${String(basket).padStart(2, '0')}.geobasket.ru`)
      })
    }
    const legacy = legacyBasketByVol(vol)
    if (legacy) add(`basket-${String(legacy).padStart(2, '0')}.wbbasket.ru`)
    let estimated = Math.round(19 + (vol - 3064) * (41 - 19) / (9816 - 3064))
    estimated = Math.max(1, Math.min(estimated, max))
    const order = []
    for (let basket = estimated; basket <= max; basket++) order.push(basket)
    for (let basket = estimated - 1; basket >= 1; basket--) order.push(basket)
    order.forEach((basket) => add(`basket-${String(basket).padStart(2, '0')}.wbbasket.ru`))
    return out
  }

  async function resolveCard(nm, hintUrl, fetchJson) {
    const candidates = []
    if (isAllowedCardUrl(hintUrl, nm)) candidates.push(hintUrl)
    for (const item of basketCardUrls(nm)) if (!candidates.includes(item.url)) candidates.push(item.url)
    let lastError = null
    for (const cardUrl of candidates) {
      try {
        const card = await fetchJson(cardUrl)
        if (card && String(card.nm_id || nm) === String(nm)) {
          return { card, cardUrl, host: new URL(cardUrl).hostname }
        }
      } catch (error) { lastError = error }
    }
    throw new Error(`无法读取 WB 商品 ${nm}: ${lastError ? lastError.message : 'card.json 不可用'}`)
  }

  return {
    nmFromUrl, isProductPage, volPart,
    cardJsonUrlFromEntries, basketCardUrls, isAllowedCardUrl, resolveCard,
    variantIds, variantLabel
  }
})
