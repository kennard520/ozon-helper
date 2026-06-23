// 就地采 → 建草稿 → 开编辑器（content script 全局 OzonHelperCollect；依赖 OzonHelperProduct/OzonHelperBridge）
;(function (root) {
  // 用商品真实 slug 路径拉 page-json（纯 id 路径 Ozon 会 301，page-json 拿不到 widgetStates）
  function _productPath(productUrl, pid) {
    try {
      const p = new URL(productUrl, 'https://www.ozon.ru').pathname
      if (p && p.indexOf('/product/') === 0) return p
    } catch (e) {
      /* ignore */
    }
    return '/product/' + pid + '/'
  }

  // 当前页币种：俄区站(Ozon/WB)=RUB 要换算，国内站(1688/拼多多)=CNY 不换算。
  function _pageCurrency() {
    if (typeof OzonHelperSite === 'undefined') return 'RUB' // 兜底按 Ozon(本插件主场)
    return OzonHelperSite.currencyOf(OzonHelperSite.detectSite(location.hostname)) || 'RUB'
  }

  // 拿后端汇率(rub_cny)：用于把卢布价换算成人民币再发后端。
  // 返回 {ok, rate}；ok=false=后端不可达；ok=true&&rate=null=后端在但没配汇率。
  async function _fetchRate() {
    if (typeof OzonHelperBridge === 'undefined') return { ok: false }
    const r = await OzonHelperBridge.bgCall('ping')
    if (!r || !r.ok || !r.data) return { ok: false }
    const v = Number(r.data.rub_cny)
    return { ok: true, rate: v > 0 ? v : null }
  }

  // WB 就地取价：与页面同源(wildberries.ru)→card.wb.ru 允许 CORS，公开无需登录。
  // 逐个候选试，第一个出 product 价的即命中。返回 {price_rub, old_rub, rating, feedbacks} 或 null。
  async function _fetchWbPrice(nm) {
    if (typeof OzonHelperWb === 'undefined') return null
    for (const u of OzonHelperWb.priceCandidateUrls(nm)) {
      try {
        const r = await fetch(u)
        if (!r.ok) continue
        const parsed = OzonHelperWb.parseWbPrice(await r.json())
        if (parsed) return parsed
      } catch (e) { /* 试下一个候选 */ }
    }
    return null
  }

  // 媒体重托管：把草稿里所有图/视频下载后多线程直传 OSS（预签名，国内快），
  // 换成 OSS 公网直链再推后端。best-effort：传失败保留原链接，不阻断采集。onStatus 可选。
  async function _rehostMedia(data, onStatus) {
    if (typeof OzonHelperMedia === 'undefined' || typeof OzonHelperBridge === 'undefined') return data
    const urls = OzonHelperMedia.collectMediaUrls(data)
    if (!urls.length) return data
    if (onStatus) onStatus('上传图片(' + urls.length + ')…', true)
    const r = await OzonHelperBridge.bgCall('uploadMediaOss', { urls })
    if (r && r.ok && r.data && r.data.map) {
      if (r.data.error && onStatus) {
        onStatus(/401/.test(r.data.error) ? '请先在插件登录再采集' : ('图片上传失败:' + r.data.error + '，沿用原链接'), false)
      } else if ((r.data.failed || []).length && onStatus) {
        onStatus((r.data.failed.length) + ' 张图未上传,沿用原链接', false)
      }
      return OzonHelperMedia.applyMediaMap(data, r.data.map)
    }
    return data
  }

  // 可复用的「取一个 URL → 建一草稿」核心函数
  // extra: 附加字段合并进 data（如 variant_group）；rate: 卢布→人民币汇率(>0 时换算)
  // onStatus: 可选状态回调（媒体上传进度）
  // 返回 {ok, data}；ok=false 时 data 可能是 null
  async function _collectOne(url, pid, extra, rate, onStatus) {
    if (typeof OzonHelperProduct === 'undefined' || typeof OzonHelperBridge === 'undefined') {
      return { ok: false, data: null }
    }
    const path = _productPath(url, pid)
    const base = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url='
    const get = async (pth) => {
      const r = await fetch(base + encodeURIComponent(pth), { credentials: 'include' })
      return r.ok ? r.json() : null
    }
    let page1 = null
    let page2 = null
    try {
      ;[page1, page2] = await Promise.all([
        get(path).catch(() => null),
        get(path + '?layout_page_index=2&layout_container=pdpPage2column').catch(() => null)
      ])
    } catch (e) {
      /* ignore */
    }
    if (!page1) return { ok: false, data: null }
    let data = OzonHelperProduct.buildCollectData(OzonHelperProduct.parseOzonProduct(page1, page2))
    if (extra) Object.assign(data, extra)
    if (rate > 0) data = OzonHelperProduct.applyRubToCny(data, rate) // 卢布→人民币，后端统一 CNY
    // 计划三：不再同步传媒体——直接推原始链接(采集秒回)，媒体由 background 后台异步传 OSS
    const r = await OzonHelperBridge.bgCall('collectParsed', { url, data })
    if (r && r.ok) OzonHelperBridge.bgCall('rehostPending')   // 踢后台补传，不等结果
    return { ok: !!(r && r.ok), data: r && r.data }
  }

  async function collectAndEdit(pid, url, onStatus) {
    if (typeof OzonHelperProduct === 'undefined' || typeof OzonHelperBridge === 'undefined') return
    if (onStatus) onStatus('采集中…', true)
    let rate = 0
    if (_pageCurrency() === 'RUB') { // 卢布站才需汇率换算；人民币站(1688/拼多多)直接发
      const rt = await _fetchRate()
      if (!rt.ok) { if (onStatus) onStatus('连不上后端服务器，请检查网络或联系管理员', false); return }
      if (!rt.rate) { if (onStatus) onStatus('未配置汇率:先在 webui 设置填 RUB/CNY', false); return }
      rate = rt.rate
    }
    const result = await _collectOne(url, pid, null, rate, onStatus)
    if (result.ok) {
      if (onStatus) onStatus('已采集 ✓', true)
      const created = result.data && result.data.created
      const draftId = Array.isArray(created) && created[0] ? created[0].id : null
      // 开了「采集后自动发布」就不弹 webui 编辑器（采集即发到 Ozon，不需要 webui）
      if (!(result.data && result.data.auto_publish)) OzonHelperBridge.bgCall('openEditor', { draftId })
    } else if (onStatus) {
      onStatus('连不上后端服务器，请检查网络或联系管理员', false)
    }
  }

  // WB：全插件采集——card.json(经 bg 取,客户端解析) + 就地取价 + 媒体传 OSS → collect-parsed
  async function collectWbAndEdit(nm, url, onStatus) {
    if (typeof OzonHelperWb === 'undefined' || typeof OzonHelperBridge === 'undefined') return
    if (onStatus) onStatus('采集中…', true)
    // WB 是卢布站 → 必须先有汇率才能把价换成人民币(与 Ozon 一致，绝不发原始卢布)
    const rt = await _fetchRate()
    if (!rt.ok) { if (onStatus) onStatus('连不上后端服务器，请检查网络或联系管理员', false); return }
    if (!rt.rate) { if (onStatus) onStatus('未配置汇率:先在 webui 设置填 RUB/CNY', false); return }
    // 1) card.json → 解析正文(标题/描述/属性/图/克重尺寸)
    const cr = await OzonHelperBridge.bgCall('wbResolveCard', { nm })
    if (!cr || !cr.ok || !cr.data || !cr.data.card) {
      if (onStatus) onStatus('WB 商品数据采不到(card.json)', false)
      return
    }
    let data = OzonHelperWb.parseCard(cr.data.card, cr.data.host, nm)
    // 2) 就地取价(卢布→人民币)
    const wp = await _fetchWbPrice(nm)
    if (wp) {
      const cny = OzonHelperProduct.applyRubToCny({ price: wp.price_rub, old_price: wp.old_rub }, rt.rate)
      data.price = cny.price
      if (cny.old_price !== '' && cny.old_price != null) data.old_price = cny.old_price
      if (wp.rating != null) data.source_raw.rating = wp.rating
      if (wp.feedbacks != null) data.source_raw.feedbacks = wp.feedbacks
    }
    // 3) 推送（计划三：不再同步传媒体，推原始链接秒回，媒体由 background 后台异步传 OSS）
    const r = await OzonHelperBridge.bgCall('collectParsed', { url, data })
    if (r && r.ok) {
      OzonHelperBridge.bgCall('rehostPending')   // 踢后台补传，不等结果
      if (onStatus) onStatus(wp ? '已采集 ✓' : '已采集(价格没取到,请手填)', true)
      const created = r.data && r.data.created
      const draftId = Array.isArray(created) && created[0] ? created[0].id : null
      // 开了「采集后自动发布」就不弹 webui 编辑器（采集即发到 Ozon，不需要 webui）
      if (!(r.data && r.data.auto_publish)) OzonHelperBridge.bgCall('openEditor', { draftId })
    } else if (onStatus) {
      onStatus('采集失败:' + ((r && r.error) || '连不上后端服务器'), false)
    }
  }

  // content script(隔离世界)读不到页面 window.context/offer_details；经 content/main-1688.js(主世界)
  // 用 window.postMessage 桥接取回裁剪后的页面数据(slim)+详情HTML。超时/失败回退 {data:null}。
  function _read1688PageData() {
    return new Promise(function (resolve) {
      if (typeof window === 'undefined') { resolve({ data: null, detailHtml: '' }); return }
      const reqId = 'oh' + Date.now() + '_' + Math.random()
      let settled = false
      function onMsg(e) {
        if (e.source !== window) return
        const m = e.data
        if (!m || m.__oh1688 !== 'res' || m.reqId !== reqId) return
        window.removeEventListener('message', onMsg)
        settled = true
        resolve({ data: m.data || null, detailHtml: m.detailHtml || '' })
      }
      window.addEventListener('message', onMsg)
      window.postMessage({ __oh1688: 'req', reqId: reqId }, '*')
      setTimeout(function () {
        if (!settled) { window.removeEventListener('message', onMsg); resolve({ data: null, detailHtml: '' }) }
      }, 2500)
    })
  }

  // 1688：全插件采集——经主世界桥接读页面数据(window.context/offer_details) + DOM 属性 → 全量 SKU 各建一草稿。
  // 1688 是人民币站，不换汇；图/视频/富文本图走后台异步传 OSS。
  async function collect1688AndEdit(url, onStatus) {
    if (typeof OzonHelperParse1688 === 'undefined' || typeof OzonHelperBridge === 'undefined') return
    if (onStatus) onStatus('采集中…', true)
    const page = await _read1688PageData()
    const data = page.data
    if (!data) { if (onStatus) onStatus('请等商品详情加载完再采集（未读到页面数据）', false); return }
    const detailHtml = page.detailHtml || ''
    const attrEl = (typeof document !== 'undefined') ? document.querySelector('.module-od-product-attributes') : null
    const attrHtml = attrEl ? attrEl.outerHTML : ''
    // 「商品件重尺」表(长宽高 cm + 重量 g)——Ozon 必填，尺寸优先源
    const packEl = (typeof document !== 'undefined') ? document.querySelector('.module-od-product-pack-info') : null
    const packHtml = packEl ? packEl.outerHTML : ''
    const base = OzonHelperParse1688.parse1688Base(data, detailHtml, attrHtml, url)
    if (!base.title) { if (onStatus) onStatus('未识别到 1688 商品（标题为空）', false); return }
    const group = OzonHelperParse1688.extractOfferId(url)
    const variants = OzonHelperParse1688.expandSkus(data, base, packHtml)
    let firstDraftId = null
    let autoPublish = false
    let ok = 0
    let lastErr = ''
    for (let i = 0; i < variants.length; i++) {
      if (onStatus) onStatus('采集 ' + (i + 1) + '/' + variants.length + '…', true)
      const cd = variants[i]
      if (group) cd.variant_group = group
      const skuId = cd.source_raw && cd.source_raw.sku_id
      const variantUrl = OzonHelperParse1688.variantSourceUrl(url, skuId)  // 唯一化，防后端按 source_url 去重收敛
      try {
        const r = await OzonHelperBridge.bgCall('collectParsed', { url: variantUrl, data: cd })
        if (r && r.ok) {
          ok++
          if (firstDraftId == null) {
            const created = r.data && r.data.created
            firstDraftId = Array.isArray(created) && created[0] ? created[0].id : null
            autoPublish = !!(r.data && r.data.auto_publish)
          }
        } else if (r && r.error) { lastErr = r.error }
      } catch (e) { lastErr = (e && e.message) || lastErr }
    }
    if (!ok) { if (onStatus) onStatus('采集失败:' + (lastErr || '连不上后端服务器，请检查网络或联系管理员'), false); return }
    OzonHelperBridge.bgCall('rehostPending')   // 踢后台补传图/视频到 OSS
    if (onStatus) onStatus('已采集 ' + ok + '/' + variants.length + ' ✓', true)
    if (!autoPublish) OzonHelperBridge.bgCall('openEditor', { draftId: firstDraftId })
  }

  // 串行限速爬取所有变体；每个变体 → 一个草稿(带 variant_group=主商品SKU)
  // onProgress(done,total,label); getStop()→true 则停。返回 {collected, stopped}
  async function collectAllVariants(currentUrl, opts) {
    opts = opts || {}
    const onProgress = opts.onProgress || function () {}
    const getStop = opts.getStop || function () { return false }
    const spacingMs = opts.spacingMs || 4000
    const includeUnavailable = !!opts.includeUnavailable
    // 卢布站才先拿汇率：缺则整批中止，不发卢布价进后端；人民币站直接发
    let rate = 0
    if (_pageCurrency() === 'RUB') {
      const rt = await _fetchRate()
      if (!rt.ok) { onProgress(0, 0, '连不上后端服务器'); return { collected: 0, stopped: false, noRate: true } }
      if (!rt.rate) { onProgress(0, 0, '未配置汇率(webui 设置填 RUB/CNY)'); return { collected: 0, stopped: false, noRate: true } }
      rate = rt.rate
    }
    // 拉当前页拿变体清单 + 主商品 SKU 作为分组键
    let page1 = null
    try {
      const u = 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=' + encodeURIComponent(new URL(currentUrl, 'https://www.ozon.ru').pathname)
      const r = await fetch(u, { credentials: 'include' })
      page1 = r.ok ? await r.json() : null
    } catch (e) { /* ignore */ }
    if (!page1) { onProgress(0, 0, '读取失败'); return { collected: 0, stopped: false } }
    const parsed = OzonHelperProduct.parseOzonProduct(page1)
    const group = (typeof OzonHelperParse !== 'undefined' && OzonHelperParse.extractProductId)
      ? (OzonHelperParse.extractProductId(currentUrl) || '')
      : ''
    const list = (parsed.variants || []).filter((v) => includeUnavailable || v.available)
    const total = list.length
    let collected = 0
    for (let i = 0; i < total; i++) {
      if (getStop()) return { collected, stopped: true }
      const v = list[i]
      onProgress(i, total, v.label || v.sku)
      try {
        await _collectOne(v.link, v.sku, { variant_group: group }, rate)
        collected++
      } catch (e) { /* 单个失败跳过 */ }
      if (i < total - 1) await new Promise((res) => setTimeout(res, spacingMs)) // 限速防封
    }
    onProgress(total, total, '完成')
    return { collected, stopped: false }
  }

  root.OzonHelperCollect = { collectAndEdit, collectAllVariants, collectWbAndEdit, collect1688AndEdit }
})(typeof globalThis !== 'undefined' ? globalThis : self)
