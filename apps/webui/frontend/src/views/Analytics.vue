<script setup>
import { onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAnalytics } from '../composables/useAnalytics.js'
import SAlert from '../ui/SAlert.vue'
import SButton from '../ui/SButton.vue'
import STabs from '../ui/STabs.vue'
import DiagnosticBanner from '../components/analytics/DiagnosticBanner.vue'
import ConversionFunnel from '../components/analytics/ConversionFunnel.vue'
import KpiCards from '../components/analytics/KpiCards.vue'
import ProductTable from '../components/analytics/ProductTable.vue'
import TrafficTrend from '../components/analytics/TrafficTrend.vue'
import KeywordInsight from '../components/analytics/KeywordInsight.vue'

const router = useRouter()
const {
  loading, error, store, storeList, dateRange,
  dashboard, traffic, keywords, activeTab,
  load, loadTab, setRange, exportCsv,
} = useAnalytics()

const TABS = [
  { key: 'product', label: '商品表现' },
  { key: 'traffic', label: '流量趋势' },
  { key: 'keyword', label: '搜索词洞察' },
]

const RANGE_OPTS = [
  { label: '近 7 天', value: '7' },
  { label: '近 30 天', value: '30' },
]

function onTabChange(key) {
  loadTab(key)
}

function onRangeChange(preset) {
  setRange(preset)
}

function onOpenDraft(row) {
  // 尝试跳转到工作台草稿，如 offer_id 可定位就传，否则退回首页
  if (row && row.offer_id) {
    router.push({ path: '/', query: { offer_id: row.offer_id } })
  } else {
    router.push('/')
  }
}

onMounted(() => {
  load()
})
</script>
<template>
  <div class="analytics-page">
    <!-- 页头 -->
    <div class="ap__header">
      <div class="ap__title-row">
        <h2 class="ap__title">数据分析</h2>
        <span class="ap__note">数据 T+1~2 滞后（Ozon 官方限制）</span>
      </div>
      <div class="ap__controls">
        <!-- 店铺下拉 -->
        <select v-if="storeList.length > 1" v-model="store" class="ap__select" @change="load()">
          <option value="">全部店铺</option>
          <option v-for="s in storeList" :key="s.client_id" :value="s.client_id">{{ s.name }}</option>
        </select>
        <!-- 时间范围 -->
        <div class="ap__range-btns">
          <button
            v-for="opt in RANGE_OPTS"
            :key="opt.value"
            class="ap__range-btn"
            :class="{ 'is-active': dateRange.preset === opt.value }"
            @click="onRangeChange(opt.value)"
          >{{ opt.label }}</button>
        </div>
        <!-- 导出 -->
        <SButton variant="ghost" size="sm" @click="exportCsv" :disabled="!dashboard">导出 CSV</SButton>
      </div>
    </div>

    <!-- 错误提示 -->
    <SAlert v-if="error" variant="warn" :title="error" style="margin-bottom:16px">
      请前往「系统设置」配置 Ozon 店铺 Client-ID 和 API Key。
    </SAlert>

    <!-- 加载骨架 -->
    <div v-if="loading" class="ap__skeleton">
      <div class="ap__sk-row"></div>
      <div class="ap__sk-row ap__sk-row--sm"></div>
      <div class="ap__sk-row ap__sk-row--sm"></div>
    </div>

    <!-- 数据内容 -->
    <template v-if="!loading && dashboard">
      <!-- 诊断 Banner -->
      <DiagnosticBanner
        :grand-total="dashboard.grand_total"
        :degraded="dashboard.degraded"
        style="margin-bottom:12px"
      />

      <!-- 转化漏斗 -->
      <div class="ap__section">
        <div class="ap__section-title">转化漏斗</div>
        <ConversionFunnel :grand-total="dashboard.grand_total" />
      </div>

      <!-- KPI 卡片 -->
      <div class="ap__section">
        <KpiCards :grand-total="dashboard.grand_total" />
      </div>

      <!-- 三 Tab -->
      <div class="ap__section">
        <STabs :items="TABS" :active-key="activeTab" @change="onTabChange" />
        <div class="ap__tab-content">
          <!-- 商品表现 -->
          <div v-if="activeTab === 'product'">
            <ProductTable :rows="dashboard.rows || []" @open-draft="onOpenDraft" />
          </div>
          <!-- 流量趋势 -->
          <div v-else-if="activeTab === 'traffic'">
            <div v-if="loading" class="ap__tab-loading">加载中…</div>
            <div v-else-if="!traffic" class="ap__tab-empty">切换到此 Tab 后自动加载</div>
            <TrafficTrend v-else :rows="traffic.rows || []" />
          </div>
          <!-- 搜索词洞察 -->
          <div v-else-if="activeTab === 'keyword'">
            <div v-if="loading" class="ap__tab-loading">加载中…</div>
            <div v-else-if="!keywords" class="ap__tab-empty">切换到此 Tab 后自动加载</div>
            <KeywordInsight v-else :by-sku="keywords.by_sku || {}" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
<style scoped>
.analytics-page { padding: var(--sp-5); max-width: 1200px; }
.ap__header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: var(--sp-4); margin-bottom: var(--sp-5); }
.ap__title-row { }
.ap__title { font-size: var(--fs-2xl); font-weight: 700; color: var(--c-text); margin: 0 0 4px; }
.ap__note { font-size: var(--fs-xs); color: var(--c-text-4); }
.ap__controls { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
.ap__select { border: 1px solid var(--c-border); border-radius: var(--r-sm); padding: 6px 10px; font-size: var(--fs-sm); color: var(--c-text); background: #fff; }
.ap__range-btns { display: flex; border: 1px solid var(--c-border); border-radius: var(--r-sm); overflow: hidden; }
.ap__range-btn { background: #fff; border: none; border-right: 1px solid var(--c-border); padding: 6px 12px; font-size: var(--fs-sm); color: var(--c-text-3); cursor: pointer; }
.ap__range-btn:last-child { border-right: none; }
.ap__range-btn.is-active { background: var(--c-primary); color: #fff; }
.ap__skeleton { display: flex; flex-direction: column; gap: 12px; }
.ap__sk-row { height: 48px; background: var(--c-bg); border-radius: var(--r-md); animation: ap-pulse 1.4s ease-in-out infinite; }
.ap__sk-row--sm { height: 32px; }
@keyframes ap-pulse { 0%,100% { opacity: 1 } 50% { opacity: .5 } }
.ap__section { margin-bottom: var(--sp-5); }
.ap__section-title { font-size: var(--fs-sm); font-weight: 600; color: var(--c-text-3); margin-bottom: var(--sp-3); text-transform: uppercase; letter-spacing: 0.04em; }
.ap__tab-content { padding-top: var(--sp-4); }
.ap__tab-loading { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-4) 0; }
.ap__tab-empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-4) 0; }
</style>
