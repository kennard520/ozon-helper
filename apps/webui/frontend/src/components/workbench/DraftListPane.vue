<template>
  <div class="dlp" :class="{ 'dlp--collapsed': collapsed }">
    <!-- 头部：标题 + 计数 + 刷新 + 折叠 -->
    <div class="dlp-header">
      <span v-if="!collapsed" class="dlp-header__title">
        商品草稿
        <SBadge variant="primary">{{ c.all }}</SBadge>
      </span>
      <div class="dlp-header__ops">
        <SButton v-if="!collapsed" variant="ghost" size="sm" @click="emit('refresh')">刷新</SButton>
        <button class="dlp-collapse-btn" :title="collapsed ? '展开' : '折叠'" @click="collapsed = !collapsed">
          {{ collapsed ? '▶' : '◀' }}
        </button>
      </div>
    </div>

    <!-- 折叠态：只剩缩略图竖条 -->
    <div v-if="collapsed" class="dlp-mini">
      <div
        v-for="row in visibleDrafts"
        :key="row.id"
        class="dlp-mini__card"
        :class="{ 'is-active': selectedId === row.id }"
        :title="row.ozon_title || row.source_title"
        @click="emit('select', row.id)"
      >
        <img v-if="firstImage(row)" :src="firstImage(row)" />
        <span v-else class="dlp-mini__noimg">—</span>
      </div>
    </div>

    <template v-else>
      <!-- 状态筛选 STabs -->
      <div class="dlp-tabs-wrap">
        <STabs
          :items="tabItems"
          :active-key="filter"
          @change="(k) => emit('update:filter', k)"
        />
      </div>

      <!-- 快速过滤 + 全选 -->
      <div class="dlp-tools">
        <el-input v-model="query" size="small" clearable placeholder="快速过滤当前页…" />
        <el-checkbox
          :model-value="allChecked"
          :indeterminate="someChecked"
          @change="toggleAll"
        >全选</el-checkbox>
      </div>

      <!-- 批量工具条 -->
      <div v-if="checked.length" class="dlp-batch">
        <span class="dlp-batch__cnt">已选 {{ checked.length }} 项</span>
        <el-popover trigger="click" :width="240" placement="bottom-start">
          <template #reference>
            <el-button size="small">批量设置</el-button>
          </template>
          <div class="dlp-bpop">
            <div class="dlp-bpop__row">
              <span class="dlp-bpop__label">库存</span>
              <el-input-number v-model="batchStock" :min="0" :controls="false" size="small" style="width:96px" />
              <el-button size="small" type="primary" :disabled="batchStock == null" @click="applyStock">设置</el-button>
            </div>
            <div class="dlp-bpop__row">
              <span class="dlp-bpop__label">仓库</span>
              <el-select v-model="batchWarehouse" size="small" placeholder="选择仓库" style="flex:1" clearable>
                <el-option v-for="w in warehouses" :key="w.warehouse_id" :label="w.name || w.warehouse_id" :value="w.warehouse_id" />
              </el-select>
              <el-button size="small" type="primary" :disabled="batchWarehouse == null" @click="applyWarehouse">设置</el-button>
            </div>
          </div>
        </el-popover>
        <SButton variant="primary" size="sm" @click="emit('batch-publish', checked.map((r) => r.id))">发布</SButton>
        <SButton variant="danger" size="sm" @click="emit('delete', checked)">删除</SButton>
      </div>

      <!-- 卡片列表 -->
      <div class="dlp-cards">
        <div v-if="!visibleDrafts.length" class="dlp-cards__empty">暂无数据</div>
        <div
          v-for="row in visibleDrafts"
          :key="row.id"
          class="dcard"
          :class="{ 'is-active': selectedId === row.id }"
          @click="emit('select', row.id)"
        >
          <el-checkbox
            class="dcard__check"
            :model-value="isChecked(row)"
            @click.stop
            @change="(v) => toggleCheck(row, v)"
          />
          <div class="dcard__thumb">
            <img v-if="firstImage(row)" :src="firstImage(row)" />
            <span v-else class="dcard__noimg">无图</span>
          </div>
          <div class="dcard__body">
            <div class="dcard__title" :title="row.ozon_title || row.source_title">
              {{ row.ozon_title || row.source_title || '未命名草稿' }}
            </div>
            <div class="dcard__sub">
              <SBadge v-if="sourceLabel(row)" :variant="sourceBadgeVariant(row)">{{ sourceLabel(row) }}</SBadge>
              <span class="dcard__id">ID {{ row.id }}</span>
              <a
                v-if="purchaseLink(row)"
                :href="purchaseLink(row)"
                target="_blank"
                rel="noopener"
                class="dcard__buylink"
                @click.stop
              >采购</a>
            </div>
            <div class="dcard__foot">
              <span class="dcard__price">{{ row.price ? '¥' + row.price : '—' }}</span>
              <SBadge :variant="statusVariant(row.status)">{{ statusLabel(row.status) }}</SBadge>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div class="dlp-pager">
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
import { SBadge, SButton, STabs } from '../../ui/index.js'

