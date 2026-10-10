<template>
  <div class="fulfillment-view">
    <SSectionHeader title="备货发货（FBS）" subtitle="FBS 订单：采购 → 打单 → 发货">
      <template #actions>
        <el-button type="primary" :loading="pulling" @click="doPull">拉取 Ozon 订单</el-button>
      </template>
    </SSectionHeader>

    <!-- KPI 卡 -->
    <div class="kpi-row">
      <SStatCard label="待采购" :value="kpi.toBuy" hint="采购状态＝待采购" />
      <SStatCard label="待发货" :value="kpi.toShip" hint="已采购、待打单发货" />
      <SStatCard label="今日截单" :value="kpi.dueToday" hint="今天截止发货"
                 :danger="kpi.dueToday > 0" />
      <SStatCard label="今日已发" :value="kpi.shippedToday" hint="本会话今天发货" />
    </div>

    <el-card shadow="never">
      <STabs :items="tabItems" :active-key="activeTab" @change="activeTab = $event" />

      <div v-if="message" class="message">{{ message }}</div>

      <div v-if="!loading && rows.length === 0" class="empty">
        <div class="empty__icon">📭</div>
        <div class="empty__text">{{ emptyText }}</div>
      </div>

      <el-table v-else v-loading="loading" :data="rows" border style="width:100%"
                :row-class-name="rowUrgencyClass">
        <el-table-column prop="posting_number" label="发货单号" width="160" />
        <el-table-column label="商品" min-width="220">
          <template #default="{ row }">
            <div class="prod">
              <div class="prod__title">{{ row.title || '（未知商品）' }}</div>
              <div class="prod__sub">offer: {{ row.offer_id }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="80" align="center">
          <template #default="{ row }">×{{ row.qty }}</template>
        </el-table-column>
        <el-table-column label="截止发货" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.ship_by" :type="shipByTagType(row.ship_by)" size="small">
              {{ fmtShipBy(row.ship_by) }}
            </el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="supplier" label="供应商" width="120" />
        <el-table-column label="采购链接" width="100">
          <template #default="{ row }">
            <a v-if="row.purchase_url" :href="row.purchase_url" target="_blank">链接</a>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="cost_cny" label="成本¥" width="90" align="right" />
        <el-table-column label="采购状态" width="140">
          <template #default="{ row }">
            <el-select
              :model-value="row.purchase_state"
              size="small"
              @change="(val) => changeState(row.id, val)"
            >
              <el-option label="待采购" value="待采购" />
              <el-option label="已下单" value="已下单" />
              <el-option label="已到货" value="已到货" />
              <el-option label="已发货" value="已发货" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="120" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isShipped(row)" size="small" type="primary" @click="doShip(row)">发货</el-button>
            <el-tag v-else size="small" type="success">已发货</el-tag>
            <el-button size="small" @click="openLabel(row)">面单</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'
import SSectionHeader from '../ui/SSectionHeader.vue'
import SStatCard from '../ui/SStatCard.vue'
import STabs from '../ui/STabs.vue'

const store = useAppStore()

// ship_by urgency helpers
// urgency: 'overdue' | 'soon' | 'normal' | 'none'
function shipByUrgency(ship_by) {
  if (!ship_by) return 'none'
  const deadline = new Date(ship_by)
  if (isNaN(deadline.getTime())) return 'none'
  const now = new Date()
  const diffMs = deadline - now
  if (diffMs < 0) return 'overdue'
  if (diffMs < 48 * 60 * 60 * 1000) return 'soon'
  return 'normal'
}

function shipByTagType(ship_by) {
  const u = shipByUrgency(ship_by)
  if (u === 'overdue') return 'danger'
  if (u === 'soon') return 'warning'
  return 'info'
}

function fmtShipBy(ship_by) {
  if (!ship_by) return ''
  const d = new Date(ship_by)
  if (isNaN(d.getTime())) return ship_by
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function rowUrgencyClass({ row }) {
  const u = shipByUrgency(row.ship_by)
  if (u === 'overdue') return 'row-overdue'
  if (u === 'soon') return 'row-soon'
  return ''
}

// ship_by 是否落在「今天」（本地时区按日期判定）
function isDueToday(ship_by) {
  if (!ship_by) return false
  const d = new Date(ship_by)
  if (isNaN(d.getTime())) return false
  const now = new Date()
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate()
}

const procurement = ref([])
const loading = ref(false)
const pulling = ref(false)
const message = ref('')
const activeTab = ref('toBuy')

// 已发货留存：后端拉单默认只含 awaiting_packaging，发货后行不会从列表消失（采购行常驻），
// 但「已发货」这个事实需前端按会话标记。两条来源取并集：
//   1) posting_status 已是 deliver/shipped 等已发状态（后端若拉了已发单）；
//   2) shippedPostings：本会话点过「发货」成功的 posting_number。
const shippedPostings = ref(new Set())
// 今日发货计数（本会话内 doShip 成功累加，刷新归零，仅作当日参考）
const shippedTodayCount = ref(0)

function isShipped(row) {
  if (shippedPostings.value.has(row.posting_number)) return true
  const st = String(row.posting_status || '').toLowerCase()
  return st.includes('deliver') || st.includes('shipped') || st.includes('sent')
}

// 阶段分类：已发货 > 待采购(状态=待采购) > 待发货(其余)
function stageOf(row) {
  if (isShipped(row)) return 'shipped'
  if (row.purchase_state === '待采购') return 'toBuy'
  return 'toShip'
}

const stages = computed(() => {
  const g = { toBuy: [], toShip: [], shipped: [] }
  for (const r of procurement.value) g[stageOf(r)].push(r)
  return g
})

const rows = computed(() => stages.value[activeTab.value] || [])

const tabItems = computed(() => [
  { key: 'toBuy', label: '待采购', count: stages.value.toBuy.length },
  { key: 'toShip', label: '待发货', count: stages.value.toShip.length },
  { key: 'shipped', label: '已发货', count: stages.value.shipped.length },
])

const kpi = computed(() => ({
  toBuy: stages.value.toBuy.length,
  toShip: stages.value.toShip.length,
  // 今日截单：未发货且 ship_by 落在今天
  dueToday: procurement.value.filter(r => !isShipped(r) && isDueToday(r.ship_by)).length,
  shippedToday: shippedTodayCount.value,
}))

const emptyText = computed(() => {
  if (activeTab.value === 'toBuy') return '暂无待采购订单'
  if (activeTab.value === 'toShip') return '暂无待发货订单'
  return '暂无已发货订单'
})

// 默认确认实现：包一层 ElMessageBox.confirm（取消会 reject）。测试里会替换成 resolve(true) 的 spy。
const confirmFn = ref((msg, title) =>
  ElMessageBox.confirm(msg, title || '确认', { type: 'warning' }),
)

async function load() {
  loading.value = true
  try {
    const r = await api.fbsProcurement(store.currentStore)
    procurement.value = r.procurement || []
  } catch (err) {
    message.value = (err && err.message) || String(err)
  } finally {
    loading.value = false
  }
}
// 切店 → 重新拉当前店备货板
watch(() => store.currentStore, load, { immediate: true })

async function doPull() {
  pulling.value = true
  message.value = ''
  try {
    const r = await api.fbsPull('awaiting_packaging', 14, store.currentStore)
    procurement.value = r.procurement || []
    message.value = `已同步 ${r.synced} 个订单，备货板 ${procurement.value.length} 条`
  } catch (err) {
    message.value = (err && err.message) || String(err)
  } finally {
    pulling.value = false
  }
}

async function changeState(id, purchase_state) {
  // 受控下拉（:model-value 单向绑定）：row.purchase_state 是唯一真相，
  // 只在服务端成功后才更新。失败则不动 → 下拉自动回弹到旧值，无需手动回滚。
  try {
    const r = await api.fbsSetState(id, purchase_state, '', store.currentStore)
    procurement.value = r.procurement || []
  } catch (err) {
    // 新数组引用强制 el-table/受控下拉按未变的 row.purchase_state 重渲染 → 视觉回弹到旧值
    procurement.value = [...procurement.value]
    ElMessage.error((err && err.message) || String(err))
  }
}

async function doShip(row) {
  try {
    await confirmFn.value(
      '发货后不可逆，确认发货 ' + row.posting_number + '？',
      '发货',
    )
  } catch {
    return // 用户取消，静默处理
  }
  try {
    await api.fbsShip(row.posting_number, store.currentStore)
    ElMessage.success('发货成功：' + row.posting_number)
    // 本会话标记为已发货，留存进「已发货」tab；累计今日已发
    shippedPostings.value = new Set(shippedPostings.value).add(row.posting_number)
    shippedTodayCount.value += 1
    const r = await api.fbsProcurement(store.currentStore)
    procurement.value = r.procurement || []
  } catch (err) {
    ElMessage.error((err && err.message) || String(err))
  }
}

function openLabel(row) {
  window.open(api.fbsLabelUrl(row.posting_number, store.currentStore))
}

defineExpose({
  procurement, rows, kpi, stages, tabItems, activeTab,
  doPull, changeState, doShip, confirmFn,
  shipByUrgency, shipByTagType, fmtShipBy, rowUrgencyClass,
  isShipped, stageOf, isDueToday, shippedPostings,
})
</script>

<style scoped>
.fulfillment-view { display: flex; flex-direction: column; gap: 16px; }
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--sp-4); }
.message { margin: 12px 0; color: var(--c-text-2); }
.muted { color: var(--c-text-3); }
.prod__title { color: var(--c-text); font-weight: 600; line-height: 1.3; }
.prod__sub { font-size: var(--fs-xs); color: var(--c-text-3); margin-top: 2px; }
.empty { padding: 48px 0; text-align: center; color: var(--c-text-3); }
.empty__icon { font-size: 40px; line-height: 1; }
.empty__text { margin-top: 12px; font-size: var(--fs-md); }
</style>
<style>
/* 逾期行：浅红背景；临近行：浅橙背景。不用 scoped，el-table row 在 shadow DOM 外 */
.el-table .row-overdue td { background-color: rgba(239,68,68,0.12) !important; }
.el-table .row-soon td { background-color: rgba(245,158,11,0.12) !important; }
</style>
