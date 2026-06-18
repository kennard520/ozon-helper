import { defineStore } from 'pinia'
import { api } from '../api.js'

export const useAppStore = defineStore('app', {
  state: () => ({
    drafts: [], selectedId: null, selected: new Set(),
    filter: 'all', sourcePlatform: '1688',
    settings: {}, status: {}, paths: {}, login: {},
    // 当前操作店铺（client_id）：店铺级操作（发布默认目标，将来仓库/订单）都以它为上下文
    currentStore: '',
    // 后端分页：drafts 只存当前页；总数/计数由后端给（前端无法自算）
    page: 1, pageSize: 20, total: 0,
    serverCounts: { all: 0, invalid: 0, ready: 0, failed: 0, published: 0 },
  }),
  getters: {
    storeList: (s) => s.settings.ozon_stores || [],
    currentStoreName: (s) => {
      const hit = (s.settings.ozon_stores || []).find(x => String(x.client_id) === String(s.currentStore))
      return hit ? hit.name : ''
    },
    // 后端已按 filter 分页，drafts 即当前页，直接用
    filteredDrafts: (s) => s.drafts,
    selectedDraft: (s) => s.drafts.find(d => d.id === s.selectedId) || null,
    // Tab 计数走后端全量统计，不依赖当前页
    counts: (s) => s.serverCounts,
    pageCount: (s) => Math.max(1, Math.ceil(s.total / s.pageSize)),
  },
  actions: {
    async loadState() { const r = await api.state(); this.settings = r.settings; this.status = r.status; this.paths = r.paths; this.login = r.login || {}; this.ensureCurrentStore() },
    // 选定当前店：已选且仍在列表里则保留；否则取上次保存(localStorage)，再否则默认店/列表第一个
    ensureCurrentStore() {
      const list = this.settings.ozon_stores || []
      if (!list.length) { this.currentStore = ''; return }
      const ids = list.map(s => String(s.client_id))
      let cid = this.currentStore
      if (!cid) { try { cid = localStorage.getItem('current_store') || '' } catch { /* ignore */ } }
      if (!cid || !ids.includes(String(cid))) {
        const def = list.find(s => s.is_default) || list[0]
        cid = String(def.client_id)
      }
      this.currentStore = String(cid)
    },
    setCurrentStore(cid) {
      this.currentStore = String(cid || '')
      try { localStorage.setItem('current_store', this.currentStore) } catch { /* ignore */ }
      this.selectedId = null   // 切店清空选中（旧店草稿不属于新店）
      this.page = 1
      this.loadDrafts()
    },
    async loadDrafts() {
      // 草稿绑定店：带当前店 → 只看当前店的货（currentStore 为空时 qs 自动省略=不按店过滤）
      const r = await api.listDrafts({ status: this.filter, page: this.page, page_size: this.pageSize, store_client_id: this.currentStore })
      this.drafts = r.drafts || []
      this.total = r.total ?? this.drafts.length
      if (r.counts) this.serverCounts = r.counts
      if (r.page) this.page = r.page
      if (r.page_size) this.pageSize = r.page_size
    },
    async setFilter(f) { this.filter = f; this.page = 1; await this.loadDrafts() },
    async setPage(p) { this.page = p; await this.loadDrafts() },
    async setPageSize(sz) { this.pageSize = sz; this.page = 1; await this.loadDrafts() },
    // 后端分页后 drafts 只是当前页：只就地更新已在页内的草稿；新草稿不 unshift（会撑破页大小、
    // total/counts 不同步），交给 loadDrafts 重新拉。返回是否命中，调用方可据此决定要不要 reload。
    upsertDraft(d) { const i = this.drafts.findIndex(x => x.id === d.id); if (i >= 0) { this.drafts[i] = d; return true } return false },
    removeDraft(id) { this.drafts = this.drafts.filter(d => d.id !== id); this.selected.delete(id); if (this.selectedId === id) this.selectedId = null },
  },
})