const props = defineProps({
  drafts:     { type: Array,           default: () => [] },
  counts:     { type: Object,          default: () => ({}) },
  filter:     { type: String,          default: 'all' },
  selectedId: { type: [Number, String], default: null },
  warehouses: { type: Array,           default: () => [] },
  total:      { type: Number,          default: 0 },
  page:       { type: Number,          default: 1 },
  pageSize:   { type: Number,          default: 20 },
})
const emit = defineEmits([
  'select', 'delete', 'update:filter',
  'batch-update', 'batch-publish',
  'page-change', 'size-change', 'refresh',
])

// 状态
const checked       = ref([])
const batchStock    = ref(null)
const batchWarehouse = ref(null)
const collapsed     = ref(false)
const query         = ref('')

// counts 补零
const c = computed(() => ({
  all: 0, invalid: 0, ready: 0, failed: 0, published: 0, ...props.counts,
}))

// STabs 数据
const tabItems = computed(() => [
  { key: 'all',       label: '全部',   count: c.value.all },
  { key: 'invalid',   label: '待完善', count: c.value.invalid },
  { key: 'ready',     label: '待发布', count: c.value.ready },
  { key: 'failed',    label: '失败',   count: c.value.failed },
  { key: 'published', label: '已发布', count: c.value.published },
])

// 快速过滤
const visibleDrafts = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.drafts
  return props.drafts.filter((r) =>
    String(r.ozon_title  || '').toLowerCase().includes(q) ||
    String(r.source_title || '').toLowerCase().includes(q) ||
    String(r.id).includes(q)
  )
})

// 多选
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
  visibleDrafts.value.length > 0 && visibleDrafts.value.every((r) => isChecked(r))
)
const someChecked = computed(() =>
  checked.value.length > 0 && !allChecked.value
)
function toggleAll(v) {
  checked.value = v ? [...visibleDrafts.value] : []
}

// 批量操作
function applyStock() {
  if (batchStock.value == null) return
  emit('batch-update', { ids: checked.value.map((r) => r.id), patch: { stock: Number(batchStock.value) } })
}
function applyWarehouse() {
  if (batchWarehouse.value == null) return
  emit('batch-update', { ids: checked.value.map((r) => r.id), patch: { warehouse_id: Number(batchWarehouse.value) } })
}

// 仓库名
const warehouseMap = computed(() => {
  const m = {}
  for (const w of props.warehouses || []) m[w.warehouse_id] = w.name || String(w.warehouse_id)
  return m
})
function warehouseName(wid) {
  if (wid == null || wid === '') return '-'
  return warehouseMap.value[wid] || `#${wid}`
}

// 图片
function firstImage(row) {
  const imgs = (row.local_images && row.local_images.length ? row.local_images : row.images) || []
  return imgs.filter(Boolean)[0] || ''
}

// 采购链接
function purchaseLink(row) {
  const u = (row.purchase_url || '').trim()
  if (u) return u
  if (row.source_platform === '1688') return (row.source_url || '').trim()
  return ''
}

// 状态标签 + variant
function statusLabel(s) {
  return { draft: '草稿', invalid: '待完善', ready: '待发布', failed: '发布失败', published: '已发布' }[s] || s || '-'
}
function statusVariant(s) {
  if (s === 'ready' || s === 'published') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'invalid') return 'warn'
  return 'neutral'
}

