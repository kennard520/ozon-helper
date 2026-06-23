import { getToken, clearAuth, authHeader } from './auth.js'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function req(method, path, body) {
  const opts = { method, headers: { ...authHeader(getToken()) } }
  if (body !== undefined) { opts.headers = { ...opts.headers, ...JSON_HEADERS }; opts.body = JSON.stringify(body) }
  const resp = await fetch(path, opts)
  const data = await resp.json().catch(() => ({}))
  if (resp.status === 401) {
    // token 失效/未登录：清登录态并通知 App 跳登录页
    clearAuth()
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('auth:logout'))
  }
  if (!resp.ok) throw Object.assign(new Error(data.detail || `HTTP ${resp.status}`), { status: resp.status, data })
  return data
}
const qs = (o) => Object.entries(o)
  .filter(([, v]) => v !== undefined && v !== '')
  .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&')
// 店铺查询后缀：非空才拼 ?store_client_id=...（空=不按店过滤，后端按默认店）
const _sq = (cid) => (cid ? `?store_client_id=${encodeURIComponent(cid)}` : '')

export const api = {
  state: () => req('GET', '/api/state'),
  saveSettings: (p) => req('POST', '/api/settings', p),
  aiModels: (kind, base, key, platform) => req('POST', '/api/ai/models', { kind, base, key, platform }),
  listDrafts: (params = {}) => { const q = qs(params); return req('GET', q ? `/api/drafts?${q}` : '/api/drafts') },
  patchDraft: (id, patch) => req('PATCH', `/api/drafts/${id}`, patch),
  batchUpdateDrafts: (ids, patch) => req('POST', '/api/drafts/batch-update', { ids, ...patch }),
  batchPublish: (ids, store_client_id) => req('POST', '/api/drafts/batch-publish', store_client_id ? { ids, store_client_id } : { ids }),
  copyToStore: (id, store_client_id) => req('POST', `/api/drafts/${id}/copy-to-store`, { store_client_id }),
  deleteDraft: (id) => req('DELETE', `/api/drafts/${id}`),
  publishPreview: (id, store_client_id) => req('GET', `/api/drafts/${id}/publish-preview${store_client_id ? `?store_client_id=${encodeURIComponent(store_client_id)}` : ''}`),
  publish: (id, store_client_id) => req('POST', `/api/drafts/${id}/publish`, store_client_id ? { store_client_id } : {}),
  publishPreflight: (id) => req('GET', `/api/drafts/${id}/publish-preflight`),
  publishGroup: (variant_group, store_client_id) => req('POST', '/api/ext/publish-group', store_client_id ? { variant_group, store_client_id } : { variant_group }),
  recognizeCategory: (id) => req('POST', `/api/drafts/${id}/recognize-category`),
  autoMap: (id) => req('POST', `/api/drafts/${id}/auto-map`),
  aiFillAttributes: (id) => req('POST', `/api/drafts/${id}/ai-fill-attributes`),
  aiGenerate: (id) => req('POST', `/api/drafts/${id}/ai-generate`),
  aiCopy: (id) => req('POST', `/api/drafts/${id}/ai-copy`),
  aiImagePrompts: (id, n_points = 3) => req('POST', `/api/drafts/${id}/ai-image-prompts`, { n_points }),
  aiProposalPatch: (id, patch) => req('PATCH', `/api/drafts/${id}/ai-proposal`, patch),
  aiProposalApply: (id) => req('POST', `/api/drafts/${id}/ai-proposal/apply`),
  aiImage: (id, p) => req('POST', `/api/drafts/${id}/ai-image`, p),
  makeInfographic: (id, p = {}) => req('POST', `/api/drafts/${id}/make-infographic`, p),
  tryCopy: (id) => req('POST', `/api/drafts/${id}/try-copy`),
  makeRichContent: (id, p = {}) => req('POST', `/api/drafts/${id}/make-rich-content`, p),
  understand: (id, p = {}) => req('POST', `/api/drafts/${id}/understand`, p),
  recommend: (id) => req('GET', `/api/drafts/${id}/recommend`),
  localizeImage: (id, p = {}) => req('POST', `/api/drafts/${id}/localize-image`, p),
  regenImage: (id, p = {}) => req('POST', `/api/drafts/${id}/regen-image`, p),
  whitenMain: (id, p = {}) => req('POST', `/api/drafts/${id}/whiten-main`, p),
  sceneImage: (id, p = {}) => req('POST', `/api/drafts/${id}/scene-image`, p),
  imagePlan: (id, force = false) => req('GET', `/api/drafts/${id}/image-plan${force ? '?force=true' : ''}`),
  designImagePlan: (id, target = 10) => req('POST', `/api/drafts/${id}/design-image-plan`, { target }),
  generatePlanSlot: (id, slotId) => req('POST', `/api/drafts/${id}/generate-plan-slot`, { slot_id: slotId }),
  applyCandidates: (id, indices) => req('POST', `/api/drafts/${id}/apply-candidates`, indices ? { indices } : {}),
  discardCandidates: (id) => req('POST', `/api/drafts/${id}/discard-candidates`),
  aiVideo: (id, p = {}) => req('POST', `/api/drafts/${id}/ai-video`, p),
  aiVideoStatus: () => req('GET', '/api/ai-video/status'),
  aiVideoStop: () => req('POST', '/api/ai-video/stop'),
  uploadMedia: async (id, file, kind = 'image') => {
    const fd = new FormData(); fd.append('file', file); fd.append('kind', kind)
    const resp = await fetch(`/api/drafts/${id}/media`, { method: 'POST', body: fd })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    return data
  },
  translateDraft: (id) => req('POST', `/api/drafts/${id}/translate`),
  requiredCheck: (id, language = 'ZH_HANS') => req('GET', `/api/drafts/${id}/required-check?${qs({ language })}`),
  categorySearch: (q, limit = 500) => req('GET', `/api/category/search?${qs({ q, limit })}`),
  categoryTree: () => req('GET', '/api/category/tree'),
  categoryResolve: (cat, type) => req('GET', `/api/category/resolve?${qs({ cat, type })}`),
  categoryAttributes: (cat, type, language = 'ZH_HANS') => req('GET', `/api/category/attributes?${qs({ cat, type, language })}`),
  attributeValues: (cat, type, attr, q, language = 'ZH_HANS') => req('GET', `/api/attribute/values/search?${qs({ cat, type, attr, q, language })}`),
  attributeOptions: (cat, type, attr, language = 'ZH_HANS') => req('GET', `/api/attribute/values?${qs({ cat, type, attr, language })}`),
  getCommissionMap: (cat, type) => req('GET', `/api/commission-map?${qs({ cat, type })}`),
  saveCommissionMap: (p) => req('POST', '/api/commission-map', p),
  // realFBS 运费路线表（智能定价用，可 CSV 维护）
  realfbsRoutes: () => req('GET', '/api/realfbs-routes'),
  importRealfbsRoutes: (csv) => req('POST', '/api/realfbs-routes/import', { csv }),
  exportRealfbsRoutes: async () => {
    const resp = await fetch('/api/realfbs-routes/export', { headers: { ...authHeader(getToken()) } })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return await resp.text()
  },
  // realFBS 佣金类目表（只 FBS=RFBS；可丢 Ozon 官方 Tarifs xlsx 或本工具导出的模板）
  commissionCategories: () => req('GET', '/api/commission-categories'),
  importCommissionCategories: async (file) => {
    const fd = new FormData(); fd.append('file', file)
    const resp = await fetch('/api/commission-categories/import', {
      method: 'POST', headers: { ...authHeader(getToken()) }, body: fd,
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)
    return data
  },
  exportCommissionCategories: async () => {
    const resp = await fetch('/api/commission-categories/export', { headers: { ...authHeader(getToken()) } })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return await resp.blob()
  },
  listWarehouses: (store_client_id) => req('GET', `/api/warehouses${_sq(store_client_id)}`),
  syncWarehouses: (store_client_id) => req('POST', `/api/warehouses/sync${_sq(store_client_id)}`),
  setDefaultWarehouse: (warehouse_id, store_client_id) => req('POST', `/api/warehouses/default${_sq(store_client_id)}`, { warehouse_id }),
  fbsPull: (status = 'awaiting_packaging', days = 14, store_client_id) => req('POST', `/api/fbs/pull${_sq(store_client_id)}`, { status, days }),
  fbsProcurement: (store_client_id) => req('GET', `/api/fbs/procurement${_sq(store_client_id)}`),
  fbsSetState: (id, purchase_state, note = '', store_client_id) => req('POST', `/api/fbs/procurement/${id}/state${_sq(store_client_id)}`, { purchase_state, note }),
  fbsShip: (posting_number, store_client_id) => req('POST', `/api/fbs/ship${_sq(store_client_id)}`, { posting_number }),
  fbsLabelUrl: (posting, store_client_id) => `/api/fbs/label?posting=${encodeURIComponent(posting)}${store_client_id ? '&store_client_id=' + encodeURIComponent(store_client_id) : ''}`,
  // 鉴权 + 钱包
  login: (username, password) => req('POST', '/api/auth/login', { username, password }),
  me: () => req('GET', '/api/auth/me'),
  adminListUsers: () => req('GET', '/api/admin/users'),
  adminCreateUser: (username, password, max_stores) => req('POST', '/api/admin/users', { username, password, max_stores }),
  adminUpdateUser: (id, patch) => req('PATCH', `/api/admin/users/${id}`, patch),
  adminDeleteUser: (id) => req('DELETE', `/api/admin/users/${id}`),
  wallet: () => req('GET', '/api/wallet'),
  walletRecharge: (amount, remark = '') => req('POST', '/api/wallet/recharge', { amount, remark }),
}
