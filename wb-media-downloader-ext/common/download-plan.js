;(function (root, factory) {
  const pathApi = typeof module === 'object' && module.exports
    ? require('./file-path.js')
    : root.WbMediaPath
  const api = factory(pathApi)
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbDownloadPlan = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function (WbMediaPath) {
  const MAX_SEGMENT_LENGTH = 80

  function stableId(value, fallback, field) {
    const id = String(value == null ? '' : value).trim() || fallback
    const safe = WbMediaPath.sanitizeSegment(id, fallback, Math.max(MAX_SEGMENT_LENGTH, id.length + 1))
    if (safe !== id) throw new Error(`${field} must be Windows-safe so it can be preserved in the path`)
    return id
  }

  function productParts(product) {
    const value = product || {}
    const imtId = stableId(value.imtId, 'unknown', 'imtId')
    const suffix = `_imt-${imtId}`
    if (suffix.length > MAX_SEGMENT_LENGTH) {
      throw new RangeError('imtId suffix cannot fit in the 80-character product path segment')
    }
    const title = WbMediaPath.sanitizeSegment(value.title, '商品', MAX_SEGMENT_LENGTH)
    return { title, suffix }
  }

  function productSegment(product) {
    const { title, suffix } = productParts(product)
    const available = MAX_SEGMENT_LENGTH - suffix.length
    const shortenedTitle = title.slice(0, available).replace(/[ .]+$/g, '')
    return `${shortenedTitle}${suffix}`
  }

  function buildBatchRoot(product, date) {
    return `WB下载/${productSegment(product)}/${WbMediaPath.formatBatchTime(date)}`
  }

  function variantSegment(variant, index, nm) {
    const number = String(index + 1).padStart(2, '0')
    const prefix = `${number}_`
    const suffix = `_nm-${nm}`
    const available = MAX_SEGMENT_LENGTH - prefix.length - suffix.length
    if (available < 0) {
      throw new RangeError('nm suffix and variant index cannot fit in the 80-character variant path segment')
    }
    const label = available === 0
      ? ''
      : WbMediaPath.sanitizeSegment(variant && variant.label, `变体${number}`, available)
    return `${prefix}${label}${suffix}`
  }

  function addKind(items, base, nm, kind, folder, urls, fallbackExt, convert) {
    ;[...new Set(urls || [])].forEach((url, index) => {
      const ext = convert || WbMediaPath.extensionFromUrl(url, fallbackExt)
      items.push({
        id: `${nm}:${kind}:${index + 1}`,
        nm,
        kind,
        url,
        filename: `${base}/${folder}/${String(index + 1).padStart(2, '0')}.${ext}`,
        status: 'pending',
        attempts: 0,
        error: '',
        convertTo: convert || ''
      })
    })
  }

  function populateItems(product, variants, date) {
    const root = buildBatchRoot(product, date)
    const items = []
    ;(variants || []).forEach((variant, index) => {
      const nm = stableId(variant && variant.nm, 'unknown', 'nm')
      const base = `${root}/${variantSegment(variant, index, nm)}`
      addKind(items, base, nm, 'gallery', '轮播图', variant && variant.gallery, 'jpg', 'jpg')
      addKind(items, base, nm, 'video', '视频', variant && variant.videos, 'mp4', '')
    })
    return items
  }

  function buildDownloadPlan(product, variants, date) {
    return populateItems(product, variants, date)
  }

  return { buildBatchRoot, buildDownloadPlan }
})