// 来源标签 + variant
function sourceLabel(row) {
  const p = String(row.source_platform || '').toLowerCase()
  const src = String(row.source || '').toLowerCase()
  if (p === 'ozon' || src.startsWith('ozon')) return 'Ozon'
  if (p === 'wb') return 'WB'
  if (p === '1688') return '1688'
  return p ? p.toUpperCase() : ''
}
function sourceBadgeVariant(row) {
  const l = sourceLabel(row)
  if (l === '1688') return 'primary'
  if (l === 'WB') return 'warn'
  return 'info'
}

defineExpose({
  checked, batchStock, batchWarehouse, collapsed, query, visibleDrafts,
  isChecked, toggleCheck, toggleAll, applyStock, applyWarehouse,
  warehouseName, purchaseLink, sourceLabel, firstImage,
})
</script>

<style scoped>
.dlp {
  width: 340px;
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  height: 100%;
  overflow: hidden;
}
.dlp--collapsed { width: 60px; }

/* 头部 */
.dlp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.dlp-header__title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-text-1);
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.dlp-header__ops {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}
.dlp-collapse-btn {
  background: transparent;
  border: none;
  color: var(--c-text-3);
  font-size: var(--fs-sm);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--r-sm);
}
.dlp-collapse-btn:hover { background: var(--c-bg-2); color: var(--c-text-1); }

/* 折叠态 */
.dlp-mini {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2) var(--sp-1);
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.dlp-mini__card {
  width: 44px;
  height: 56px;
  border-radius: var(--r-sm);
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--c-border);
  background: var(--c-bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dlp-mini__card.is-active { border-color: var(--c-primary); }
.dlp-mini__card img { width: 100%; height: 100%; object-fit: cover; }
.dlp-mini__noimg { font-size: var(--fs-xs); color: var(--c-text-4); }

/* tabs */
.dlp-tabs-wrap {
  padding: 0 var(--sp-3);
  flex-shrink: 0;
}

/* 工具栏 */
.dlp-tools {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.dlp-tools .el-input { flex: 1; }

/* 批量条 */
.dlp-batch {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  padding: var(--sp-2) var(--sp-3);
  background: var(--c-primary-50);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.dlp-batch__cnt { font-size: var(--fs-sm); color: var(--c-text-3); margin-right: var(--sp-1); }
.dlp-bpop { display: flex; flex-direction: column; gap: var(--sp-3); }
.dlp-bpop__row { display: flex; align-items: center; gap: var(--sp-2); }
.dlp-bpop__label { font-size: var(--fs-sm); color: var(--c-text-3); width: 32px; flex: 0 0 auto; }

/* 卡片列表 */
.dlp-cards {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2);
}
.dlp-cards__empty {
  color: var(--c-text-4);
  text-align: center;
  padding: 32px 0;
  font-size: var(--fs-sm);
}

/* 草稿卡 */
.dcard {
  position: relative;
  display: flex;
  gap: var(--sp-3);
  align-items: flex-start;
  margin-bottom: var(--sp-2);
  padding: var(--sp-3);
  border-radius: var(--r-md);
  border: 1px solid var(--c-border);
  cursor: pointer;
  transition: all 0.15s;
  overflow: hidden;
}
.dcard:hover {
  background: var(--c-bg-2);
  border-color: var(--c-border-hover, var(--c-border));
}
.dcard.is-active {
  background: var(--c-primary-50);
  border-color: var(--c-primary-200);
}
.dcard.is-active::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--c-primary);
}
.dcard__check { flex: 0 0 auto; margin-top: 2px; }
.dcard__thumb {
  width: 44px;
  height: 58px;
  border-radius: var(--r-sm);
  overflow: hidden;
  flex: 0 0 auto;
  background: var(--c-bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.dcard__thumb img { width: 100%; height: 100%; object-fit: cover; }
.dcard__noimg { font-size: var(--fs-xs); color: var(--c-text-4); }
.dcard__body { flex: 1; min-width: 0; }
.dcard__title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dcard__sub {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
.dcard__id { font-size: var(--fs-xs); color: var(--c-text-4); }
.dcard__buylink {
  font-size: var(--fs-xs);
  color: var(--c-primary);
  text-decoration: none;
}
.dcard__buylink:hover { text-decoration: underline; }
.dcard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--sp-2);
}
.dcard__price {
  font-size: var(--fs-sm);
  color: var(--c-primary);
  font-weight: 700;
  font-family: monospace;
}

/* 分页 */
.dlp-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border-top: 1px solid var(--c-border);
  flex-shrink: 0;
}
</style>
