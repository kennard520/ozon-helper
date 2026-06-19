// MV3 service worker：唯一直连本机后端的地方；自动探测后端端口（用户机器端口保留严重）
importScripts('/common/bridge.js', '/common/media-upload.js', '/common/wb.js')

let DISCOVERED = null

function _ping(base) {
  return new Promise((resolve) => {
    const c = new AbortController()
    const t = setTimeout(() => c.abort(), 1500)
    fetch(base + '/api/ext/ping', { signal: c.signal })
      .then((r) => resolve(r.ok))
      .catch(() => resolve(false))
      .finally(() => clearTimeout(t))
  })
}

// 开发可在 popup 填“自定义后端地址”覆盖（存 chrome.storage.local.ozon_backend_base）
async function getBackendOverride() {
  try {
    const st = await chrome.storage.local.get('ozon_backend_base')
    const b = (st && st.ozon_backend_base) || ''
    return b ? String(b).replace(/\/+$/, '') : ''
  } catch (e) {
    return ''
  }
}

async function discoverBase() {
  if (DISCOVERED && (await _ping(DISCOVERED))) return DISCOVERED
  DISCOVERED = null
  // 顺序：开发自定义地址 → 生产写死服务器 → 本机端口探测(本地开发兜底)
  const bases = []
  const override = await getBackendOverride()
  if (override) bases.push(override)
  bases.push(self.OzonHelperBridge.PROD_BASE)
  bases.push(...self.OzonHelperBridge.candidateBases())
  for (const base of bases) {
    if (await _ping(base)) {
      DISCOVERED = base
      return base
    }
  }
  return null
}

// ===== 媒体重托管：插件下载源媒体 → 用登录 cookie 直传「自己的 Ozon 店铺」媒体库 → 拿 ir.ozone.ru =====
const SELLER = 'https://seller.ozon.ru'
let COMPANY_ID = null

// 取 companyId：① chrome.storage 手动覆盖 ② 读 seller.ozon.ru 的 cookie 扫出 ③ 缓存
async function getCompanyId() {
  if (COMPANY_ID) return COMPANY_ID
  try {
    const st = await chrome.storage.local.get('ozonCompanyId')
    if (st && st.ozonCompanyId) { COMPANY_ID = String(st.ozonCompanyId); return COMPANY_ID }
  } catch (e) { /* ignore */ }
  try {
    const cookies = await chrome.cookies.getAll({ domain: 'ozon.ru' })
    const hay = (cookies || []).map((c) => c.name + '=' + c.value).join('; ')
    const id = self.OzonHelperMedia.parseCompanyId(hay)
    if (id) {
      COMPANY_ID = id
      try { await chrome.storage.local.set({ ozonCompanyId: id }) } catch (e) { /* ignore */ }
      return id
    }
  } catch (e) { /* ignore */ }
  return null
}

function _fileName(url, i) {
  try {
    const seg = new URL(url).pathname.split('/').filter(Boolean).pop()
    if (seg && seg.length <= 80) return seg.indexOf('.') >= 0 ? seg : seg + '.jpg'
  } catch (e) { /* ignore */ }
  return 'media_' + i + '.jpg'
}

// 带超时的 fetch：源图 CDN 或上传接口挂起时不会永久卡死（超时即 abort，视为该图失败、跳过保留原链接）
function _fetchT(url, opts, ms) {
  const c = new AbortController()
  const t = setTimeout(() => c.abort(), ms || 30000)
  return fetch(url, Object.assign({}, opts || {}, { signal: c.signal })).finally(() => clearTimeout(t))
}

// 下载一个源 URL → 直传卖家媒体库 → 返回 ir.ozone.ru URL（失败抛错）
async function _uploadOne(url, i, companyId) {
  const dl = await _fetchT(url, {}, 30000) // host_permissions <all_urls> 绕过页面 CORS
  if (!dl.ok) throw new Error('download ' + dl.status)
  const blob = await dl.blob()
  const fd = new FormData()
  fd.append('file_name', _fileName(url, i))
  fd.append('tmp', 'true')
  fd.append('body', blob, _fileName(url, i))
  const up = await _fetchT(SELLER + '/api/media-storage/upload-file', {
    method: 'POST', credentials: 'include',
    headers: { 'x-o3-company-id': String(companyId) }, body: fd
  }, 45000)
  const text = await up.text()
  if (!up.ok) throw new Error('upload ' + up.status + ': ' + text.slice(0, 160))
  let irUrl = null
  try { irUrl = (JSON.parse(text) || {}).url } catch (e) { /* non-json */ }
  if (!irUrl) throw new Error('upload 无 url: ' + text.slice(0, 160))
  return irUrl
}

