;(function (root) {
  let panel = null
  let currentNm = null
  let bootTimer = null

  function isProductPage() {
    return Boolean(root.WbMediaCard && root.WbMediaCard.nmFromUrl(location.href))
  }

  function send(message) {
    if (!root.chrome || !chrome.runtime || typeof chrome.runtime.sendMessage !== 'function') {
      return Promise.resolve({ ok: false, error: 'runtime unavailable' })
    }
    return chrome.runtime.sendMessage(message)
  }

  function resourceUrls() {
    return performance.getEntriesByType('resource')
      .map((entry) => entry.name)
      .filter((url) => /(?:card\.json|\/mp4\/)/i.test(url) && /(?:wbbasket|geobasket|\.wb\.ru)/i.test(url))
      .slice(-100)
  }

  function cardUrl() {
    return WbMediaCard.cardJsonUrlFromEntries(resourceUrls(), currentNm) || ''
  }

  function renderIfCurrent(state) {
    if (panel && state && state.nm === currentNm) panel.render(state)
  }

  function destroyPanel() {
    if (panel) panel.destroy()
    panel = null
    currentNm = null
  }

  function bootstrap() {
    if (!root.WbMediaCard || !root.WbMediaView || !isProductPage()) {
      destroyPanel()
      return
    }

    const nm = WbMediaCard.nmFromUrl(location.href)
    if (!nm) {
      destroyPanel()
      return
    }
    if (panel && currentNm === nm) return
    destroyPanel()
    if (document.getElementById('wb-media-downloader')) return

    currentNm = nm
    panel = WbMediaView.createPanel(document, {
      startMain: () => send({ type: 'START_JOB', nm, cardUrl: cardUrl(), resourceUrls: resourceUrls(), onlyMain: true })
        .then((response) => renderIfCurrent(response && response.state)),
      startAll: () => send({ type: 'START_JOB', nm, cardUrl: cardUrl(), resourceUrls: resourceUrls(), onlyMain: false })
        .then((response) => renderIfCurrent(response && response.state)),
      stop: () => send({ type: 'STOP_JOB' }).then((response) => renderIfCurrent(response && response.state)),
      retry: () => send({ type: 'RETRY_FAILED' }).then((response) => renderIfCurrent(response && response.state)),
      open: () => send({ type: 'OPEN_DOWNLOAD' })
    })

    send({ type: 'GET_JOB_STATE' }).then((response) => {
      const state = response && response.state
      if (state && state.nm === nm) renderIfCurrent(state)
    })
  }

  function scheduleBootstrap() {
    if (bootTimer) clearTimeout(bootTimer)
    bootTimer = setTimeout(() => {
      bootTimer = null
      bootstrap()
    }, 0)
  }

  if (root.chrome && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((message) => {
      if (message && message.type === 'JOB_STATE') renderIfCurrent(message.state)
    })
  }

  ;['pushState', 'replaceState'].forEach((name) => {
    const original = history[name]
    if (typeof original !== 'function' || original.__wbMediaDownloaderPatched) return
    const patched = function (...args) {
      const result = original.apply(this, args)
      scheduleBootstrap()
      return result
    }
    patched.__wbMediaDownloaderPatched = true
    history[name] = patched
  })
  addEventListener('popstate', scheduleBootstrap)

  bootstrap()
})(typeof globalThis !== 'undefined' ? globalThis : self)
