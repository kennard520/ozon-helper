;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbMediaPath = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  const INVALID_WINDOWS_CHARS = /[<>:"/\\|?*\x00-\x1F]+/g
  const WINDOWS_DEVICE = /^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$/i

  function trimWindowsEnding(value) {
    return value.replace(/^[ .]+|[ .]+$/g, '')
  }

  function sanitizeSegment(value, fallback = '未命名', maxLength = 80) {
    const numericLimit = Number(maxLength)
    const limit = Number.isFinite(numericLimit) ? Math.max(1, Math.floor(numericLimit)) : 80
    const clean = (input) => trimWindowsEnding(String(input == null ? '' : input)
      .replace(INVALID_WINDOWS_CHARS, '_'))

    let segment = clean(value) || clean(fallback) || '未命名'
    for (;;) {
      segment = trimWindowsEnding(segment.slice(0, limit))
      if (!segment) segment = clean(fallback) || '未命名'
      if (!WINDOWS_DEVICE.test(segment)) return segment
      segment = `_${segment}`
    }
  }

  function pad(value) {
    return String(value).padStart(2, '0')
  }

  function formatBatchTime(date) {
    const value = date instanceof Date ? date : new Date(date)
    return `${value.getFullYear()}${pad(value.getMonth() + 1)}${pad(value.getDate())}-` +
      `${pad(value.getHours())}${pad(value.getMinutes())}${pad(value.getSeconds())}`
  }

  function extensionFromUrl(rawUrl, fallback = 'bin') {
    const safeFallback = String(fallback || 'bin').replace(/^\.+/, '').toLowerCase()
    const defaultExtension = /^[a-z0-9]{1,10}$/.test(safeFallback) ? safeFallback : 'bin'
    try {
      const pathname = new URL(String(rawUrl || '')).pathname
      const match = pathname.match(/\.([a-z0-9]{1,10})$/i)
      return match ? match[1].toLowerCase() : defaultExtension
    } catch (_) {
      return defaultExtension
    }
  }

  return { sanitizeSegment, formatBatchTime, extensionFromUrl }
})
