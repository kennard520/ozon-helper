// Ozon 商品页就地解析（纯函数，UMD：content script 全局 OzonHelperProduct + vitest import）
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperProduct = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function _ws(json) {
    return (json && json.widgetStates) || {}
  }
  function _state(ws, prefix) {
    const k = Object.keys(ws).find((x) => x.indexOf(prefix) === 0)
    if (!k) return null
    try {
      return typeof ws[k] === 'string' ? JSON.parse(ws[k]) : ws[k]
    } catch (e) {
      return null
    }
  }
  function _cleanPrice(s) {
    if (s == null) return ''
    const d = String(s).replace(/[^\d]/g, '')
    return d || ''
  }

  function _num(s) {
    const m = String(s == null ? '' : s).replace(',', '.').match(/[\d.]+/)
    return m ? parseFloat(m[0]) : null
  }
  function _charName(c) {
    const rs = (c && c.title && c.title.textRs) || []
    return rs.map((t) => t && t.content).join('').trim()
  }
  function _charValue(c) {
    const vs = (c && c.values) || []
    return vs.map((v) => v && v.text).join(', ').trim()
  }
  // 抽全部属性：合并 webCharacteristics(全量,page2,~45个,结构 characteristics[].short[]{name,values})
  // 与 webShortCharacteristics(高亮,page1/page2,结构 {title.textRs,values})；按名去重，跳过"Артикул"(竞品货号)。
  function _allChars(page1, page2) {
    const out = []
    const seen = new Set()
    const add = (name, value) => {
      name = String(name || '').trim()
      value = String(value || '').trim()
      if (name && value && name !== 'Артикул' && !seen.has(name)) {
        seen.add(name)
        out.push({ name, value })
      }
    }
    // 全量 webCharacteristics（page2）
    const full = _state(_ws(page2), 'webCharacteristics-')
    for (const g of (full && full.characteristics) || []) {
      for (const it of (g && (g.short || g.long)) || []) {
        if (it && it.key === 'Sku') continue
        const value = ((it && it.values) || []).map((v) => v && v.text).filter(Boolean).join(', ')
        add(it && it.name, value)
      }
    }
    // 高亮 webShortCharacteristics（page1/page2）补充
    for (const pg of [page1, page2]) {
      const sh = _state(_ws(pg), 'webShortCharacteristics-')
      for (const c of (sh && sh.characteristics) || []) add(_charName(c), _charValue(c))
    }
    return out
  }

  function _characteristics(page1, page2) {
    return _allChars(page1, page2)
  }

  // 从全部属性里找 克重(g)/长宽高(mm)；см→×10mm，кг→×1000g（全量表才有，高亮表常没有）
  function _dimsWeight(page1, page2) {
    const out = { weight_g: null, length_mm: null, width_mm: null, height_mm: null }
    for (const { name, value } of _allChars(page1, page2)) {
      const n = name.toLowerCase()
      const val = _num(value)
      if (val == null) continue
      if (/вес/.test(n) && out.weight_g == null) out.weight_g = /кг/.test(n) ? Math.round(val * 1000) : Math.round(val)
      else if (/высота/.test(n) && out.height_mm == null) out.height_mm = /мм/.test(n) ? Math.round(val) : Math.round(val * 10)
      else if (/ширина/.test(n) && out.width_mm == null) out.width_mm = /мм/.test(n) ? Math.round(val) : Math.round(val * 10)
      else if (/(длина|глубина)/.test(n) && out.length_mm == null) out.length_mm = /мм/.test(n) ? Math.round(val) : Math.round(val * 10)
    }
    return out
  }
  // 从 page2 webDescription.richAnnotationJson 抽纯文本描述
  function _stripHtml(html) {
    return String(html || '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/(p|div|li|tr)>/gi, '\n')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  }
  // 递归把 richAnnotationJson 里的所有文字捞出来，不管 Ozon 怎么嵌套
  // （兼容 {content:["..."]}、{content:"..."}、{items:[{content,type:"text"}]}、{type:"text",content} 等各种排版）
  function _collectRich(node, out) {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) {
      for (const n of node) _collectRich(n, out)
      return
    }
    if (node.type === 'text' && typeof node.content === 'string') {
      out.push(node.content)
      return
    }
    for (const k in node) {
      if (k === 'img' || k === 'imgLink' || k === 'src' || k === 'srcMobile' || k === 'trackingInfo') continue
      const v = node[k]
      if (k === 'content') {
        if (typeof v === 'string') {
          if (!/^https?:\/\//.test(v)) out.push(v)
        } else if (Array.isArray(v)) {
          for (const s of v) {
            if (typeof s === 'string') out.push(s)
            else _collectRich(s, out)
          }
        } else {
          _collectRich(v, out)
        }
      } else {
        _collectRich(v, out)
      }
    }
  }

  // 递归把富文本里的图片 URL 捞出来（详情/营销长图）
  function _collectRichImages(node, out) {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) {
      for (const n of node) _collectRichImages(n, out)
      return
    }
    if (node.img && typeof node.img === 'object') {
      const u = node.img.src || node.img.srcMobile
      if (u && typeof u === 'string' && out.indexOf(u) < 0) out.push(u)
    }
    for (const k in node) {
      if (k === 'trackingInfo' || k === 'img') continue
      _collectRichImages(node[k], out)
    }
  }

  function _descWidget(page2) {
    const ws = _ws(page2)
    for (const k of Object.keys(ws)) {
      if (k.indexOf('webDescription-') !== 0) continue
      try {
        const st = typeof ws[k] === 'string' ? JSON.parse(ws[k]) : ws[k]
        if (st && st.richAnnotationJson) return st
      } catch (e) {
        /* skip */
      }
    }
    return null
  }

  function _description(page2) {
    const ws = _ws(page2)
    for (const k of Object.keys(ws)) {
      if (k.indexOf('webDescription-') !== 0) continue
      let st
      try {
        st = typeof ws[k] === 'string' ? JSON.parse(ws[k]) : ws[k]
      } catch (e) {
        continue
      }
      if (!st) continue
      // 格式1：richAnnotationJson 结构化（各种排版，递归捞）
      if (st.richAnnotationJson) {
        const parts = []
        _collectRich(st.richAnnotationJson, parts)
        const text = parts.map((s) => String(s).trim()).filter(Boolean).join('\n').trim()
        if (text) return text
      }
      // 格式2：richAnnotation 富文本字符串（含 <br/> 等 HTML）
      if (typeof st.richAnnotation === 'string' && st.richAnnotation.trim()) {
        const text = _stripHtml(st.richAnnotation)
        if (text) return text
      }
    }
    return ''
  }

  // 富文本里的详情/营销长图
  function _detailImages(page2) {
    const st = _descWidget(page2)
    if (!st) return []
    const out = []
    _collectRichImages(st.richAnnotationJson, out)
    return out
  }

  // 原始 richAnnotationJson 对象（发布时作为 A+ Rich 内容属性复刻图文）
  function _richContentJson(page2) {
    const st = _descWidget(page2)
    return (st && st.richAnnotationJson) || null
  }

  // page2 webHashtags → 主题标签数组（badges[].text，如 "#мылоручнойработы"）；去空/trim/去重
  function _hashtags(page2) {
    const st = _state(_ws(page2), 'webHashtags-')
    const badges = (st && st.badges) || []
    const out = []
    for (const b of badges) {
      const t = ((b && b.text) || '').trim()
      if (t && out.indexOf(t) < 0) out.push(t)
    }
    return out
  }

  // 解析 webAspects → 扁平去重的变体列表（每个唯一 SKU 一条，含标签/链接/价/缩略图）
  function _variants(page1) {
    const st = _state(_ws(page1), 'webAspects-')
    const aspects = (st && st.aspects) || []
    const out = []
    const seen = {}
    for (const a of aspects) {
      const aspectName = (a && a.aspectName) || ''
      for (const v of (a && a.variants) || []) {
        const sku = v && v.sku
        if (!sku || seen[sku]) continue
        seen[sku] = true
        const raw = (v.link || '')
        const link = raw ? (/^https?:\/\//i.test(raw) ? raw : 'https://www.ozon.ru' + raw) : ''
        const d = v.data || {}
        out.push({
          sku: String(sku),
          label: d.searchableText || '',
          aspect: aspectName,
          link: link,
          price: typeof v.price === 'number' ? v.price : null,
          cover: d.coverImage || '',
          available: v.availability === 'inStock',
          active: !!v.active
        })
      }
    }
    return out
  }

  // 买家端面包屑路径（如 "Аптека/Оптика/Растворы для линз/..."），后端据此自动匹配卖家类目
  function _categoryPath(page1) {
    const ws = _ws(page1)
    const st = _state(ws, 'breadCrumbs-') || _state(ws, 'webBreadCrumbs-')
    if (!st) return ''
    const crumbs = st.breadcrumbs || st.crumbs || st.items || (Array.isArray(st) ? st : [])
    if (!Array.isArray(crumbs)) return ''
    const names = crumbs
      .map((c) => (c && (c.text || c.title || c.name || (c.textRs && c.textRs.map((t) => t && t.content).join('')))) || '')
      .map((s) => String(s).trim())
      .filter(Boolean)
    return names.join('/')
  }

  // 当前商品自己选中的各 aspect 值（颜色/尺寸），用于发布时填变体属性
  function _selectedAspects(page1) {
    const st = _state(_ws(page1), 'webAspects-')
    const aspects = (st && st.aspects) || []
    const out = []
    for (const a of aspects) {
      const active = ((a && a.variants) || []).find((v) => v && v.active)
      if (active) {
        out.push({
          aspect: (a.aspectName || ''),
          aspect_key: (a.aspectKey || ''),
          value: (active.data && active.data.searchableText) || ''
        })
      }
    }
    return out
  }

  function parseOzonProduct(page1, page2) {
    const ws = _ws(page1)
    const heading = _state(ws, 'webProductHeading-')
    const gallery = _state(ws, 'webGallery-')
    const priceW = _state(ws, 'webPrice-')
    const title = (heading && (heading.title || heading.name)) || ''
    const images = []
    const push = (u) => {
      if (u && typeof u === 'string' && images.indexOf(u) < 0) images.push(u)
    }
    if (gallery) {
      push(gallery.coverImage)
      if (Array.isArray(gallery.images)) gallery.images.forEach((im) => push(im && (im.src || im.url || im.image)))
    }
    const videos =
      gallery && Array.isArray(gallery.videos)
        ? gallery.videos.map((v) => v && (v.url || v.videoUrl || v.src)).filter(Boolean)
        : []
    const price = _cleanPrice(priceW && (priceW.cardPrice || priceW.price))
    const old_price = _cleanPrice(priceW && priceW.originalPrice)
    const dw = _dimsWeight(page1, page2)
    return {
      title, images, videos, price, old_price, video_url: videos[0] || '',
      description: _description(page2),
      detail_images: _detailImages(page2),
      rich_content_json: _richContentJson(page2),
      weight_g: dw.weight_g, length_mm: dw.length_mm, width_mm: dw.width_mm, height_mm: dw.height_mm,
      category_path: _categoryPath(page1),
      variants: _variants(page1),
      selected_aspects: _selectedAspects(page1),
      hashtags: _hashtags(page2),
      characteristics: _characteristics(page1, page2)
    }
  }

  function buildCollectData(parsed) {
    parsed = parsed || {}
    return {
      title: parsed.title || '',
      price: parsed.price || '',
      old_price: parsed.old_price || '',
      images: parsed.images || [],
      detail_images: parsed.detail_images || [],
      rich_content_json: parsed.rich_content_json || null,
      video_url: parsed.video_url || '',
      description: parsed.description || '',
      weight_g: parsed.weight_g != null ? parsed.weight_g : null,
      length_mm: parsed.length_mm != null ? parsed.length_mm : null,
      width_mm: parsed.width_mm != null ? parsed.width_mm : null,
      height_mm: parsed.height_mm != null ? parsed.height_mm : null,
      category_path: parsed.category_path || '',
      variants: parsed.variants || [],
      selected_aspects: parsed.selected_aspects || [],
      hashtags: parsed.hashtags || [],
      // 采集的全部属性走 attributes(名值对)；后端进 draft.attributes，collected_chars 读它喂 auto-map/AI，
      // 发布时 to_ozon_import_item 只发 {id,values}、名值对自动丢弃（不会误发给 Ozon）。
      attributes: parsed.characteristics || []
    }
  }

  // 卢布→人民币：Ozon 公开页价是卢布(₽)，但后端/上架统一按人民币(CNY)处理。
  // 采集后、发后端前在插件侧换算：CNY = RUB × rate（rate=rub_cny，与 publish 路径
  // price_RUB = price_CNY / rub_cny 互逆，保持一致）。rate 无效则原样返回，绝不静默写错价。
  function applyRubToCny(data, rate) {
    const r = Number(rate)
    if (!data || !(r > 0)) return data
    const conv = (v) => {
      const n = _num(v)
      return n == null ? v : Math.round(n * r * 100) / 100
    }
    const out = Object.assign({}, data)
    if (out.price !== '' && out.price != null) out.price = conv(out.price)
    if (out.old_price !== '' && out.old_price != null) out.old_price = conv(out.old_price)
    if (Array.isArray(out.variants)) {
      out.variants = out.variants.map((v) =>
        v && typeof v.price === 'number' ? Object.assign({}, v, { price: conv(v.price) }) : v
      )
    }
    return out
  }

  return { parseOzonProduct, buildCollectData, applyRubToCny }
})
