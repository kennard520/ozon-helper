importScripts(
  'common/wb-card.js',
  'common/media-resolver.js',
  'common/file-path.js',
  'common/download-plan.js',
  'common/download-queue.js',
  'common/job-controller.js'
)

const MESSAGE_TYPES = new Set(['START_JOB', 'STOP_JOB', 'RETRY_FAILED', 'GET_JOB_STATE', 'OPEN_DOWNLOAD'])
const SESSION_KEY = 'wbMediaJob'
const ACTIVE_PHASES = new Set(['scanning', 'resolving', 'downloading'])
const NETWORK_TIMEOUT_MS = 8000
let restorePromise = null
let lastCompletedDownloadId = null

function withTimeout(task, timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs || NETWORK_TIMEOUT_MS)
  return Promise.resolve()
    .then(() => task(controller.signal))
    .finally(() => clearTimeout(timer))
}

function nmFromCardPath(url) {
  try {
    const match = new URL(url).pathname.match(/\/(\d+)\/info\/ru\/card\.json$/)
    return match ? match[1] : ''
  } catch (_) {
    return ''
  }
}

function isAllowedRichJsonUrl(raw) {
  try {
    const url = new URL(raw)
    return url.protocol === 'https:' &&
      /\.(?:wbbasket|geobasket|wb)\.ru$/i.test(url.hostname) &&
      /\/\d+\/info\/ru\/rich_v1\.json$/i.test(url.pathname)
  } catch (_) {
    return false
  }
}

async function fetchJson(url) {
  const nm = nmFromCardPath(url)
  if (!(WbMediaCard.isAllowedCardUrl(url, nm) || isAllowedRichJsonUrl(url))) {
    throw new Error('URL not allowed')
  }
  return withTimeout(async (signal) => {
    const response = await fetch(url, { signal })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    return response.json()
  })
}

async function probe(url) {
  if (!isAllowedProbeUrl(url)) throw new Error('URL not allowed')
  return withTimeout(async (signal) => {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Range: 'bytes=0-0' },
      signal
    })
    if (response.body && typeof response.body.cancel === 'function') {
      response.body.cancel().catch(() => {})
    }
    return response.status === 200 || response.status === 206
  }, NETWORK_TIMEOUT_MS)
}

function isAllowedProbeUrl(raw) {
  try {
    const url = new URL(raw)
    return url.protocol === 'https:' &&
      /\.(?:wbbasket|geobasket|wb)\.ru$/i.test(url.hostname) &&
      /\/\d+\//.test(url.pathname) &&
      /\.mp4$/i.test(url.pathname)
  } catch (_) {
    return false
  }
}

function waitForDownload(downloadId) {
  return new Promise((resolve, reject) => {
    const listener = (delta) => {
      if (delta.id !== downloadId || !delta.state) return
      if (delta.state.current === 'complete') {
        lastCompletedDownloadId = downloadId
        chrome.downloads.onChanged.removeListener(listener)
        resolve()
      } else if (delta.state.current === 'interrupted') {
        chrome.downloads.onChanged.removeListener(listener)
        reject(new Error((delta.error && delta.error.current) || 'download interrupted'))
      }
    }
    chrome.downloads.onChanged.addListener(listener)
  })
}

async function convertToJpeg(url, signal) {
  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const blob = await response.blob()
  if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError')
  const bitmap = await createImageBitmap(blob)
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, bitmap.width, bitmap.height)
  ctx.drawImage(bitmap, 0, 0)
  bitmap.close()
  const jpegBlob = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.92 })
  const buffer = await jpegBlob.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192))
  }
  return `data:image/jpeg;base64,${btoa(binary)}`
}

