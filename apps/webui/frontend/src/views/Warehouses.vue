<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'
import {
  SButton, SBadge, SCard, SStatCard, SSectionHeader,
} from '../ui/index.js'

const store = useAppStore()
const warehouses = ref([])
const loading = ref(false)
const syncing = ref(false)
const expanded = ref({})
const showArchived = ref(false)

function isArchived(w) {
  const status = String(w && w.status || '').toLowerCase()
  return status.includes('archive')
}

function isActive(w) {
  return String(w && w.status || '').toLowerCase() === 'created'
}

function deliveryMethodsOf(w) {
  const out = []
  const seen = new Set()
  for (const dm of (w.delivery_methods || [])) {
    const key = dm.delivery_method_id ?? dm.id ?? `${dm.warehouse_id || ''}:${dm.name || ''}:${dm.dropoff_code || ''}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(dm)
  }
  return out
}

const visibleWarehouses = computed(() => warehouses.value.filter(w => showArchived.value || !isArchived(w)))
const total = computed(() => visibleWarehouses.value.length)
const archivedCount = computed(() => warehouses.value.filter(isArchived).length)
const activeCount = computed(() => visibleWarehouses.value.filter(isActive).length)
const rfbsCount = computed(() => visibleWarehouses.value.filter(w => w.is_rfbs).length)

async function load() {
  loading.value = true
  try {
    const r = await api.listWarehouses(store.currentStore)
    warehouses.value = r.warehouses || []
  } catch (e) {
    ElMessage.error(e.message || '加载仓库失败')
  } finally {
    loading.value = false
  }
}
watch(() => store.currentStore, load, { immediate: true })

async function doSync() {
  syncing.value = true
  try {
    const r = await api.syncWarehouses(store.currentStore)
    warehouses.value = r.warehouses || []
    ElMessage.success(`同步成功，共 ${r.synced ?? 0} 个仓库 / ${r.delivery_methods ?? 0} 个配送方式`)
  } catch (e) {
    ElMessage.error(e.message || '同步失败')
  } finally {
    syncing.value = false
  }
}

async function makeDefault(wid) {
  try {
    const r = await api.setDefaultWarehouse(wid, store.currentStore)
    warehouses.value = r.warehouses || []
  } catch (e) {
    ElMessage.error(e.message || '设置默认仓库失败')
  }
}

function toggleExpand(wid) {
  expanded.value = { ...expanded.value, [wid]: !expanded.value[wid] }
}

function statusVariant(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'created') return 'success'
  if (s.includes('archive') || s === 'disabled') return 'neutral'
  return 'warn'
}

function statusLabel(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'created') return '启用'
  if (s.includes('archive')) return '已归档'
  if (s === 'disabled') return '停用'
  if (!s) return '未知'
  return status
}

function fmtFetchedAt(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

defineExpose({ warehouses, visibleWarehouses, doSync, makeDefault, fmtFetchedAt, deliveryMethodsOf })
</script>

<template>
  <div class="wh-page" v-loading="loading">
    <SSectionHeader
      title="仓库"
      subtitle="仅当前店铺，从 Ozon 同步 FBS / realFBS 仓库与配送方式。默认隐藏已归档仓库。"
    >
      <template #actions>
        <SButton variant="ghost" size="sm" @click="showArchived = !showArchived">
          {{ showArchived ? '隐藏归档' : `显示归档${archivedCount ? ` (${archivedCount})` : ''}` }}
        </SButton>
        <SButton variant="primary" size="sm" :loading="syncing" @click="doSync">
          从 Ozon 同步仓库
        </SButton>
      </template>
    </SSectionHeader>

    <div class="wh-stats">
      <SStatCard label="启用仓库" :value="`${activeCount} / ${total}`" hint="当前显示范围内状态为 created 的仓库数" />
      <SStatCard label="realFBS 仓库" :value="rfbsCount" hint="支持卖家自配送的 rFBS 仓库数" />
      <SStatCard label="已归档" :value="archivedCount" hint="默认隐藏，可在右上角显示" />
    </div>

    <div v-if="!loading && !visibleWarehouses.length" class="wh-empty">
      <div class="wh-empty__icon">仓</div>
      <div class="wh-empty__text">{{ archivedCount && !showArchived ? '只剩已归档仓库' : '该店铺暂无仓库' }}</div>
      <div class="wh-empty__hint">点击右上角同步仓库，或显示已归档仓库查看历史数据。</div>
    </div>

    <div v-else class="wh-grid">
      <SCard
        v-for="w in visibleWarehouses"
        :key="w.warehouse_id"
        padding="0"
        class="wh-card"
        :class="{ 'is-inactive': !isActive(w), 'is-archived': isArchived(w) }"
      >
        <template #header>
          <div class="wh-card-head">
            <div class="wh-card-icon">仓</div>
            <div class="wh-card-info">
              <div class="wh-card-name" :title="w.name">{{ w.name }}</div>
              <div class="wh-card-id">仓库 ID: {{ w.warehouse_id }}</div>
            </div>
            <div class="wh-card-badges">
              <SBadge :variant="w.is_rfbs ? 'warn' : 'info'">{{ w.is_rfbs ? 'realFBS' : 'FBS' }}</SBadge>
              <SBadge :variant="statusVariant(w.status)">
                <span class="wh-dot" :class="isActive(w) ? 'wh-dot--on' : 'wh-dot--off'"></span>
                {{ statusLabel(w.status) }}
              </SBadge>
            </div>
          </div>
        </template>

        <div class="wh-card-body">
          <label class="wh-default" :class="{ 'is-on': w.is_default, 'is-disabled': isArchived(w) }">
            <input
              type="radio"
              class="wh-default__radio"
              name="wh-default"
              :checked="!!w.is_default"
              :disabled="isArchived(w)"
              @change="makeDefault(w.warehouse_id)"
            >
            <span class="wh-default__text">
              {{ w.is_default ? '默认仓库' : (isArchived(w) ? '归档仓库不可设为默认' : '设为默认仓库') }}
            </span>
            <SBadge v-if="w.is_default" variant="primary">默认</SBadge>
          </label>

          <div class="wh-meta-row">
            <span class="wh-meta-label">上次同步</span>
            <span v-if="w.fetched_at" class="wh-meta-value">{{ fmtFetchedAt(w.fetched_at) }}</span>
            <span v-else class="wh-meta-value wh-meta-empty">—</span>
          </div>

          <div class="wh-dm">
            <button class="wh-dm__toggle" type="button" @click="toggleExpand(w.warehouse_id)">
              <span class="wh-dm__caret" :class="{ 'is-open': expanded[w.warehouse_id] }">›</span>
              配送方式（{{ deliveryMethodsOf(w).length }}）
            </button>

            <div v-if="expanded[w.warehouse_id]" class="wh-dm__panel">
              <div v-if="deliveryMethodsOf(w).length" class="wh-dm__list">
                <div
                  v-for="dm in deliveryMethodsOf(w)"
                  :key="dm.delivery_method_id ?? dm.id"
                  class="wh-dm__item"
                >
                  <div class="wh-dm__item-head">
                    <span class="wh-dm__name" :title="dm.name">{{ dm.name || '未命名配送方式' }}</span>
                    <SBadge v-if="dm.is_express" variant="success">express</SBadge>
                    <span v-if="dm.status" class="wh-dm__status">{{ dm.status }}</span>
                  </div>
                  <div class="wh-dm__fields">
                    <span v-if="dm.tpl_integration_type" class="wh-dm__field">集成类型：{{ dm.tpl_integration_type }}</span>
                    <span v-if="dm.cutoff" class="wh-dm__field">截单：{{ dm.cutoff }}</span>
                    <span v-if="dm.provider_id" class="wh-dm__field">承运商：{{ dm.provider_id }}</span>
                    <span v-if="dm.dropoff_name" class="wh-dm__field">自提点：{{ dm.dropoff_name }}</span>
                    <span v-if="dm.dropoff_code" class="wh-dm__field">编码：{{ dm.dropoff_code }}</span>
                  </div>
                  <div v-if="dm.dropoff_address" class="wh-dm__addr">
                    {{ dm.dropoff_address }}
                    <span v-if="dm.dropoff_lat != null && dm.dropoff_lng != null" class="wh-dm__coord">
                      （{{ dm.dropoff_lat }}, {{ dm.dropoff_lng }}）
                    </span>
                  </div>
                </div>
              </div>
              <div v-else class="wh-dm__empty">该仓库暂无配送方式</div>
            </div>
          </div>
        </div>
      </SCard>
    </div>
  </div>
</template>

<style scoped>
.wh-page{padding:var(--sp-6);max-width:1200px}
.wh-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--sp-4);margin-bottom:var(--sp-5);max-width:840px}
.wh-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:var(--sp-4)}
.wh-card.is-inactive{opacity:.72}
.wh-card.is-archived{filter:saturate(.75)}
.wh-card-head{display:flex;align-items:center;gap:var(--sp-3)}
.wh-card-icon{width:40px;height:40px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;border-radius:var(--r-md);background:var(--c-primary-100);color:var(--c-primary)}
.wh-card-info{flex:1;min-width:0}
.wh-card-name{font-weight:700;color:var(--c-text);font-size:var(--fs-md);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wh-card-id{font-size:var(--fs-xs);color:var(--c-text-3);margin-top:2px}
.wh-card-badges{display:flex;align-items:center;gap:6px;flex-shrink:0}
.wh-dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.wh-dot--on{background:var(--c-success)}
.wh-dot--off{background:var(--c-text-4)}
.wh-card-body{padding:var(--sp-4) var(--sp-5)}
.wh-default{display:flex;align-items:center;gap:var(--sp-2);padding:var(--sp-3);border:1px solid var(--c-border);border-radius:var(--r-sm);cursor:pointer;margin-bottom:var(--sp-3);transition:.15s}
.wh-default:hover{border-color:var(--c-primary-200)}
.wh-default.is-on{border-color:var(--c-primary);background:var(--c-primary-50)}
.wh-default.is-disabled{cursor:not-allowed;background:var(--c-bg)}
.wh-default__radio{accent-color:var(--c-primary);cursor:pointer;margin:0}
.wh-default__radio:disabled{cursor:not-allowed}
.wh-default__text{flex:1;font-size:var(--fs-sm);color:var(--c-text-2)}
.wh-default.is-on .wh-default__text{color:var(--c-primary);font-weight:600}
.wh-meta-row{display:flex;align-items:center;gap:var(--sp-3);margin-bottom:var(--sp-3)}
.wh-meta-label{font-size:var(--fs-xs);color:var(--c-text-3);min-width:56px}
.wh-meta-value{font-size:var(--fs-sm);color:var(--c-text-2)}
.wh-meta-empty{color:var(--c-text-4)}
.wh-dm{border-top:1px solid var(--c-border);padding-top:var(--sp-3)}
.wh-dm__toggle{display:inline-flex;align-items:center;gap:6px;background:none;border:none;padding:0;cursor:pointer;font-size:var(--fs-sm);font-weight:600;color:var(--c-text-2)}
.wh-dm__toggle:hover{color:var(--c-primary)}
.wh-dm__caret{display:inline-block;transition:transform .15s;color:var(--c-text-3);font-size:16px}
.wh-dm__caret.is-open{transform:rotate(90deg)}
.wh-dm__panel{margin-top:var(--sp-3)}
.wh-dm__list{display:flex;flex-direction:column;gap:var(--sp-2)}
.wh-dm__item{background:var(--c-bg-2);border:1px solid var(--c-border);border-radius:var(--r-sm);padding:var(--sp-2) var(--sp-3)}
.wh-dm__item-head{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.wh-dm__name{font-size:var(--fs-sm);font-weight:600;color:var(--c-text)}
.wh-dm__status{font-size:var(--fs-xs);color:var(--c-text-3)}
.wh-dm__fields{display:flex;flex-wrap:wrap;gap:4px var(--sp-3);margin-top:4px}
.wh-dm__field,.wh-dm__addr{font-size:var(--fs-xs);color:var(--c-text-3)}
.wh-dm__addr{margin-top:4px}
.wh-dm__coord{color:var(--c-text-4)}
.wh-dm__empty{font-size:var(--fs-sm);color:var(--c-text-4)}
.wh-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:var(--sp-2);padding:var(--sp-6);border:2px dashed var(--c-border);border-radius:var(--r-lg);text-align:center}
.wh-empty__icon{font-size:24px;font-weight:700;color:var(--c-text-4)}
.wh-empty__text{font-size:var(--fs-md);font-weight:600;color:var(--c-text-3)}
.wh-empty__hint{font-size:var(--fs-xs);color:var(--c-text-4)}
@media (max-width:800px){
  .wh-page{padding:var(--sp-4)}
  .wh-stats,.wh-grid{grid-template-columns:1fr}
}
</style>