// 多线程并发(限 6)把 urls 直传到卖家媒体库；返回 {map:{原:ir.ozone.ru}, failed:[], companyId}
async function uploadMedia(urls) {
  const companyId = await getCompanyId()
  if (!companyId) return { map: {}, failed: urls || [], error: 'no-company-id' }
  const list = Array.from(new Set((urls || []).filter(Boolean)))
  const map = {}
  const failed = []
  let idx = 0
  async function worker() {
    while (idx < list.length) {
      const i = idx++
      const u = list[i]
      try { map[u] = await _uploadOne(u, i, companyId) }
      catch (e) { failed.push(u) }
    }
  }
  await Promise.all([0, 1, 2, 3, 4, 5].map(() => worker()))  // 6 路并发
  return { map, failed, companyId }
}

// ===== 媒体重托管（OSS 预签名直传，国内快）=====
async function _sha256Hex(buf) {
  const h = await crypto.subtle.digest('SHA-256', buf)
  return Array.from(new Uint8Array(h)).map((x) => x.toString(16).padStart(2, '0')).join('')
}

function _extOf(ct, url) {
  const c = String(ct || '').toLowerCase()
  if (c.includes('png')) return 'png'
  if (c.includes('webp')) return 'webp'
  if (c.includes('gif')) return 'gif'
  if (c.includes('mp4')) return 'mp4'
  if (c.includes('jpeg') || c.includes('jpg')) return 'jpg'
  const m = String(url || '').toLowerCase().match(/\.(jpg|jpeg|png|webp|gif|mp4)\b/)
  return m ? (m[1] === 'jpeg' ? 'jpg' : m[1]) : 'jpg'
}

// 下载源图 → sha256 当内容 key → 后端签名 → PUT 直传 OSS。返回 {map:{原url:OSS直链}, failed:[]}
// 与 uploadMedia 同结构，给 _rehostMedia 复用。需插件已登录（presign 要 JWT）。
async function uploadMediaOss(urls) {
  const base = await discoverBase()
  if (!base) return { map: {}, failed: urls || [], error: 'no backend' }
  const jwt = await getJwt()
  const list = Array.from(new Set((urls || []).filter(Boolean)))
  const map = {}
  const failed = []
  // 1) 并发下载源图 + 算内容哈希 key
  const dl = []   // {u, blob, key, ct}
  let i = 0
  async function dlWorker() {
    while (i < list.length) {
      const u = list[i++]
      try {
        const r = await _fetchT(u, {}, 30000)
        if (!r.ok) { failed.push(u); continue }
        const blob = await r.blob()
        const buf = await blob.arrayBuffer()
        const ct = blob.type || ('image/' + _extOf('', u))
        const key = 'ozon-media/' + (await _sha256Hex(buf)) + '.' + _extOf(ct, u)
        dl.push({ u, blob, key, ct })
      } catch (e) { failed.push(u) }
    }
  }
  await Promise.all([0, 1, 2, 3, 4, 5].map(() => dlWorker()))
  if (!dl.length) return { map, failed }
  // 2) 一次性向后端要预签名（需登录 JWT）
  let results = []
  try {
    const pr = await _fetchT(base + '/api/media/presign', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, jwt ? { Authorization: 'Bearer ' + jwt } : {}),
      body: JSON.stringify({ items: dl.map((d) => ({ key: d.key, content_type: d.ct })) })
    }, 15000)
    if (!pr.ok) return { map, failed: list, error: 'presign ' + pr.status }
    results = ((await pr.json()) || {}).results || []
  } catch (e) { return { map, failed: list, error: String(e) } }
  const byKey = {}
  results.forEach((p) => { byKey[p.key] = p })
  // 3) 并发 PUT 直传 OSS（已存在的 upload_url 为 null，直接用 url，不重传）
  let j = 0
  async function upWorker() {
    while (j < dl.length) {
      const d = dl[j++]
      const p = byKey[d.key]
      if (!p) { failed.push(d.u); continue }
      try {
        if (p.upload_url) {
          const put = await _fetchT(p.upload_url, { method: 'PUT', headers: { 'Content-Type': d.ct }, body: d.blob }, 45000)
          if (!put.ok) { failed.push(d.u); continue }
        }
        map[d.u] = p.url
      } catch (e) { failed.push(d.u) }
    }
  }
  await Promise.all([0, 1, 2, 3, 4, 5].map(() => upWorker()))
  return { map, failed }
}