async function startDownload(item, options) {
  const signal = options && options.signal
  if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError')
  let url = item.url
  if (item.convertTo === 'jpg' && /\.webp(?:[?#]|$)/i.test(item.url)) {
    try {
      url = await convertToJpeg(item.url, signal)
    } catch (err) {
      if (err && err.name === 'AbortError') throw err
      // 转换失败则直接下载原始 webp
      url = item.url
    }
  }
  if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError')
  const downloadId = await chrome.downloads.download({
    url,
    filename: item.filename,
    saveAs: false,
    conflictAction: 'uniquify'
  })
  return { handle: downloadId, completion: waitForDownload(downloadId) }
}

async function cancelDownload(handle) {
  if (handle == null) return
  await chrome.downloads.cancel(Number(handle))
}

async function reconcileDownload(handle) {
  const found = await chrome.downloads.search({ id: Number(handle) })
  const [item] = found || []
  if (!item) return null
  return { state: item.state, error: item.error }
}

async function openDownload() {
  if (lastCompletedDownloadId != null && chrome.downloads.show) {
    try {
      await chrome.downloads.show(lastCompletedDownloadId)
      return controller.getState()
    } catch (_) {
      if (chrome.downloads.showDefaultFolder) chrome.downloads.showDefaultFolder()
      return controller.getState()
    }
  }
  if (chrome.downloads.showDefaultFolder) chrome.downloads.showDefaultFolder()
  return controller.getState()
}

async function saveState(state) {
  await chrome.storage.session.set({ [SESSION_KEY]: state })
}

async function emitState(state) {
  const tabs = await chrome.tabs.query({ url: 'https://www.wildberries.ru/catalog/*/detail.aspx*' })
  await Promise.all((tabs || []).map(async (tab) => {
    if (!tab.id) return
    try {
      await chrome.tabs.sendMessage(tab.id, { type: 'JOB_STATE', state })
    } catch (_) {}
  }))
}

const controller = WbJobController.createJobController({
  fetchJson,
  probe,
  start: startDownload,
  cancel: cancelDownload,
  saveState,
  emitState
})

function allowedResourceUrls(resourceUrls, nm) {
  return (Array.isArray(resourceUrls) ? resourceUrls : [])
    .filter((url) => WbMediaResolver.isAllowedMediaUrl(url, nm, 'video') ||
      WbMediaResolver.isAllowedMediaUrl(url, nm, 'gallery') ||
      WbMediaResolver.isAllowedMediaUrl(url, nm, 'rich'))
    .slice(0, 100)
}

function narrowPayload(message) {
  const nm = String((message && message.nm) || '').trim()
  return {
    nm,
    cardUrl: String((message && message.cardUrl) || ''),
    resourceUrls: allowedResourceUrls(message && message.resourceUrls, nm),
    onlyMain: Boolean(message && message.onlyMain)
  }
}

function ensureRestore() {
  if (typeof controller.isActive === 'function' && controller.isActive()) return Promise.resolve(null)
  if (restorePromise) return restorePromise
  restorePromise = chrome.storage.session.get(SESSION_KEY)
    .then((stored) => {
      const saved = stored && stored[SESSION_KEY]
      if (saved && ACTIVE_PHASES.has(saved.phase)) {
        return controller.restore(saved, reconcileDownload)
      }
      return null
    })
    .finally(() => { restorePromise = null })
  return restorePromise
}

ensureRestore()

chrome.downloads.onChanged.addListener(() => {
  ensureRestore()
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!sender || !WbMediaCard.isProductPage(sender.url || '') || !MESSAGE_TYPES.has(message && message.type)) {
    sendResponse({ ok: false, error: 'unsupported message' })
    return false
  }

  Promise.resolve()
    .then(() => ensureRestore())
    .then(async () => {
      if (message.type === 'START_JOB') return controller.start(narrowPayload(message))
      if (message.type === 'STOP_JOB') return controller.stop()
      if (message.type === 'RETRY_FAILED') return controller.retryFailed()
      if (message.type === 'OPEN_DOWNLOAD') return openDownload()
      return controller.getState()
    })
    .then((state) => sendResponse({ ok: true, state }))
    .catch((error) => sendResponse({ ok: false, error: error && error.message ? error.message : String(error) }))
  return true
})
