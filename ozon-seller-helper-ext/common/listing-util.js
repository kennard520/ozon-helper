// 列表页卡片纯逻辑（UMD：content script 全局 OzonHelperListing + vitest import）
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperListing = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function _pid(href) {
    const m = String(href || '').match(/\/product\/[^/?#]*?(\d+)\/?(?:[?#]|$)/)
    return m ? m[1] : null
  }

  function uniqueProductIds(hrefs) {
    const out = []
    const seen = new Set()
    for (const h of hrefs || []) {
      const pid = _pid(h)
      if (pid && !seen.has(pid)) {
        seen.add(pid)
        out.push(pid)
      }
    }
    return out
  }

  function _editBtn() {
    return '<button class="ohl-edit" type="button">编辑上架</button>'
  }

  // 多变体商品(variantCount>1)才显示「采集全部变体」——逐变体各建草稿、同 variant_group 合并
  function _variantsBtn(n) {
    return `<button class="ohl-variants" type="button">采集全部变体(${n})</button>`
  }

  function _fmtShort(n) {
    if (n >= 10000) return (n / 10000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, '') + '万'
    return String(n)
  }

  // 每个指标一行：跟卖家数 / 最低价 / 销量(估) / 评分（缺的不出行）
  // 注意：销量/评分与跟卖无关（来自商品页评论数），无跟卖时也要照常显示，别被"无跟卖"吞掉
  function _metricLines(state) {
    const s = state.summary
    const out = []
    if (!s || s.followCount === 0) {
      out.push('无跟卖')
    } else {
      out.push(`跟卖 <b>${s.followCount}</b> 家`)
      if (s.priceMin != null) out.push(`最低 ${s.priceMin} ₽`)
    }
    if (state.estimate) out.push(`销量(估) <b>${_fmtShort(state.estimate.salesLow)}–${_fmtShort(state.estimate.salesHigh)}</b>`)
    if (state.rating != null) out.push(`★ ${state.rating}`)
    return out
  }

  function _info(lines) {
    return '<div class="ohl-info">' + lines.map((t) => `<div class="ohl-line">${t}</div>`).join('') + '</div>'
  }

  // state: {loading} | {error} | {summary:{followCount,priceMin,priceMax}, estimate?:{salesLow,salesHigh}, rating?}
  function cardHtml(state) {
    state = state || {}
    if (state.loading) return _info(['加载中…']) + _editBtn()
    if (state.error) return _info(['未获取']) + _editBtn()
    const vbtn = (state.variantCount > 1) ? _variantsBtn(state.variantCount) : ''
    return _info(_metricLines(state)) + _editBtn() + vbtn
  }

  return { uniqueProductIds, cardHtml }
})
