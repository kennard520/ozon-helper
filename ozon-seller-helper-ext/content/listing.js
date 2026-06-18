;(function () {
  if (typeof OzonHelperSite === 'undefined' || OzonHelperSite.detectSite(location.hostname) !== 'ozon') return

  const MARK = 'data-ozon-helper-lcard'
  const cache = new Map() // pid -> summary
  const queue = []
  let active = 0
  const MAX_CONCURRENT = 2
  const SPACING_MS = 500
  let lastStart = 0

  function isDetailPage() {
    return /\/product\//.test(location.pathname)
  }
  function pidOf(href) {
    return OzonHelperParse.extractProductId(href || '')
  }

  // 与 class 无关地定位商品卡：从链接向上走，直到再往上会并入"别的商品"
  function findTile(anchor, pid) {
    let el = anchor
    while (el.parentElement && el.parentElement !== document.body) {
      const parent = el.parentElement
      const hasOther = Array.from(parent.querySelectorAll('a[href*="/product/"]')).some((a) => {
        const p = pidOf(a.getAttribute('href') || '')
        return p && p !== pid
      })
      if (hasOther) break
      el = parent
    }
    return el
  }

  function renderCard(card, state) {
    // 仅设 innerHTML；点击用卡片级事件委托（见 ensureCards），避免每次重渲染重复绑监听
    card.innerHTML = OzonHelperListing.cardHtml(state)
  }

  function onEdit(card) {
    if (typeof OzonHelperCollect === 'undefined') return
    const url = card.dataset.url
    const pid = card.dataset.pid
    OzonHelperCollect.collectAndEdit(pid, url, (text, disabled) => {
      const btn = card.querySelector('.ohl-edit')
      if (btn) {
        btn.textContent = text
        btn.disabled = !!disabled
      }
    })
  }

  function ensureCards() {
    if (isDetailPage()) return
    const seen = new Set()
    document.querySelectorAll('a[href*="/product/"]').forEach((a) => {
      const pid = pidOf(a.getAttribute('href') || '')
      if (!pid || seen.has(pid)) return
      seen.add(pid)
      const tile = findTile(a, pid)
      if (!tile || tile.querySelector('[' + MARK + ']')) return
      // 跳过过窄的容器(缩略图/推荐位小链接)：否则卡片被挤成竖排单字，丑且无用
      if (tile.offsetWidth && tile.offsetWidth < 120) return
      let url
      try {
        url = new URL(a.getAttribute('href'), location.origin).href
      } catch (e) {
        url = a.href
      }
      const card = document.createElement('div')
      card.setAttribute(MARK, pid)
      card.className = 'ozon-helper-lcard'
      card.dataset.pid = pid
      card.dataset.url = url
      card.addEventListener('click', (e) => {
        if (e.target.classList.contains('ohl-edit') && !e.target.disabled) {
          e.preventDefault()
          e.stopPropagation()
          onEdit(card)
        }
      })
      renderCard(card, { loading: true })
      tile.appendChild(card)
      observer.observe(card)
    })
  }

  function enqueue(card) {
    queue.push(card)
    pump()
  }
  function pump() {
    if (active >= MAX_CONCURRENT || !queue.length) return
    const wait = Math.max(0, SPACING_MS - (Date.now() - lastStart))
    const card = queue.shift()
    active++
    setTimeout(() => {
      lastStart = Date.now()
      fetchFollow(card).finally(() => {
        active--
        pump()
      })
    }, wait)
  }

  function productJsonUrl(url, pid) {
    let path = '/product/' + pid + '/'
    try {
      const p = new URL(url || '', 'https://www.ozon.ru').pathname
      if (p && p.indexOf('/product/') === 0) path = p
    } catch (e) {
      /* ignore */
    }
    return 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=' + encodeURIComponent(path)
  }

  async function fetchFollow(card) {
    const pid = card.dataset.pid
    if (cache.has(pid)) {
      renderCard(card, cache.get(pid))
      return
    }
    try {
      const inner = `/modal/otherOffersFromSellers?product_id=${pid}&sort=price&page_changed=true`
      const u = `https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=${encodeURIComponent(inner)}`
      // 并行：跟卖弹窗 + 商品页(取评论数算估算销量)
      const [resp, pResp] = await Promise.all([
        fetch(u, { credentials: 'include' }),
        fetch(productJsonUrl(card.dataset.url, pid), { credentials: 'include' }).catch(() => null)
      ])
      if (!resp.ok) {
        renderCard(card, { error: true })
        return
      }
      let estimate = null
      let rating = null
      try {
        if (pResp && pResp.ok) {
          const pJson = await pResp.json()
          estimate = OzonHelperParse.estimateSales(OzonHelperParse.parseReviewCount(pJson))
          rating = OzonHelperParse.parseRating(pJson)
        }
      } catch (e) { /* 估算失败不影响跟卖 */ }
      const json = await resp.json()
      const summary = OzonHelperParse.summarizeOtherOffers(json)
      cache.set(pid, { summary, estimate, rating })
      renderCard(card, { summary, estimate, rating })
      if (summary.followCount > 0 && typeof OzonHelperBridge !== 'undefined') {
        OzonHelperBridge.bgCall('snapshot', {
          product_id: pid,
          follow_count: summary.followCount,
          price_min: summary.priceMin,
          price_max: summary.priceMax,
          sellers: summary.sellers
        })
      }
    } catch (e) {
      renderCard(card, { error: true })
    }
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          observer.unobserve(en.target)
          enqueue(en.target)
        }
      })
    },
    { rootMargin: '120px' }
  )

  // Ozon 列表是无限滚动/SPA，DOM 变化时补卡（节流）
  let scheduled = false
  function schedule() {
    if (scheduled) return
    scheduled = true
    setTimeout(() => {
      scheduled = false
      ensureCards()
    }, 800)
  }
  try {
    new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true })
  } catch (e) {
    /* body 未就绪时忽略 */
  }
  ensureCards()
})()
