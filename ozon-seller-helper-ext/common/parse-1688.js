// ozon-seller-helper-ext/common/parse-1688.js
// 1688 商品页纯函数（UMD：content script 全局 OzonHelperParse1688 + vitest import）
// 数据源：window.context.result.data（主数据）/ window.offer_details.content（详情HTML）/ DOM 属性表
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperParse1688 = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  // 从 detail.1688.com/offer/<id>.html 提取 offerId（作 variant_group / source_offer_id）
  function extractOfferId(url) {
    const m = String(url || '').match(/\/offer\/(\d+)\.html/)
    return m ? m[1] : ''
  }

  // 从详情 HTML 提取 <img src>，只留 http(s)，去 query，按出现顺序去重
  function parseDetailImages(html) {
    if (typeof html !== 'string' || !html) return []
    const out = []
    const seen = new Set()
    const re = /<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']/gi
    let m
    while ((m = re.exec(html))) {
      let u = (m[1] || '').trim()
      if (!/^https?:\/\//i.test(u)) continue
      u = u.split('?')[0]
      if (!seen.has(u)) { seen.add(u); out.push(u) }
    }
    return out
  }

  // 详情图列表 → Ozon richAnnotationJson（A+富文本）；每张图一个 raShowcase 块。
  // 内嵌图节点为 {img:{src,srcMobile}}，与 media-upload._collectRich 对齐 → 发布前自动传 OSS。
  function buildRichContent(imgUrls) {
    const list = Array.isArray(imgUrls) ? imgUrls.filter((u) => typeof u === 'string' && u) : []
    if (!list.length) return null
    return {
      content: list.map((u) => ({
        widgetName: 'raShowcase',
        type: 'billboard',
        blocks: [{ img: { src: u, srcMobile: u, alt: '' } }]
      })),
      version: 0.3
    }
  }

  return { extractOfferId, parseDetailImages, buildRichContent }
})
