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
    // 主图优先 mainImage(干净的主图轮播)；offerImgList 是全量(含各尺寸变体缩略图，会"很多都一样")，仅兜底
    const mainImg = _get(data, ['gallery', 'fields', 'mainImage'])
    const offerImg = _get(data, ['gallery', 'fields', 'offerImgList'])
    const pick = (Array.isArray(mainImg) && mainImg.length) ? mainImg : offerImg
    const imgs = Array.isArray(pick) ? pick.filter((u) => typeof u === 'string' && u) : []
    const video = _get(data, ['gallery', 'fields', 'video']) || {}
    // 1688 改版后价在 finalPriceModel.tradeWithoutPromotion(offerPriceDisplay 区间 / offerMaxPrice 最贵档)；
    // 旧版兜底 priceModel.originalPriceDisplay。阶梯价取最贵那档(小批量实付价)。
    const fpm = _get(data, ['mainPrice', 'fields', 'finalPriceModel', 'tradeWithoutPromotion']) || {}
    const priceDisplay =
      fpm.offerPriceDisplay ||
      (fpm.offerMaxPrice != null ? String(fpm.offerMaxPrice) : '') ||
      _get(data, ['mainPrice', 'fields', 'priceModel', 'originalPriceDisplay']) ||
      ''
    const attrs = parseAttributes(attrHtml)
    return {
      source_platform: '1688',
      title: title,
      description: '',                       // 留空，webui AI 生成俄语
      images: imgs,
      detail_images: [],
      rich_content_json: buildRichContent(parseDetailImages(detailHtml)),
      video_url: typeof video.videoUrl === 'string' ? video.videoUrl : '',
      attributes: attrs,
      price: '', old_price: '',              // 变体展开时填
      weight_g: null, length_mm: null, width_mm: null, height_mm: null,  // 变体展开时按 skuId 填
      category_path: '',
      source_raw: {
        offer_id: extractOfferId(url),
        price_display: priceDisplay,
        video_cover: typeof video.coverUrl === 'string' ? video.coverUrl : '',
        attributes: attrs
      }
    }
  }

  // 按 skuId 在 pieceWeightScaleInfo 找克重尺寸(包装表 parsePackInfo 是首选，此为回退)。
  // 1688 长宽高是【毫米】，草稿列统一存【毫米】→ 直存不换算。weight 两边都用【克】。
  function _packBySkuId(packInfo, skuId) {
    const mm = (v) => (typeof v === 'number' ? Math.round(v) : null)
    for (const p of packInfo || []) {
      if (p && p.skuId === skuId) {
        return {
          weight_g: typeof p.weight === 'number' ? p.weight : null,
          length_mm: mm(p.length),
          width_mm: mm(p.width),
          height_mm: mm(p.height)
        }
      }
    }
    return { weight_g: null, length_mm: null, width_mm: null, height_mm: null }
  }

  // 解析「商品件重尺」HTML 表(module-od-product-pack-info)→ [{color,spec,length_cm,width_cm,height_cm,weight_g}]。
  // 表头明确带单位(长(cm)/重量(g))，比 JS 结构 pieceWeightScaleInfo(单位不一、易 10× 错)更可靠。
  function parsePackInfo(html) {
    if (typeof html !== 'string' || !html) return []
    const heads = []
    const reH = /<th\b[^>]*>([\s\S]*?)<\/th>/gi
    let m
    while ((m = reH.exec(html))) heads.push(_text(m[1]))
    if (!heads.length) return []
    const idxOf = (kw) => heads.findIndex((h) => h.indexOf(kw) >= 0)
    const ci = { color: idxOf('颜色'), spec: idxOf('规格'), L: idxOf('长'), W: idxOf('宽'), H: idxOf('高'), wt: idxOf('重量') }
    const rows = []
    const reTr = /<tr\b[^>]*>([\s\S]*?)<\/tr>/gi
    let tr
    while ((tr = reTr.exec(html))) {
      const cells = []
      const reTd = /<td\b[^>]*>([\s\S]*?)<\/td>/gi
      let td
      while ((td = reTd.exec(tr[1]))) cells.push(_text(td[1]))
      if (!cells.length) continue   // 表头行(只有 th)跳过
      const num = (i) => { const v = parseFloat(cells[i]); return isFinite(v) ? v : null }
      rows.push({
        color: ci.color >= 0 ? (cells[ci.color] || '') : '',
        spec: ci.spec >= 0 ? (cells[ci.spec] || '') : '',
        length_cm: ci.L >= 0 ? num(ci.L) : null,
        width_cm: ci.W >= 0 ? num(ci.W) : null,
        height_cm: ci.H >= 0 ? num(ci.H) : null,
        weight_g: ci.wt >= 0 ? num(ci.wt) : null
      })
    }
    return rows
  }

  // 包装表行 → 草稿尺寸字段。表里是厘米，草稿列统一存【毫米】→ cm×10；weight 克直填。
  function _packRowToDims(row) {
    const g = (v) => (typeof v === 'number' && isFinite(v) ? Math.round(v) : null)
    const mm = (v) => (typeof v === 'number' && isFinite(v) ? Math.round(v * 10) : null)
    return { weight_g: g(row.weight_g), length_mm: mm(row.length_cm), width_mm: mm(row.width_cm), height_mm: mm(row.height_cm) }
  }

  // 把变体按颜色匹配到包装表某行(颜色出现在 specAttrs 里)；匹配不到用第一行(多数变体同尺寸)。无表返回 null。
  function _packForVariant(packRows, specAttrs) {
    if (!packRows || !packRows.length) return null
    const hit = packRows.find((p) => p.color && String(specAttrs || '').indexOf(p.color) >= 0)
    return _packRowToDims(hit || packRows[0])
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

  // 区间最高价（"143.00-159.00" → 最贵那档；阶梯价小批量实付价，用户要"贵的那个"）
  function _highestFromDisplay(disp) {
    const nums = String(disp || '').match(/\d+(?:\.\d+)?/g)
    if (!nums || !nums.length) return ''
    let hi = nums[0]
    for (const n of nums) if (Number(n) > Number(hi)) hi = n
    return hi
  }

  // 全量 SKU 展开 → 变体草稿数组。packHtml = 「商品件重尺」表 outerHTML(尺寸优先源)
  function expandSkus(data, base, packHtml) {
    data = data || {}
    base = base || {}
    const skuModel = _get(data, ['Root', 'fields', 'dataJson', 'skuModel']) || {}
    const infoMap = skuModel.skuInfoMap || {}
    const skuProps = skuModel.skuProps || []
    const packInfo = _get(data, ['productPackInfo', 'fields', 'pieceWeightScale', 'pieceWeightScaleInfo']) || []
    const packRows = parsePackInfo(packHtml)   // 包装表(单位明确)优先；无则回退 pieceWeightScaleInfo
    const keys = Object.keys(infoMap)
    const baseImgs = Array.isArray(base.images) ? base.images : []

    if (!keys.length) {
      // 无 SKU：单条，价取区间最贵那档；尺寸取包装表第一行
      const price = _highestFromDisplay(_get(base, ['source_raw', 'price_display']))
      const dims = packRows.length ? _packRowToDims(packRows[0])
        : { weight_g: null, length_mm: null, width_mm: null, height_mm: null }
      return [Object.assign({}, base, { price: price }, dims)]
    }

    // 多数 1688 商品 SKU 不带单价 → 用整品区间最贵那档兜底
    const offerHigh = _highestFromDisplay(_get(base, ['source_raw', 'price_display']))
    return keys.map((k) => {
      const sku = infoMap[k] || {}
      const dims = _packForVariant(packRows, sku.specAttrs || k) || _packBySkuId(packInfo, sku.skuId)
      const vimg = _variantImage(skuProps, sku.specAttrs || k)
      const images = []
      const push = (u) => { if (u && images.indexOf(u) < 0) images.push(u) }
      push(vimg)
      baseImgs.forEach(push)
      return Object.assign({}, base, {
        price: sku.price != null ? String(sku.price) : offerHigh,
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

  // 多 SKU 各建独立草稿：拼 #sku=<skuId> 让 source_url 唯一（后端按 source_url 去重，否则 N 变体收敛成 1 张）
  function variantSourceUrl(baseUrl, skuId) {
    const b = String(baseUrl || '')
    return skuId ? (b + '#sku=' + skuId) : b
  }

  return { extractOfferId, parseDetailImages, buildRichContent, parseAttributes, parsePackInfo, parse1688Base, expandSkus, variantSourceUrl }
})
