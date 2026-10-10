// 媒体重托管纯函数（UMD：content script 全局 OzonHelperMedia + vitest import）
// 思路：采集来的非 Ozon 媒体(1688/WB/淘宝图)在 Ozon 不渲染 → 插件把它们下载后
// 用登录 cookie 传到「自己的 Ozon 店铺」媒体库(ir.ozone.ru) → 换链接 → 再推后端。
// 已是 Ozon CDN(ir.ozone.ru 等)的图本就能渲染，跳过不重传。
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperMedia = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  // 是否已经是 Ozon 自家 CDN（无需重传）
  function isOzonCdn(url) {
    const s = String(url || '')
    return /(^|\/\/|\.)(ozone\.ru|ozon\.ru|ozonusercontent\.com)\//.test(s) || /\bir\.ozone\.ru\b/.test(s)
  }

  // 递归收集富文本(rich_content_json)里的内嵌图 img.src / img.srcMobile
  function _collectRich(node, set) {
    if (Array.isArray(node)) {
      node.forEach((x) => _collectRich(x, set))
    } else if (node && typeof node === 'object') {
      const img = node.img
      if (img && typeof img === 'object') {
        ;['src', 'srcMobile'].forEach((k) => {
          const v = img[k]
          if (typeof v === 'string' && v.trim()) set.add(v)
        })
      }
      Object.keys(node).forEach((k) => {
        if (k !== 'img') _collectRich(node[k], set)
      })
    }
  }

  // 按 {原URL: 新URL} 替换富文本内嵌图
  function _applyRich(node, map) {
    if (Array.isArray(node)) {
      node.forEach((x) => _applyRich(x, map))
    } else if (node && typeof node === 'object') {
      const img = node.img
      if (img && typeof img === 'object') {
        ;['src', 'srcMobile'].forEach((k) => {
          if (typeof img[k] === 'string' && map[img[k]]) img[k] = map[img[k]]
        })
      }
      Object.keys(node).forEach((k) => {
        if (k !== 'img') _applyRich(node[k], map)
      })
    }
  }

  // 收集草稿里所有媒体 URL（去重；只跳过空值）。
  // 不管来源是 Ozon/WB/1688，都要重传到「自己的店铺」媒体库——竞品图哪怕在 ir.ozone.ru
  // 也是别人账号的媒体，必须换成自己店铺的。data 字段：images[] / detail_images[] / video_url / rich_content_json
  function collectMediaUrls(data) {
    const set = new Set()
    const add = (u) => {
      if (typeof u === 'string' && u.trim()) set.add(u.trim())
    }
    if (data) {
      ;(data.images || []).forEach(add)
      ;(data.detail_images || []).forEach(add)
      add(data.video_url)
      if (data.rich_content_json) {
        const rich = new Set()
        _collectRich(data.rich_content_json, rich)
        rich.forEach(add)
      }
    }
    return Array.from(set)
  }

  // 用 {原URL: ir.ozone.ru URL} 重写草稿所有媒体；返回新对象（不就地改原 data）
  function applyMediaMap(data, map) {
    if (!data) return data
    map = map || {}
    const out = Object.assign({}, data)
    const sub = (u) => (typeof u === 'string' && map[u] ? map[u] : u)
    out.images = (data.images || []).map(sub)
    out.detail_images = (data.detail_images || []).map(sub)
    if (data.video_url) out.video_url = sub(data.video_url)
    if (data.rich_content_json) {
      const rich = JSON.parse(JSON.stringify(data.rich_content_json))
      _applyRich(rich, map)
      out.rich_content_json = rich
    }
    return out
  }

  // 从 cookie 串里扫出卖家 companyId（实测在 seller.ozon.ru 的 cookie 里，如 companyId=5020196）
  function parseCompanyId(cookieStr) {
    const re = /compan(?:yId|y_id|y)["':=\s]+(\d{4,})/i
    const s = String(cookieStr || '')
    let m = s.match(re)
    if (!m) {
      try { m = decodeURIComponent(s).match(re) } catch (e) { /* 坏编码忽略 */ }
    }
    return m ? m[1] : null
  }

  return { isOzonCdn, collectMediaUrls, applyMediaMap, parseCompanyId }
})
