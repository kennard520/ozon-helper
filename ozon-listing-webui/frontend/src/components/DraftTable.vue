<template>
  <div class="draft-table" :class="{ collapsed }">
    <!-- 列表头：标题 + 计数 + 刷新 + 折叠 -->
    <div class="list-header">
      <span v-if="!collapsed" class="list-title">
        商品草稿
        <span class="count-badge">{{ c.all }}</span>
      </span>
      <div class="list-header-ops">
        <el-button v-if="!collapsed" link size="small" @click="emit('refresh')">刷新</el-button>
        <button class="collapse-btn" :title="collapsed ? '展开' : '折叠'" @click="collapsed = !collapsed">
          {{ collapsed ? '▶' : '◀' }}
        </button>
      </div>
    </div>

    <!-- 折叠态：只剩缩略图竖条 -->
    <div v-if="collapsed" class="mini-list">
      <div
        v-for="row in visibleDrafts"
        :key="row.id"
        class="mini-card"
        :class="{ active: selectedId === row.id }"
        :title="row.ozon_title || row.source_title"
        @click="emit('select', row.id)"
      >
        <img v-if="firstImage(row)" :src="firstImage(row)" />
        <span v-else class="mini-noimg">—</span>
      </div>
    </div>

    <template v-else>
      <!-- 状态筛选 -->
      <el-tabs :model-value="filter" class="status-tabs" @tab-change="(k) => emit('update:filter', k)">
        <el-tab-pane :label="`全部 ${c.all}`" name="all" />
        <el-tab-pane :label="`待完善 ${c.invalid}`" name="invalid" />
        <el-tab-pane :label="`待发布 ${c.ready}`" name="ready" />
        <el-tab-pane :label="`失败 ${c.failed}`" name="failed" />
        <el-tab-pane :label="`已发布 ${c.published}`" name="published" />
      </el-tabs>

      <!-- 快速过滤 + 全选 -->
      <div class="list-tools">
        <el-input v-model="query" size="small" clearable placeholder="快速过滤当前页…" />
        <el-checkbox
          :model-value="allChecked"
          :indeterminate="someChecked"
          @change="toggleAll"
        >全选</el-checkbox>
      </div>

      <!-- 批量工具条：紧凑单行，库存/仓库设置收进弹出层，避免窄列里堆成多行 -->
      <div v-if="checked.length" class="batch-bar">
        <span class="batch-count">已选 {{ checked.length }} 项</span>
        <el-popover trigger="click" :width="240" placement="bottom-start">
          <template #reference>
            <el-button size="small">批量设置</el-button>
          </template>
          <div class="batch-pop">
            <div class="bp-row">
              <span class="bp-label">库存</span>
              <el-input-number v-model="batchStock" :min="0" :controls="false" size="small" style="width:96px" />
              <el-button size="small" type="primary" :disabled="batchStock == null" @click="applyStock">设置</el-button>
            </div>
            <div class="bp-row">
              <span class="bp-label">仓库</span>
              <el-select v-model="batchWarehouse" size="small" placeholder="选择仓库" style="flex:1" clearable>
                <el-option v-for="w in warehouses" :key="w.warehouse_id" :label="w.name || w.warehouse_id" :value="w.warehouse_id" />
              </el-select>
              <el-button size="small" type="primary" :disabled="batchWarehouse == null" @click="applyWarehouse">设置</el-button>
            </div>
          </div>
        </el-popover>
        <el-button type="success" size="small" @click="emit('batch-publish', checked.map((r) => r.id))">发布</el-button>
        <el-button type="danger" plain size="small" @click="emit('delete', checked)">删除</el-button>
      </div>

      <!-- 卡片列表 -->
      <div class="cards">
        <div v-if="!visibleDrafts.length" class="cards-empty">暂无数据</div>
        <div
          v-for="row in visibleDrafts"
          :key="row.id"
          class="dcard"
          :class="{ active: selectedId === row.id }"
          @click="emit('select', row.id)"
        >
          <el-checkbox
            class="dcard-check"
            :model-value="isChecked(row)"
            @click.stop
            @change="(v) => toggleCheck(row, v)"
          />
          <div class="dcard-thumb">
            <img v-if="firstImage(row)" :src="firstImage(row)" />
            <span v-else class="dcard-noimg">无图</span>
          </div>
          <div class="dcard-body">
            <div class="dcard-title" :title="row.ozon_title || row.source_title">{{ row.ozon_title || row.source_title || '未命名草稿' }}</div>
            <div class="dcard-sub">
              <el-tag v-if="sourceLabel(row)" :type="sourceTagType(row)" size="small" effect="dark">{{ sourceLabel(row) }}</el-tag>
              <span class="dcard-id">ID {{ row.id }}</span>
              <a
                v-if="purchaseLink(row)"
                :href="purchaseLink(row)"
                target="_blank"
                rel="noopener"
                class="buy-link"
                @click.stop
              >采购</a>
            </div>
            <div class="dcard-foot">
              <span class="dcard-price">{{ row.price ? '¥' + row.price : '—' }}</span>
              <el-tag :type="tagType(row.status)" size="small" effect="plain">{{ statusLabel(row.status) }}</el-tag>
            </div>
          </div>
        </div>
      </div>

      <div class="pager">
        <el-pagination
          background
          small
          layout="prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          @current-change="(p) => emit('page-change', p)"
        />
        <el-select
          :model-value="pageSize"
          size="small"
          style="width:96px"
          @change="(s) => emit('size-change', s)"
        >
          <el-option v-for="s in [10, 20, 50, 100]" :key="s" :label="`${s}/页`" :value="s" />
        </el-select>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  drafts: { type: Array, default: () => [] },
  counts: { type: Object, default: () => ({}) },
  filter: { type: String, default: 'all' },
  selectedId: { type: [Number, String], default: null },
  warehouses: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
})
const emit = defineEmits(['select', 'delete', 'update:filter', 'batch-update', 'batch-publish', 'page-change', 'size-change', 'refresh'])

