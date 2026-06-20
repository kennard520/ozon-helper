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

  // 去标签取纯文本
  function _text(s) {
    return String(s == null ? '' : s).replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, ' ').trim()
  }
  // ant-descriptions HTML → [{name,value}]。label/content 在 HTML 里成对交替出现，按序配对。
  function parseAttributes(html) {
    if (typeof html !== 'string' || !html) return []
    const tokens = []
    const re = /ant-descriptions-item-(label|content)[^>]*>([\s\S]*?)<\/(?:th|td)>/gi
    let m
    while ((m = re.exec(html))) tokens.push({ kind: m[1], text: _text(m[2]) })
    const out = []
    for (let i = 0; i < tokens.length - 1; i++) {
      if (tokens[i].kind === 'label' && tokens[i + 1].kind === 'content') {
        const name = tokens[i].text
        const value = tokens[i + 1].text
        if (name && value) out.push({ name, value })
        i++ // 跳过已配对的 content
      }
    }
    return out
  }

  // 安全取嵌套字段
  function _get(obj, path) {
    let cur = obj
    for (const k of path) {
      if (cur == null) return undefined
      cur = cur[k]
    }
    return cur
  }

  // 主数据：全商品共用字段（变体专属的价/克重/变体图见 expandSkus）
  // data = window.context.result.data；detailHtml = window.offer_details.content；attrHtml = 属性容器 outerHTML
  function parse1688Base(data, detailHtml, attrHtml, url) {
    data = data || {}
    const title = _get(data, ['productTitle', 'fields', 'title']) || ''
    const images = _get(data, ['gallery', 'fields', 'offerImgList'])
    const imgs = Array.isArray(images) ? images.filter((u) => typeof u === 'string' && u) : []
    const video = _get(data, ['gallery', 'fields', 'video']) || {}
    const priceDisplay = _get(data, ['mainPrice', 'fields', 'priceModel', 'originalPriceDisplay']) || ''
    return {
      source_platform: '1688',
      title: title,
      description: '',                       // 留空，webui AI 生成俄语
      images: imgs,
      detail_images: [],
      rich_content_json: buildRichContent(parseDetailImages(detailHtml)),
      video_url: typeof video.videoUrl === 'string' ? video.videoUrl : '',
      attributes: parseAttributes(attrHtml),
      price: '', old_price: '',              // 变体展开时填
      weight_g: null, length_mm: null, width_mm: null, height_mm: null,  // 变体展开时按 skuId 填
      category_path: '',
      source_raw: {
        offer_id: extractOfferId(url),
        price_display: priceDisplay,
        video_cover: typeof video.coverUrl === 'string' ? video.coverUrl : '',
        attributes: parseAttributes(attrHtml)
      }
    }
  }

  // 按 skuId 在 pieceWeightScaleInfo 找克重尺寸（weight 已是克、长宽高已是 mm）
  function _packBySkuId(packInfo, skuId) {
    for (const p of packInfo || []) {
      if (p && p.skuId === skuId) {
        return {
          weight_g: typeof p.weight === 'number' ? p.weight : null,
          length_mm: typeof p.length === 'number' ? p.length : null,
          width_mm: typeof p.width === 'number' ? p.width : null,
          height_mm: typeof p.height === 'number' ? p.height : null
        }
      }
    }
    return { weight_g: null, length_mm: null, width_mm: null, height_mm: null }
  }

  // 在 skuProps 维度值里按规格名找变体图（单维度：specAttrs === value.name）
  function _variantImage(skuProps, specAttrs) {
    for (const prop of skuProps || []) {
      for (const v of (prop && prop.value) || []) {
        if (v && v.name && specAttrs.indexOf(v.name) >= 0 && v.imageUrl) return v.imageUrl
      }
    }
    return ''
  }

  // 区间最低价（"18.79-141.63" → "18.79"）
  function _lowestFromDisplay(disp) {
    const nums = String(disp || '').match(/\d+(?:\.\d+)?/g)
    return nums && nums.length ? nums[0] : ''
  }

  // 全量 SKU 展开 → 变体草稿数组
  function expandSkus(data, base) {
    data = data || {}
    base = base || {}
    const skuModel = _get(data, ['Root', 'fields', 'dataJson', 'skuModel']) || {}
    const infoMap = skuModel.skuInfoMap || {}
    const skuProps = skuModel.skuProps || []
    const packInfo = _get(data, ['productPackInfo', 'fields', 'pieceWeightScale', 'pieceWeightScaleInfo']) || []
    const keys = Object.keys(infoMap)
    const baseImgs = Array.isArray(base.images) ? base.images : []

    if (!keys.length) {
      // 无 SKU：单条，价取区间最低
      const price = _lowestFromDisplay(_get(base, ['source_raw', 'price_display']))
      return [Object.assign({}, base, { price: price })]
    }

    return keys.map((k) => {
      const sku = infoMap[k] || {}
      const dims = _packBySkuId(packInfo, sku.skuId)
      const vimg = _variantImage(skuProps, sku.specAttrs || k)
      const images = []
      const push = (u) => { if (u && images.indexOf(u) < 0) images.push(u) }
      push(vimg)
      baseImgs.forEach(push)
      return Object.assign({}, base, {
        price: sku.price != null ? String(sku.price) : '',
        variant_label: sku.specAttrs || k,
        weight_g: dims.weight_g,
        length_mm: dims.length_mm,
        width_mm: dims.width_mm,
        height_mm: dims.height_mm,
        images: images,
        source_raw: Object.assign({}, base.source_raw, {
          sku_id: sku.skuId, spec_id: sku.specId, spec_attrs: sku.specAttrs, stock: sku.canBookCount
        })
      })
    })
  }

  return { extractOfferId, parseDetailImages, buildRichContent, parseAttributes, parse1688Base, expandSkus }
})
