<template>
  <div class="fulfillment-view">
    <el-card shadow="never">
      <template #header>
        <div class="card-title">
          <strong>备货发货（FBS）</strong>
          <el-button type="primary" :loading="pulling" @click="doPull">拉取 Ozon 订单</el-button>
        </div>
      </template>
      <div v-if="message" class="message">{{ message }}</div>
      <el-table v-loading="loading" :data="procurement" border style="width:100%"
                :row-class-name="rowUrgencyClass">
        <el-table-column prop="posting_number" label="发货单号" width="160" />
        <el-table-column prop="offer_id" label="商品 ID" width="140" />
        <el-table-column prop="qty" label="数量" width="70" align="center" />
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
            <el-button size="small" type="primary" @click="doShip(row)">发货</el-button>
            <el-button size="small" @click="openLabel(row)">面单</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'

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

const procurement = ref([])
const loading = ref(false)
const pulling = ref(false)
const message = ref('')

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
    const r = await api.fbsProcurement(store.currentStore)
    procurement.value = r.procurement || []
  } catch (err) {
    ElMessage.error((err && err.message) || String(err))
  }
}

function openLabel(row) {
  window.open(api.fbsLabelUrl(row.posting_number, store.currentStore))
}

defineExpose({ procurement, doPull, changeState, doShip, confirmFn, shipByUrgency, shipByTagType, fmtShipBy, rowUrgencyClass })
</script>

<style scoped>
.fulfillment-view { display: flex; flex-direction: column; gap: 16px; }
.card-title { display: flex; justify-content: space-between; align-items: center; }
.message { margin-bottom: 12px; color: var(--c-text-2); }
.muted { color: var(--c-text-3); }
</style>
<style>
/* 逾期行：浅红背景；临近行：浅橙背景。不用 scoped，el-table row 在 shadow DOM 外 */
.el-table .row-overdue td { background-color: rgba(239,68,68,0.12) !important; }
.el-table .row-soon td { background-color: rgba(245,158,11,0.12) !important; }
</style>
