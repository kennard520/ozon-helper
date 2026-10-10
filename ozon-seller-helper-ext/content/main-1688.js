// 主世界(MAIN world)桥接脚本。
// content script 跑在隔离世界，读不到页面自己的 JS 全局(window.context / window.offer_details)；
// 本脚本由 manifest 以 world:"MAIN" 注入页面主世界，能读到这些全局。
// 收到隔离世界经 window.postMessage 发来的 {__oh1688:'req'} 后，回传裁剪后的页面数据(slim)+详情HTML。
// 只取解析所需模块，避免把整个 window.context(体积大/含敏感)跨界传输。
;(function () {
  function g(o, path) {
    var cur = o
    for (var i = 0; i < path.length; i++) { if (cur == null) return undefined; cur = cur[path[i]] }
    return cur
  }
  function buildSlim() {
    var d = g(window, ['context', 'result', 'data']) || {}
    var sku = g(d, ['Root', 'fields', 'dataJson', 'skuModel']) || {}
    return {
      productTitle: { fields: { title: g(d, ['productTitle', 'fields', 'title']) } },
      mainPrice: { fields: {
        priceModel: { originalPriceDisplay: g(d, ['mainPrice', 'fields', 'priceModel', 'originalPriceDisplay']) },
        finalPriceModel: { tradeWithoutPromotion: {
          offerPriceDisplay: g(d, ['mainPrice', 'fields', 'finalPriceModel', 'tradeWithoutPromotion', 'offerPriceDisplay']),
          offerMaxPrice: g(d, ['mainPrice', 'fields', 'finalPriceModel', 'tradeWithoutPromotion', 'offerMaxPrice'])
        } }
      } },
      gallery: { fields: { mainImage: g(d, ['gallery', 'fields', 'mainImage']), offerImgList: g(d, ['gallery', 'fields', 'offerImgList']), video: g(d, ['gallery', 'fields', 'video']) } },
      productPackInfo: { fields: { pieceWeightScale: { pieceWeightScaleInfo: g(d, ['productPackInfo', 'fields', 'pieceWeightScale', 'pieceWeightScaleInfo']) } } },
      Root: { fields: { dataJson: { skuModel: { skuProps: sku.skuProps, skuInfoMap: sku.skuInfoMap } } } }
    }
  }
  window.addEventListener('message', function (e) {
    if (e.source !== window) return
    var m = e.data
    if (!m || m.__oh1688 !== 'req') return
    var res
    try {
      res = { __oh1688: 'res', reqId: m.reqId, data: buildSlim(), detailHtml: g(window, ['offer_details', 'content']) || '' }
    } catch (err) {
      res = { __oh1688: 'res', reqId: m.reqId, data: null, detailHtml: '' }
    }
    window.postMessage(res, '*')
  })
})()
