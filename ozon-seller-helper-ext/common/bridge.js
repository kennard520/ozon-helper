// 插件↔本机后端 桥（UMD：content script/popup 全局 OzonHelperBridge + service worker importScripts + vitest import）
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.OzonHelperBridge = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  const CANDIDATE_PORTS = [8585, 8787, 5050, 7373, 6464, 9911, 8123, 5151, 19283, 28282]
  // 生产：写死服务器地址（用户版直连）。开发时可在 popup 填“自定义后端地址”覆盖。
  // 注意：HTTP 明文，正式对外建议换成 https://你的域名（服务器套 Caddy）。
  const PROD_BASE = 'http://8.152.196.119:8585'  // 生产：服务器地址（开发联调可在 popup 填“自定义后端地址”覆盖为 127.0.0.1:8585）
  const PATHS = {
    ping: '/api/ext/ping',
    collect: '/api/ext/collect',
    collectParsed: '/api/ext/collect-parsed',
    snapshot: '/api/ext/snapshot',
    snapshots: '/api/ext/snapshots',
    pendingMediaDrafts: '/api/ext/pending-media-drafts',
    updateDraftMedia: '/api/ext/update-draft-media'
  }
  const GET_TYPES = new Set(['ping', 'snapshots', 'pendingMediaDrafts'])

  // 多用户：插件以登录用户身份连后端。给定 JWT 返回鉴权头（纯函数，便于单测）。
  function authHeader(token) {
    return token ? { Authorization: 'Bearer ' + token } : {}
  }

  function candidateBases() {
    return CANDIDATE_PORTS.map((p) => 'http://127.0.0.1:' + p)
  }

  // 返回相对请求；真实 base 由 background 探测后拼接
  function buildExtRequest(type, payload) {
    const p = PATHS[type]
    if (!p) return null
    const method = GET_TYPES.has(type) ? 'GET' : 'POST'
    let path = p
    let body = null
    if (method === 'GET') {
      if (payload && Object.keys(payload).length) path += '?' + new URLSearchParams(payload).toString()
    } else {
      body = JSON.stringify(payload || {})
    }
    return { path, method, body }
  }

  function bgCall(type, payload) {
    return new Promise((resolve) => {
      // 重载/更新插件后，旧页面里的 content script 上下文会失效（chrome.runtime 失踪）→ 给人话提示
      if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.id) {
        resolve({ ok: false, error: '插件已更新/重载，请刷新本页面(F5)后再试' })
        return
      }
      try {
        chrome.runtime.sendMessage({ type, payload }, (resp) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message })
          } else {
            resolve(resp || { ok: false, error: 'no response' })
          }
        })
      } catch (e) {
        resolve({ ok: false, error: String(e) })
      }
    })
  }

  return { CANDIDATE_PORTS, PROD_BASE, candidateBases, buildExtRequest, bgCall, authHeader }
})
