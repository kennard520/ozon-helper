;(function () {
  const PANEL_ID = 'ozon-helper-panel'
  const site = (typeof OzonHelperSite !== 'undefined') ? OzonHelperSite.detectSite(location.hostname) : null
  if (!site) return

  const SITE_LABEL = { ozon: 'Ozon', '1688': '1688', pdd: '拼多多', wb: 'Wildberries' }
  let collapsed = false
  let lastBody = '<div class="ohp-empty">正在识别当前页面...</div>'
  let generation = 0
  let variantStop = false

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
  }

  function ensurePanel() {
    let el = document.getElementById(PANEL_ID)
    if (!el && document.body) {
      el = document.createElement('div')
      el.id = PANEL_ID
      el.addEventListener('click', onPanelClick)
      document.body.appendChild(el)
    }
    return el
  }

  function render() {
    const el = ensurePanel()
    if (!el) return
    el.className = collapsed ? 'ohp-collapsed' : ''
    el.innerHTML =
      `<div class="ohp-head">` +
        `<span class="ohp-title"><b>上品助手</b><em>${SITE_LABEL[site] || '商品页'}</em></span>` +
        `<button class="ohp-toggle" type="button" data-act="toggle">${collapsed ? '展开' : '收起'}</button>` +
      `</div>` +
      (collapsed ? '' : `<div class="ohp-body">${lastBody}</div>`)
  }

  function setBody(html) {
    lastBody = html
    render()
  }

  function statusHtml(text, tone) {
    return `<div class="ohp-status ${tone || ''}">${escapeHtml(text)}</div>`
  }

  function actionHtml(options) {
    const extra = options && options.variants
      ? '<button class="ohp-variants" type="button">采集全部变体</button>'
      : ''
    return '<button class="ohp-edit" type="button">采集到管理端草稿</button>' + extra
  }

  function onPanelClick(e) {
    const t = e.target
    if (!t || !t.classList) return
    if (t.dataset && t.dataset.act === 'toggle') {
      e.preventDefault()
      collapsed = !collapsed
      render()
      return
    }
    if (t.classList.contains('ohp-edit') && !t.disabled) {
      e.preventDefault()
      onEditCurrent()
      return
    }
    if (t.classList.contains('ohp-variants')) {
      e.preventDefault()
      if (t.classList.contains('ohp-stopbtn')) variantStop = true
      else onCollectVariants()
    }
  }

  function setEditButton(text, disabled) {
    const panel = document.getElementById(PANEL_ID)
    const btn = panel && panel.querySelector('.ohp-edit')
    if (btn) {
      btn.textContent = text
      btn.disabled = !!disabled
    }
  }

  function onEditCurrent() {
    if (typeof OzonHelperCollect === 'undefined') return
    if (site === 'wb') {
      const nm = (typeof OzonHelperWb !== 'undefined') ? OzonHelperWb.nmFromUrl(location.href) : null
      if (!nm) {
        setBody(statusHtml('当前不是 WB 商品页', 'warn'))
        return
      }
      OzonHelperCollect.collectWbAndEdit(nm, location.href, setEditButton)
      return
    }
    if (site !== 'ozon') {
      setBody(unsupportedBody())
      return
    }
    const pid = OzonHelperParse.extractProductId(location.href)
    if (!pid) {
      setBody(statusHtml('打开 Ozon 商品详情页后可采集', 'warn'))
      return
    }
    OzonHelperCollect.collectAndEdit(pid, location.href, setEditButton)
  }

  function unsupportedBody() {
    return (
      '<div class="ohp-empty"><b>当前站点采集接入中</b><br>' +
      '1688 / 拼多多会在页面浮层完成采集，管理端只负责编辑、AI 生成和发布。</div>' +
      '<button class="ohp-btn" type="button" disabled>采集入口接入中</button>'
    )
  }

  function buildOtherOffersUrl(pid) {
    const inner = `/modal/otherOffersFromSellers?product_id=${pid}&sort=price&page_changed=true`
    return `https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=${encodeURIComponent(inner)}`
  }

  function productJsonUrl(url, pid) {
    let path = '/product/' + pid + '/'
    try {
      const p = new URL(url, 'https://www.ozon.ru').pathname
      if (p && p.indexOf('/product/') === 0) path = p
    } catch (e) {
      /* ignore */
    }
    return 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=' + encodeURIComponent(path)
  }

  function fmtNum(n) {
    if (n == null) return '-'
    if (n >= 10000) return (n / 10000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, '') + '万'
    return String(n)
  }

  function sellersPopupHtml(summary) {
    if (!summary || !summary.followCount) return '<div class="ohp-empty">暂无跟卖卖家</div>'
    return (summary.sellers || []).slice(0, 20).map((s) => {
      const safeLink = /^https?:\/\//i.test(s.link || '') ? s.link : '#'
      const price = s.price != null ? `<span class="ohp-price">${escapeHtml(s.price)} ₽</span>` : '<span class="ohp-price">-</span>'
      return (
        `<a class="ohp-row" href="${escapeHtml(safeLink)}" target="_blank" rel="noreferrer">` +
          `<div class="ohp-line1"><span class="ohp-name">${escapeHtml(s.name || '卖家')}</span>${price}</div>` +
          (s.deliver ? `<div class="ohp-deliver">${escapeHtml(s.deliver)}</div>` : '') +
        `</a>`
      )
    }).join('')
  }

  function metricRow(label, value, popupHtml) {
    const pop = popupHtml ? `<div class="ohp-pop">${popupHtml}</div>` : ''
    const cls = popupHtml ? 'ohp-metric ohp-has-pop' : 'ohp-metric'
    return `<div class="${cls}"><span class="ohp-mlabel">${label}</span><span class="ohp-mval">${value}</span>${pop}</div>`
  }

  function metricsHtml(m) {
    if (!m) return statusHtml('跟卖数据暂未获取到', 'warn')
    return [
      metricRow('跟卖数', m.followCount != null ? `<b>${m.followCount}</b> 家` : '-', sellersPopupHtml(m)),
      metricRow('价格区间', m.priceMin != null ? `${m.priceMin} - ${m.priceMax} ₽` : '-'),
      metricRow('估算累计销量', m.estimate ? `<b>${fmtNum(m.estimate.salesLow)} - ${fmtNum(m.estimate.salesHigh)}</b> 件` : '-'),
      metricRow('评分', m.rating != null ? `★ ${m.rating}` : '-'),
      metricRow('评论数', m.reviews != null ? String(m.reviews) : '-')
    ].join('')
  }

  async function runOzonFollow() {
    const gen = ++generation
    const pid = OzonHelperParse.extractProductId(location.href)
    if (!pid) {
      setBody(statusHtml('打开 Ozon 商品详情页后可查看跟卖和采集', 'warn'))
      return
    }
    setBody(actionHtml({ variants: true }) + statusHtml('正在读取跟卖和评论数据...', 'loading'))
    try {
      const [resp, pResp] = await Promise.all([
        fetch(buildOtherOffersUrl(pid), { credentials: 'include' }),
        fetch(productJsonUrl(location.href, pid), { credentials: 'include' }).catch(() => null)
      ])
      if (gen !== generation) return
      let rating = null
      let reviews = null
      if (pResp && pResp.ok) {
        try {
          const pJson = await pResp.json()
          reviews = OzonHelperParse.parseReviewCount(pJson)
          rating = OzonHelperParse.parseRating(pJson)
        } catch (e) {
          /* ignore */
        }
      }
      const summary = resp.ok ? OzonHelperParse.summarizeOtherOffers(await resp.json()) : null
      if (gen !== generation) return
      setBody(actionHtml({ variants: true }) + metricsHtml({
        followCount: summary ? summary.followCount : null,
        priceMin: summary ? summary.priceMin : null,
        priceMax: summary ? summary.priceMax : null,
        sellers: summary ? summary.sellers : [],
        estimate: OzonHelperParse.estimateSales(reviews),
        rating,
        reviews
      }))
      if (summary && summary.followCount > 0 && typeof OzonHelperBridge !== 'undefined') {
        OzonHelperBridge.bgCall('snapshot', {
          product_id: pid,
          follow_count: summary.followCount,
          price_min: summary.priceMin,
          price_max: summary.priceMax,
          sellers: summary.sellers
        })
      }
    } catch (e) {
      if (gen === generation) setBody(actionHtml({ variants: true }) + statusHtml('跟卖数据暂未获取到', 'warn'))
    }
  }

  function onCollectVariants() {
    if (typeof OzonHelperCollect === 'undefined') return
    variantStop = false
    const panel = document.getElementById(PANEL_ID)
    const btn = panel && panel.querySelector('.ohp-variants')
    if (btn) {
      btn.textContent = '采集中，点击停止'
      btn.disabled = false
      btn.classList.add('ohp-stopbtn')
    }
    OzonHelperCollect.collectAllVariants(location.href, {
      getStop: () => variantStop,
      onProgress: (done, total, label) => {
        const panelEl = document.getElementById(PANEL_ID)
        let p = panelEl && panelEl.querySelector('#ohp-variant-progress')
        if (!p && panelEl) {
          p = document.createElement('div')
          p.id = 'ohp-variant-progress'
          p.className = 'ohp-vprog'
          panelEl.appendChild(p)
        }
        if (p) p.textContent = total ? `变体采集 ${done}/${total} ${label || ''}` : (label || '')
      }
    }).then((res) => {
      const panelEl = document.getElementById(PANEL_ID)
      const b2 = panelEl && panelEl.querySelector('.ohp-variants')
      if (b2) {
        b2.textContent = res.stopped ? '已停止，继续采集全部变体' : `完成 ${res.collected} 个，重新采集`
        b2.disabled = false
        b2.classList.remove('ohp-stopbtn')
      }
    })
  }

  function renderWbBody() {
    if (typeof OzonHelperWb !== 'undefined' && OzonHelperWb.isWbProductPage(location.pathname)) {
      setBody(actionHtml() + statusHtml('采集后进入管理端草稿编辑', 'ok'))
    } else {
      setBody(statusHtml('打开 WB 商品页后可采集到管理端草稿', 'warn'))
    }
  }

  function update() {
    if (site === 'ozon') runOzonFollow()
    else if (site === 'wb') renderWbBody()
    else setBody(unsupportedBody())
  }

  render()
  let lastUrl = ''
  function tick() {
    if (!document.getElementById(PANEL_ID)) render()
    if (location.href !== lastUrl) {
      lastUrl = location.href
      update()
    }
  }
  const tid = setInterval(tick, 1500)
  window.addEventListener('pagehide', () => clearInterval(tid))
  tick()
})()