// 多用户：插件存登录用户的 JWT，所有后端请求带上
async function getJwt() {
  try {
    const st = await chrome.storage.local.get('ozon_jwt')
    return (st && st.ozon_jwt) || ''
  } catch (e) {
    return ''
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  ;(async () => {
    // 登录：拿用户名密码换 JWT 存起来
    if (msg && msg.type === 'login') {
      const base = await discoverBase()
      if (!base) { sendResponse({ ok: false, error: 'no backend' }); return }
      try {
        const r = await fetch(base + '/api/auth/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: msg.payload.username, password: msg.payload.password })
        })
        const data = await r.json().catch(() => ({}))
        if (r.ok && data.token) {
          await chrome.storage.local.set({ ozon_jwt: data.token, ozon_user: data.user })
          sendResponse({ ok: true, data: { user: data.user } })
        } else {
          sendResponse({ ok: false, error: data.detail || ('HTTP ' + r.status) })
        }
      } catch (e) {
        sendResponse({ ok: false, error: String(e) })
      }
      return
    }
    if (msg && msg.type === 'authStatus') {
      const st = await chrome.storage.local.get(['ozon_jwt', 'ozon_user'])
      sendResponse({ ok: true, data: { loggedIn: !!(st && st.ozon_jwt), user: (st && st.ozon_user) || null } })
      return
    }
    if (msg && msg.type === 'logout') {
      await chrome.storage.local.remove(['ozon_jwt', 'ozon_user'])
      sendResponse({ ok: true })
      return
    }

    // WB：在 background 探测 + 取 card.json（content script 跨域 wbbasket 受限；bg 有 <all_urls>）
    if (msg && msg.type === 'wbResolveCard') {
      const nm = msg.payload && msg.payload.nm
      const cands = self.OzonHelperWb.basketCardUrls(nm)
      for (const c of cands) {
        try {
          const r = await fetch(c.url)
          if (!r.ok) continue
          const txt = await r.text()
          if (txt.trim()[0] !== '{') continue
          sendResponse({ ok: true, data: { card: JSON.parse(txt), host: c.host } })
          return
        } catch (e) { /* 试下一个 basket */ }
      }
      sendResponse({ ok: false, error: 'WB card.json 不可达' })
      return
    }

    // 媒体重托管：插件下载源媒体 → 传自己 Ozon 店铺 → 回 {map}
    if (msg && msg.type === 'uploadMedia') {
      try {
        const res = await uploadMedia(msg.payload && msg.payload.urls)
        sendResponse({ ok: true, data: res })
      } catch (e) {
        sendResponse({ ok: false, error: String(e) })
      }
      return
    }

    // 媒体重托管（OSS 预签名直传，国内快）：下载源图 → 直传 OSS → 回 {map}
    if (msg && msg.type === 'uploadMediaOss') {
      try {
        const res = await uploadMediaOss(msg.payload && msg.payload.urls)
        sendResponse({ ok: true, data: res })
      } catch (e) {
        sendResponse({ ok: false, error: String(e) })
      }
      return
    }

    // 打开 webui（编辑器/后台）独立弹窗——带上 JWT 做单点登录(插件登过,网页免再登)
    if (msg && (msg.type === 'openEditor' || msg.type === 'openAdmin')) {
      const base = await discoverBase()
      if (!base) {
        sendResponse({ ok: false, error: 'no backend' })
        return
      }
      const id = msg.payload && msg.payload.draftId
      const jwt = await getJwt()
      const params = []
      if (jwt) params.push('token=' + encodeURIComponent(jwt))
      if (msg.type === 'openEditor' && id != null) params.push('edit=' + encodeURIComponent(id))
      const url = base + '/' + (params.length ? '?' + params.join('&') : '')
      chrome.tabs.create({ url, active: true }, () => sendResponse({ ok: true }))
      return
    }

    const req = self.OzonHelperBridge.buildExtRequest(msg && msg.type, msg && msg.payload)
    if (!req) {
      sendResponse({ ok: false, error: 'unknown type' })
      return
    }
    const base = await discoverBase()
    if (!base) {
      sendResponse({ ok: false, error: 'no backend' })
      return
    }
    const opts = { method: req.method, headers: { ...self.OzonHelperBridge.authHeader(await getJwt()) } }
    if (req.body) {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = req.body
    }
    // 采集/推送要在后端建草稿+匹配类目（可能调 Ozon API，慢）给长超时；其余短超时
    const timeoutMs = (msg.type === 'collect' || msg.type === 'collectParsed') ? 120000 : 8000
    const c = new AbortController()
    const t = setTimeout(() => c.abort(), timeoutMs)
    opts.signal = c.signal
    try {
      const r = await fetch(base + req.path, opts)
      let data = null
      try {
        data = await r.json()
      } catch (e) {
        /* non-json */
      }
      sendResponse({ ok: r.ok, status: r.status, data })
    } catch (e) {
      sendResponse({ ok: false, error: String(e) })
    } finally {
      clearTimeout(t)
    }
  })()
  return true // 异步 sendResponse
})
