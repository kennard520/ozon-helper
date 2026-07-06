// Wildberries 商品页纯函数（UMD：content script 全局 OzonHelperWb + vitest import）
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperWb = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function nmFromUrl(url) {
    const m = String(url || '').match(/\/catalog\/(\d+)/)
    return m ? m[1] : null
  }

  function isWbProductPage(pathname) {
    return /\/catalog\/\d+\/detail\.aspx/i.test(String(pathname || ''))
  }

  // WB 价接口候选：v4 当前可用(v2 已 404)，留 v3/v2/v1 兜底防改版；命中即用
  function priceCandidateUrls(nm, dest) {
    const d = dest || '-1257786'
    return ['v4', 'v3', 'v2', 'v1'].map(
      (v) => `https://card.wb.ru/cards/${v}/detail?appType=1&curr=rub&dest=${d}&spp=30&nm=${nm}`
    )
  }

  function _product(json) {
    if (!json) return null
    const arr = (json.data && json.data.products) || json.products
    return Array.isArray(arr) && arr.length ? arr[0] : null
  }

  // 价在戈比(÷100 得卢布)：product=售价(折后), basic=划线价(原价, 须 > 售价)
  function parseWbPrice(json) {
    const p = _product(json)
    if (!p) return null
    const price = (p.sizes && p.sizes[0] && p.sizes[0].price) || null
    if (!price || typeof price.product !== 'number') return null
    const oldRub =
      typeof price.basic === 'number' && price.basic > price.product ? Math.round(price.basic) / 100 : ''
    return {
      price_rub: Math.round(price.product) / 100,
      old_rub: oldRub,
      rating: typeof p.rating === 'number' ? p.rating : (typeof p.reviewRating === 'number' ? p.reviewRating : null),
      feedbacks: typeof p.feedbacks === 'number' ? p.feedbacks : null
    }
  }

  // ===== card.json 解析（从后端 collector_wb.py 移植，纯函数）=====
  function volPart(nm) {
    const n = parseInt(nm, 10)
    return { vol: Math.floor(n / 100000), part: Math.floor(n / 1000) }
  }

  function _numFromValue(v) {
    const m = String(v == null ? '' : v).match(/\d+(?:[.,]\d+)?/)
    return m ? parseFloat(m[0].replace(',', '.')) : null
  }

  function _weightG(options) {
    for (const o of options || []) {
      if (String((o && o.name) || '').toLowerCase().includes('вес')) {
        const kg = _numFromValue(o.value)
        if (kg != null) return Math.round(kg * 1000)   // кг → g
      }
    }
    return null
  }

  function _dimsMm(options) {
    const keymap = { 'длина': 'length_mm', 'ширина': 'width_mm', 'высота': 'height_mm' }
    const out = {}
    for (const o of options || []) {
      const name = String((o && o.name) || '').toLowerCase()
      for (const ru in keymap) {
        const key = keymap[ru]
        if (name.includes(ru) && !(key in out)) {
          const cm = _numFromValue(o.value)
          if (cm != null) out[key] = Math.round(cm * 10)   // см → mm
        }
      }
    }
    return out
  }

  function _optionItems(card) {
    const out = []
    const seen = new Set()
    const add = (o) => {
      const name = String((o && o.name) || '').trim()
      const value = String((o && o.value) || '').trim()
      if (!name || !value) return
      const key = `${name}\u0000${value}`
      if (seen.has(key)) return
      seen.add(key)
      out.push({ name, value })
    }
    ;((card && card.options) || []).forEach(add)
    ;((card && card.grouped_options) || []).forEach((group) => {
      ;((group && group.options) || []).forEach(add)
    })
    return out
  }

  function _attributes(card) {
    const out = []
    for (const o of _optionItems(card)) out.push({ name: o.name, value: o.value })
    return out
  }

  function imageUrls(host, vol, part, nm, photoCount) {
    const n = Math.max(1, parseInt(photoCount, 10) || 0)
    const base = `https://${host}/vol${vol}/part${part}/${nm}/images/big`
    const out = []
    for (let i = 1; i <= n; i++) out.push(`${base}/${i}.webp`)
    return out
  }

  function variantIds(card, fallbackNm) {
    const out = []
    const seen = new Set()
    const add = (v) => {
      const raw = v && typeof v === 'object' ? (v.nm_id || v.id || v.nm) : v
      const id = String(raw || '').trim()
      if (!/^\d+$/.test(id) || seen.has(id)) return
      seen.add(id)
      out.push(id)
    }
    ;((card && card.full_colors) || []).forEach(add)
    ;((card && card.colors) || []).forEach(add)
    if (!out.length) add(fallbackNm || (card && card.nm_id))
    return out
  }

  function variantGroup(card, fallbackNm) {
    const raw = (card && (card.imt_id || card.root)) || fallbackNm
    const id = String(raw || '').trim()
    return id ? `wb-${id}` : ''
  }

  function variantLink(nm) {
    return `https://www.wildberries.ru/catalog/${nm}/detail.aspx`
  }

  function variants(card, fallbackNm) {
    return variantIds(card, fallbackNm).map((id) => ({
      sku: id,
      label: id,
      link: variantLink(id),
      available: true
    }))
  }

  function cardJsonUrlFromEntries(entries, nm) {
    const id = String(nm || '').trim()
    if (!id || !Array.isArray(entries)) return null
    for (let i = entries.length - 1; i >= 0; i--) {
      const raw = typeof entries[i] === 'string' ? entries[i] : (entries[i] && entries[i].name)
      if (!raw) continue
      try {
        const u = new URL(String(raw))
        const path = u.pathname.toLowerCase()
        if (/\/vol\d+\/part\d+\/\d+\/info\/ru\/card\.json$/.test(path) && path.includes(`/${id}/info/ru/card.json`)) {
          return u.href
        }
      } catch (e) { /* ignore invalid resource names */ }
    }
    return null
  }

  function loadedCardJsonUrl(nm) {
    if (typeof performance === 'undefined' || !performance.getEntriesByType) return null
    try {
      return cardJsonUrlFromEntries(performance.getEntriesByType('resource'), nm)
    } catch (e) {
      return null
    }
  }

  // card.json → collect-parsed 的 data（键名对齐 Ozon 路径：title/description/images...；
  // WB 俄语直接用；options 放 source_raw 供后端 auto-map/AI；价后续就地取）
  function parseCard(card, host, nm) {
    card = card || {}
    const { vol, part } = volPart(nm)
    const options = _optionItems(card)
    const title = String(card.imt_name || '').trim()
    const media = card.media || {}
    const selling = card.selling || {}
    const vg = variantGroup(card, nm)
    const vlist = variants(card, nm)
    const ids = variantIds(card, nm)
    const attrs = _attributes(card)
    const pageAttrs = String(nm || '').trim()
      ? [{ name: 'Артикул', value: String(nm).trim() }, ...attrs]
      : attrs
    const data = {
      source_platform: 'wb',
      title: title,                 // 后端 → source_title + ozon_title
      description: String(card.description || '').trim(),
      attributes: pageAttrs,  // 名值对 → draft.attributes，喂 auto-map/AI
      weight_g: _weightG(options),
      images: imageUrls(host, vol, part, nm, media.photo_count),
      price: '', old_price: '', video_url: '',
      variant_group: vg,
      variants: vlist,
      variant_label: title,
      source_raw: {
        nm_id: nm, imt_id: card.imt_id, imt_name: title,
        title: title,
        description_text: String(card.description || '').trim(),
        sku_id: nm,
        spec_attrs: title,
        variant_group: vg,
        variants: vlist,
        colors: ids,
        full_colors: card.full_colors || [],
        brand_name: String(selling.brand_name || ''),
        brand_hash: String(selling.brand_hash || ''),
        supplier_id: selling.supplier_id,
        vendor_code: card.vendor_code,
        slug: card.slug,
        subj_name: card.subj_name,
        subj_root_name: card.subj_root_name,
        contents: card.contents,
        data: card.data || {},
        grouped_options: card.grouped_options || [],
        nm_colors_names: card.nm_colors_names,
        options: attrs,   // 俄语名值对，喂 auto-map/AI
        photo_count: media.photo_count,
        basket_host: host
      }
    }
    Object.assign(data, _dimsMm(options))
    return data
  }

  // 按估算起点生成 card.json 候选地址（vol→basket 大致单调；偏差由全范围兜底）
  function basketCardUrls(nm) {
    const n = parseInt(nm, 10)
    const { vol, part } = volPart(n)
    const MAX = 100
    const out = []
    const seen = new Set()
    const add = (host) => {
      if (!host || seen.has(host)) return
      seen.add(host)
      out.push({ host, url: `https://${host}/vol${vol}/part${part}/${n}/info/ru/card.json` })
    }
    if (vol >= 10000) {
      const cdn = Math.max(1, Math.floor(vol / 500))
      ;[cdn, cdn - 1, cdn + 1].forEach((b) => {
        if (b >= 1 && b <= MAX) add(`mow-basket-cdn-${String(b).padStart(2, '0')}.geobasket.ru`)
      })
    }
    let est = Math.round(19 + (vol - 3064) * (41 - 19) / (9816 - 3064))
    est = Math.max(1, Math.min(est, MAX))
    const order = []
    for (let b = est; b <= MAX; b++) order.push(b)
    for (let b = est - 1; b >= 1; b--) order.push(b)
    order.forEach((b) => add(`basket-${String(b).padStart(2, '0')}.wbbasket.ru`))
    return out
  }

  return {
    nmFromUrl, isWbProductPage, priceCandidateUrls, parseWbPrice,
    volPart, imageUrls, variantIds, variantGroup, variantLink, variants,
    parseCard, basketCardUrls, cardJsonUrlFromEntries, loadedCardJsonUrl
  }
})