const checked = ref([])
const batchStock = ref(null)
const batchWarehouse = ref(null)
const collapsed = ref(false)
const query = ref('')

const c = computed(() => ({
  all: 0, invalid: 0, ready: 0, failed: 0, published: 0, ...props.counts,
}))

const visibleDrafts = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.drafts
  return props.drafts.filter((r) =>
    String(r.ozon_title || '').toLowerCase().includes(q) ||
    String(r.source_title || '').toLowerCase().includes(q) ||
    String(r.id).includes(q))
})

// 批量选择（卡片模式自管，替代旧 el-table 的 selection）
function isChecked(row) {
  return checked.value.some((r) => r.id === row.id)
}
function toggleCheck(row, v) {
  if (v) {
    if (!isChecked(row)) checked.value = [...checked.value, row]
  } else {
    checked.value = checked.value.filter((r) => r.id !== row.id)
  }
}
const allChecked = computed(() =>
  visibleDrafts.value.length > 0 && visibleDrafts.value.every((r) => isChecked(r)))
const someChecked = computed(() =>
  checked.value.length > 0 && !allChecked.value)
function toggleAll(v) {
  checked.value = v ? [...visibleDrafts.value] : []
}

const warehouseMap = computed(() => {
  const m = {}
  for (const w of props.warehouses || []) m[w.warehouse_id] = w.name || String(w.warehouse_id)
  return m
})
function warehouseName(wid) {
  if (wid == null || wid === '') return '-'
  return warehouseMap.value[wid] || `#${wid}`
}

function firstImage(row) {
  const imgs = (row.local_images && row.local_images.length ? row.local_images : row.images) || []
  return imgs.filter(Boolean)[0] || ''
}

// 采购链接：优先 purchase_url，其次 1688 来源链接（Ozon 商品通常无采购链接）
function purchaseLink(row) {
  const u = (row.purchase_url || '').trim()
  if (u) return u
  if (row.source_platform === '1688') return (row.source_url || '').trim()
  return ''
}

function applyStock() {
  if (batchStock.value == null) return
  emit('batch-update', { ids: checked.value.map((r) => r.id), patch: { stock: Number(batchStock.value) } })
}
function applyWarehouse() {
  if (batchWarehouse.value == null) return
  emit('batch-update', { ids: checked.value.map((r) => r.id), patch: { warehouse_id: Number(batchWarehouse.value) } })
}

function statusLabel(s) {
  return { draft: '草稿', invalid: '待完善', ready: '待发布', failed: '发布失败', published: '已发布' }[s] || s || '-'
}
function tagType(s) {
  if (s === 'ready' || s === 'published') return 'success'
  if (s === 'failed') return 'danger'
  return 'warning'
}
// 来源标签：以 source_platform(插件采集可靠设置) 为准，兼容旧的 source=ozon_*
function sourceLabel(row) {
  const p = String(row.source_platform || '').toLowerCase()
  const src = String(row.source || '').toLowerCase()
  if (p === 'ozon' || src.startsWith('ozon')) return 'Ozon'
  if (p === 'wb') return 'WB'
  if (p === '1688') return '1688'
  return p ? p.toUpperCase() : ''
}
function sourceTagType(row) {
  const l = sourceLabel(row)
  return l === 'Ozon' ? 'primary' : (l === 'WB' ? 'warning' : 'info')
}

