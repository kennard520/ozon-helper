// 站点识别（纯函数，UMD：content script 全局 OzonHelperSite + vitest import）
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperSite = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function detectSite(hostname) {
    const h = String(hostname || '').toLowerCase()
    if (/(^|\.)ozon\.ru$/.test(h)) return 'ozon'
    if (/(^|\.)1688\.com$/.test(h)) return '1688'
    if (/(^|\.)(yangkeduo|pinduoduo)\.com$/.test(h)) return 'pdd'
    if (/(^|\.)wildberries\.ru$/.test(h)) return 'wb'
    return null
  }

  // 各站点商品价的币种：俄区(Ozon/WB)=卢布，国内(1688/拼多多)=人民币。
  // 用于采集时判断是否要把价换算成人民币（后端统一 CNY）。
  function currencyOf(site) {
    if (site === 'ozon' || site === 'wb') return 'RUB'
    if (site === '1688' || site === 'pdd') return 'CNY'
    return null
  }

  return { detectSite, currencyOf }
})
