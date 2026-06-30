import { ref, computed } from 'vue'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}
function daysAgoStr(n) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

export function useAnalytics() {
  const appStore = useAppStore()
  const storeList = computed(() => appStore.settings.ozon_stores || [])

  // 当前选中店铺 client_id
  const store = ref('')
  // 时间范围：preset = '7' | '30' | 'custom'；from/to 为 yyyy-mm-dd
  const dateRange = ref({ preset: '30', from: daysAgoStr(30), to: todayStr() })

  const loading = ref(false)
  const error = ref('')

  const dashboard = ref(null)
  const traffic = ref(null)
  const keywords = ref(null)

  const activeTab = ref('product')   // 'product' | 'traffic' | 'keyword'

  function _params() {
    return {
      date_from: dateRange.value.from,
      date_to: dateRange.value.to,
      store_client_id: store.value || undefined,
    }
  }

  async function load() {
    loading.value = true
    error.value = ''
    traffic.value = null
    keywords.value = null
    try {
      dashboard.value = await api.analyticsDashboard(_params())
    } catch (e) {
      if (e.status === 400) {
        error.value = e.data?.detail || '请先在系统设置配置 Ozon 店铺凭证'
      } else {
        error.value = e.message || '加载失败'
      }
      dashboard.value = null
    } finally {
      loading.value = false
    }
  }

  async function loadTab(tab) {
    activeTab.value = tab
    if (tab === 'traffic' && !traffic.value) {
      loading.value = true
      error.value = ''
      try {
        traffic.value = await api.analyticsTraffic(_params())
      } catch (e) {
        error.value = e.status === 400
          ? (e.data?.detail || '请先在系统设置配置 Ozon 店铺凭证')
          : (e.message || '加载失败')
      } finally {
        loading.value = false
      }
    } else if (tab === 'keyword' && !keywords.value) {
      loading.value = true
      error.value = ''
      try {
        keywords.value = await api.analyticsKeywords(_params())
      } catch (e) {
        error.value = e.status === 400
          ? (e.data?.detail || '请先在系统设置配置 Ozon 店铺凭证')
          : (e.message || '加载失败')
      } finally {
        loading.value = false
      }
    }
  }

  function setRange(preset, from, to) {
    if (preset === 'today') {
      dateRange.value = { preset: 'today', from: todayStr(), to: todayStr() }
    } else if (preset === 'yesterday') {
      const y = daysAgoStr(1)
      dateRange.value = { preset: 'yesterday', from: y, to: y }
    } else if (preset === '7') {
      dateRange.value = { preset: '7', from: daysAgoStr(7), to: todayStr() }
    } else if (preset === '30') {
      dateRange.value = { preset: '30', from: daysAgoStr(30), to: todayStr() }
    } else {
      dateRange.value = { preset: 'custom', from: from || dateRange.value.from, to: to || dateRange.value.to }
    }
    // 重拉 dashboard；tab 数据清空等待懒拉
    traffic.value = null
    keywords.value = null
    return load()
  }

  function exportCsv() {
    const rows = dashboard.value?.rows || []
    const BOM = '﻿'
    const headers = ['SKU', '商品名', '价格', '库存', '曝光', '访问', '加购', '下单', '收入', '转化率%', '诊断']
    const lines = [
      headers.join(','),
      ...rows.map(r => [
        r.sku,
        `"${(r.title || '').replace(/"/g, '""')}"`,
        r.price,
        r.stock,
        r.exposure,
        r.sessions,
        r.cart,
        r.ordered_units,
        r.revenue,
        r.conv_cart_pct,
        `"${(r.diagnostics || []).join(';')}"`,
      ].join(',')),
    ]
    const csv = BOM + lines.join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `analytics_${dateRange.value.from}_${dateRange.value.to}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return {
    loading,
    error,
    store,
    storeList,
    dateRange,
    dashboard,
    traffic,
    keywords,
    activeTab,
    load,
    loadTab,
    setRange,
    exportCsv,
  }
}
