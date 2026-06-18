// 解析 Ozon 跟卖接口（纯函数，UMD：content script 全局 + vitest import）
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperParse = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  const OZON_ORIGIN = 'https://www.ozon.ru'

  function extractProductId(url) {
    if (!url || typeof url !== 'string') return null
    const m = url.match(/\/product\/[^/?#]*?(\d+)\/?(?:[?#]|$)/)
    return m ? m[1] : null
  }

  function parseRubPrice(text) {
    if (text == null) return null
    let s = String(text).replace(/[^\d.,]/g, '')
    // 逗号千分位（数字,3位数字 后接 逗号/点/结尾）→ 去掉逗号，避免被当小数
    s = s.replace(/(\d),(\d{3})(?=[,.]|$)/g, '$1$2')
    s = s.replace(',', '.')
    if (!s) return null
    const n = parseFloat(s)
    return Number.isFinite(n) ? Math.round(n) : null
  }

  function _firstSellerName(s) {
    return s.sellerName || s.name || s.title || (s.seller && s.seller.name) || ''
  }
  function _firstSellerPriceText(s) {
    const p = s.price
    if (p && typeof p === 'object') {
      // 实测结构：price.cardPrice.price（买家实付的卡价）
      if (p.cardPrice && p.cardPrice.price) return p.cardPrice.price
      if (p.price) return p.price
      if (p.originalPrice && p.originalPrice.price) return p.originalPrice.price
    }
    return s.finalPrice || s.cardPrice || s.priceText || (typeof s.price === 'string' ? s.price : '')
  }
  function _firstSellerOriginalPriceText(s) {
    const p = s.price
    if (p && typeof p === 'object') {
      if (p.originalPrice && p.originalPrice.price) return p.originalPrice.price
      if (typeof p.originalPrice === 'string') return p.originalPrice
    }
    return ''
  }
  function _sellerDeliver(s) {
    const adv = Array.isArray(s.advantages) ? s.advantages : []
    for (const a of adv) {
      if (a && a.key === 'delivery') {
        try { return a.contentRs.headRs.map((h) => h.content).join(' ').trim() } catch (e) { /* ignore */ }
      }
    }
    return ''
  }
  function _sellerOrigin(s) {
    const creds = Array.isArray(s.credentials) ? s.credentials : []
    const text = creds.join(' ')
    if (!text.trim()) return 'unknown'
    // 国外关键词（哈萨克/中国/白俄等）
    const FOREIGN = /\b(kz|cn|by)\b|astana|almaty|kazakh|казахстан|china|кита[йя]|beijing|guangzhou|shenzhen|belarus|беларус|minsk|минск/i
    // 俄罗斯标记
    const RU = /росси|область|обл\.|край|респ|москв|петербург|самар|екатеринбург|\bООО\b|\bИП\b|\bЗАО\b|\bПАО\b|\bАО\b/i
    if (FOREIGN.test(text)) return 'foreign'
    if (RU.test(text)) return 'ru'
    if (/[а-яё]/i.test(text)) return 'ru'        // 有西里尔但无明显标记 → 偏俄
    // 已知取舍：极少数俄卖家用拉丁转写地址会被误判为国外；宁可这样也别放过拼音/国外地址。勿轻易改。
    if (/[a-z]/i.test(text)) return 'foreign'    // 纯拉丁/拼音地址 → 国外
    return 'unknown'
  }
  // 履约模式：跨境(非本地)卖家在 Ozon 只能 FBS；本地按 FBO 近似(本地自发也可能 FBS，够用)
  function _modeFromOrigin(origin) {
    if (origin === 'foreign') return 'FBS'
    if (origin === 'ru') return 'FBO'
    return ''
  }
  function _firstSellerLink(s) {
    // 优先 productLink（该卖家此商品的报价页，绝对 https），退回卖家店铺链接
    const raw = s.productLink || s.link || s.sellerLink || s.url || (s.seller && s.seller.link) || ''
    if (!raw) return ''
    if (/^https?:\/\//i.test(raw)) return raw
    return OZON_ORIGIN + (raw.startsWith('/') ? raw : '/' + raw)
  }

  function _pickSellers(widgetStates) {
    if (!widgetStates || typeof widgetStates !== 'object') return []
    const keys = Object.keys(widgetStates).filter((k) => k.indexOf('webSellerList-') === 0)
    for (const k of keys) {
      try {
        const raw = widgetStates[k]
        const state = typeof raw === 'string' ? JSON.parse(raw) : raw
        if (state && Array.isArray(state.sellers) && state.sellers.length) return state.sellers
      } catch (e) {
        /* 跳过坏块 */
      }
    }
    return []
  }

  function _empty() {
    return { followCount: 0, priceMin: null, priceMax: null, sellers: [] }
  }

  // 递归在一个 widget state 里找评论数（不写死 key，Ozon 改版也能命中）
  function _deepReviewCount(node, depth) {
    if (!node || typeof node !== 'object' || depth > 6) return null
    if (Array.isArray(node)) {
      for (const n of node) {
        const r = _deepReviewCount(n, depth + 1)
        if (r != null) return r
      }
      return null
    }
    for (const k in node) {
      if (/^(reviewsCount|reviewCount|commentsCount|totalReviews|totalComments)$/i.test(k)) {
        const v = node[k]
        const n = typeof v === 'number' ? v : parseInt(String(v).replace(/[^\d]/g, ''), 10)
        if (Number.isFinite(n) && n >= 0) return n
      }
    }
    for (const k in node) {
      const r = _deepReviewCount(node[k], depth + 1)
      if (r != null) return r
    }
    return null
  }

  // 从商品页 json 取评论数（公开、确定）。评分/评论/评价类 widget 优先，再兜底全扫。
  function parseReviewCount(pageJson) {
    const ws = pageJson && pageJson.widgetStates
    if (!ws || typeof ws !== 'object') return null
    const keys = Object.keys(ws)
    const prefer = keys.filter((k) => /review|score|comment|отзыв/i.test(k))
    const rest = keys.filter((k) => prefer.indexOf(k) < 0)
    for (const k of prefer.concat(rest)) {
      let st
      try {
        st = typeof ws[k] === 'string' ? JSON.parse(ws[k]) : ws[k]
      } catch (e) {
        continue
      }
      const n = _deepReviewCount(st, 0)
      if (n != null) return n
    }
    return null
  }

  // 递归找评分（0–5 浮点）
  function _deepRating(node, depth) {
    if (!node || typeof node !== 'object' || depth > 6) return null
    if (Array.isArray(node)) {
      for (const n of node) {
        const r = _deepRating(n, depth + 1)
        if (r != null) return r
      }
      return null
    }
    for (const k in node) {
      if (/^(totalScore|reviewScore|productScore|rating|score)$/i.test(k)) {
        const v = node[k]
        const n = typeof v === 'number' ? v : parseFloat(String(v).replace(',', '.'))
        if (Number.isFinite(n) && n > 0 && n <= 5) return Math.round(n * 10) / 10
      }
    }
    for (const k in node) {
      const r = _deepRating(node[k], depth + 1)
      if (r != null) return r
    }
    return null
  }

  // 从商品页 json 取评分（公开）。评分/评论类 widget 优先。
  function parseRating(pageJson) {
    const ws = pageJson && pageJson.widgetStates
    if (!ws || typeof ws !== 'object') return null
    const keys = Object.keys(ws)
    const prefer = keys.filter((k) => /review|score|comment|rating|отзыв/i.test(k))
    const rest = keys.filter((k) => prefer.indexOf(k) < 0)
    for (const k of prefer.concat(rest)) {
      let st
      try {
        st = typeof ws[k] === 'string' ? JSON.parse(ws[k]) : ws[k]
      } catch (e) {
        continue
      }
      const n = _deepRating(st, 0)
      if (n != null) return n
    }
    return null
  }

  // 由公开评论数粗估累计销量。Ozon 不公开真实销量/月销量；竞品的「月销量」也是它服务端估的。
  // 经验评论率 3%–7% → 累计销量 ≈ 评论数 ÷ 评论率。这是范围粗估，仅供参考。
  function estimateSales(reviewCount) {
    if (reviewCount == null || !Number.isFinite(reviewCount) || reviewCount < 0) return null
    return {
      reviews: reviewCount,
      salesLow: Math.round(reviewCount / 0.07), // 评论率高(7%)→销量低
      salesHigh: Math.round(reviewCount / 0.03) // 评论率低(3%)→销量高
    }
  }

  function summarizeOtherOffers(pageJson) {
    if (!pageJson || typeof pageJson !== 'object') return _empty()
    const raw = _pickSellers(pageJson.widgetStates)
    if (!raw.length) return _empty()
    const sellers = raw.map((s) => {
      const origin = _sellerOrigin(s)
      return {
        name: _firstSellerName(s),
        price: parseRubPrice(_firstSellerPriceText(s)),
        originalPrice: parseRubPrice(_firstSellerOriginalPriceText(s)),
        link: _firstSellerLink(s),
        origin: origin,
        mode: _modeFromOrigin(origin),
        deliver: _sellerDeliver(s)
      }
    })
    const prices = sellers.map((s) => s.price).filter((p) => p != null)
    return {
      followCount: sellers.length,
      priceMin: prices.length ? Math.min(...prices) : null,
      priceMax: prices.length ? Math.max(...prices) : null,
      sellers
    }
  }

  return { extractProductId, parseRubPrice, summarizeOtherOffers, parseReviewCount, parseRating, estimateSales }
})
