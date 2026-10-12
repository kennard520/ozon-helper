;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbMediaResolver = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function galleryUrls(card, cardUrl, nm) {
    const id = String(nm || '').trim()
    if (!isAllowedMediaUrl(cardUrl, id, 'gallery')) return []
    const url = new URL(cardUrl)
    if (!url.pathname.endsWith(`/${id}/info/ru/card.json`)) return []
    const count = Math.max(0, Number.parseInt(card && card.media && card.media.photo_count, 10) || 0)
    const prefix = url.pathname.replace(`/${id}/info/ru/card.json`, `/${id}/images/big`)
    return Array.from({ length: count }, (_, index) => `${url.origin}${prefix}/${index + 1}.webp`)
  }

  function richJsonUrl(cardUrl) {
    return String(cardUrl).replace(/\/card\.json(?:\?.*)?$/, '/rich_v1.json')
  }

  function ensureWebp(url) {
    return /\.[a-z0-9]{2,5}(?:[?#]|$)/i.test(url) ? url : `${url}.webp`
  }

  function safeRichImageUrl(src) {
    if (typeof src !== 'string' || !src) return null
    const url = ensureWebp(src)
    return isAllowedMediaUrl(url, '', 'rich') ? url : null
  }

  function richImageUrls(richJson) {
    const content = Array.isArray(richJson && richJson.content) ? richJson.content : []
    const out = []
    for (const widget of content) {
      for (const block of (widget && widget.blocks) || []) {
        const src = block && block.image && block.image.src
        const url = safeRichImageUrl(src)
        if (url) out.push(url)
      }
    }
    if (!out.length && richJson && richJson.preview && richJson.preview.src) {
      const url = safeRichImageUrl(richJson.preview.src)
      if (url) out.push(url)
    }
    return [...new Set(out)]
  }

  function isAllowedMediaUrl(raw, nm, kind) {
    try {
      const url = new URL(raw)
      if (url.protocol !== 'https:' || !/\.(?:wbbasket|geobasket|wb)\.ru$/i.test(url.hostname)) return false
      if (kind === 'gallery' || kind === 'video') {
        return url.pathname.includes(`/${String(nm || '')}/`)
      }
      return kind === 'rich' && url.hostname.toLowerCase().startsWith('content-') &&
        /\.(?:avif|gif|jpe?g|png|webp)$/i.test(url.pathname)
    } catch (_) {
      return false
    }
  }

  function videoCandidates(card, nm, observedUrls) {
    const id = String(nm || '').trim()
    const out = []
    const seen = new Set()
    const add = (raw) => {
      if (typeof raw !== 'string' || seen.has(raw)) return
      let url
      try {
        url = new URL(raw)
      } catch (_) {
        return
      }
      if (!url.pathname.toLowerCase().endsWith('.mp4') || !isAllowedMediaUrl(url.href, id, 'video')) return
      seen.add(url.href)
      out.push(url.href)
    }
    const inspect = (node, inVideoField) => {
      if (typeof node === 'string') {
        if (inVideoField) add(node)
        return
      }
      if (Array.isArray(node)) {
        for (const item of node) inspect(item, inVideoField)
        return
      }
      if (!node || typeof node !== 'object') return
      for (const [key, value] of Object.entries(node)) {
        const childInVideoField = inVideoField || String(key).toLowerCase().includes('video')
        if (childInVideoField || (value && typeof value === 'object')) inspect(value, childInVideoField)
      }
    }

    inspect(card, false)
    for (const url of observedUrls || []) add(url)

    if (card && card.media && card.media.has_video && /^\d+$/.test(id)) {
      const n = Number.parseInt(id, 10)
      const vol = n % 144
      const part = Math.floor(n / 10000)
      const bucket = Math.floor(vol / 12) + 1
      const host = `videonme-basket-${String(bucket).padStart(2, '0')}.wbbasket.ru`
      for (const quality of ['720p', '480p', '360p']) {
        add(`https://${host}/vol${vol}/part${part}/${n}/mp4/${quality}/1.mp4`)
      }
    }
    return out
  }

  async function resolveVideo(candidates, probe) {
    for (const candidate of candidates || []) {
      try {
        if (await probe(candidate)) return candidate
      } catch (_) { continue }
    }
    return null
  }

  return {
    galleryUrls, richJsonUrl, richImageUrls,
    videoCandidates, resolveVideo, isAllowedMediaUrl
  }
})