defineExpose({ checked, batchStock, batchWarehouse, collapsed, query, visibleDrafts, isChecked, toggleCheck, toggleAll, applyStock, applyWarehouse, warehouseName, purchaseLink, sourceLabel, firstImage })
</script>

<style scoped>
.draft-table {
  width: 340px;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  max-height: calc(100vh - 130px);
}
.draft-table.collapsed { width: 60px; }

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--gp-line-soft);
}
.list-title { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.count-badge {
  background: rgba(139, 92, 246, 0.2);
  color: var(--gp-purple-soft);
  font-size: 10px;
  font-family: monospace;
  padding: 2px 8px;
  border-radius: 99px;
}
.list-header-ops { display: flex; align-items: center; gap: 4px; }
.collapse-btn {
  background: transparent;
  border: none;
  color: var(--gp-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
}
.collapse-btn:hover { background: rgba(0, 0, 0, 0.06); color: var(--c-text); }

.list-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--gp-line-soft);
}
.list-tools .el-input { flex: 1; }

.status-tabs { padding: 0 8px; }
:deep(.status-tabs .el-tabs__header) { margin: 0; }
:deep(.status-tabs .el-tabs__item) { padding: 0 10px; font-size: 12px; }
:deep(.status-tabs .el-tabs__nav-wrap::after) { display: none; }

.batch-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: rgba(139, 92, 246, 0.08);
  border-bottom: 1px solid var(--gp-line-soft);
}
.batch-count { font-size: 12px; color: var(--gp-muted); margin-right: 2px; }
.batch-pop { display: flex; flex-direction: column; gap: 10px; }
.bp-row { display: flex; align-items: center; gap: 8px; }
.bp-label { font-size: 12px; color: var(--gp-muted); width: 32px; flex: 0 0 auto; }

.cards { flex: 1; overflow-y: auto; padding: 8px; }
.cards-empty { color: var(--gp-faint); text-align: center; padding: 32px 0; font-size: 13px; }

.dcard {
  position: relative;
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 8px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  cursor: pointer;
  transition: all 0.2s;
  overflow: hidden;
}
.dcard:hover { background: rgba(0, 0, 0, 0.03); border-color: rgba(0, 0, 0, 0.1); }
.dcard.active { background: rgba(139, 92, 246, 0.1); border-color: rgba(139, 92, 246, 0.5); }
.dcard.active::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--gp-purple);
}
.dcard-check { flex: 0 0 auto; margin-top: 2px; }
.dcard-thumb {
  width: 44px; height: 58px;
  border-radius: 6px;
  overflow: hidden;
  flex: 0 0 auto;
  background: rgba(0, 0, 0, 0.04);
  display: flex; align-items: center; justify-content: center;
}
.dcard-thumb img { width: 100%; height: 100%; object-fit: cover; }
.dcard-noimg { font-size: 10px; color: var(--gp-dim); }
.dcard-body { flex: 1; min-width: 0; }
.dcard-title {
  font-size: 12px; font-weight: 600; color: var(--gp-text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dcard-sub { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.dcard-id { font-size: 10px; color: var(--gp-faint); }
.buy-link { font-size: 10px; color: var(--gp-purple-soft); text-decoration: none; }
.buy-link:hover { text-decoration: underline; }
.dcard-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
.dcard-price { font-size: 12px; color: var(--gp-purple-soft); font-weight: bold; font-family: monospace; }

.mini-list { flex: 1; overflow-y: auto; padding: 8px 6px; display: flex; flex-direction: column; gap: 6px; }
.mini-card {
  width: 44px; height: 56px; border-radius: 6px; overflow: hidden; cursor: pointer;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: rgba(0, 0, 0, 0.04);
  display: flex; align-items: center; justify-content: center;
}
.mini-card.active { border-color: var(--gp-purple); }
.mini-card img { width: 100%; height: 100%; object-fit: cover; }
.mini-noimg { font-size: 10px; color: var(--gp-dim); }

.pager {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--gp-line-soft);
}
</style>
