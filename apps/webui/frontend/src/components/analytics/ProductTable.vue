<script setup>
import { ref, computed } from 'vue'
import SBadge from '../../ui/SBadge.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
})

const onlyProblems = ref(false)

// 可排序列：key + 默认初次点击方向
const SORTABLE = ['stock', 'exposure', 'sessions', 'cart', 'ordered_units']
const sortKey = ref('exposure')   // 默认按曝光（后端也是曝光降序）
const sortDir = ref('desc')       // 'desc' | 'asc'

function toggleSort(key) {
  if (!SORTABLE.includes(key)) return
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortKey.value = key
    sortDir.value = 'desc'
  }
}

function sortArrow(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'desc' ? '↓' : '↑'
}

const problemCount = computed(
  () => props.rows.filter(r => r.diagnostics && r.diagnostics.length > 0).length
)

const displayRows = computed(() => {
  let list = props.rows
  if (onlyProblems.value) {
    list = list.filter(r => r.diagnostics && r.diagnostics.length > 0)
  }
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...list].sort((a, b) => ((a[key] || 0) - (b[key] || 0)) * dir)
})

// 诊断标签 → 更具体的「带操作建议」文案
function diagText(tag) {
  if (tag === '缺货') return '缺货·补库存'
  if (tag === '0曝光') return '0曝光·优化标题/广告'
  if (tag.includes('高曝光')) return '页面0转化·查价/主图/评价'
  if (tag.includes('加购')) return '加购未转化·查运费'
  return tag
}

function badgeVariant(tag) {
  if (tag === '缺货') return 'danger'
  if (tag === '0曝光') return 'neutral'
  if (tag.includes('高曝光')) return 'warn'
  if (tag.includes('加购')) return 'info'
  return 'neutral'
}

function fmt(v) {
  if (v == null) return '—'
  return v
}
// ₽ 价格
function fmtRub(v) {
  if (v == null) return null
  return '₽' + Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}
function productUrl(row) {
  const url = row?.product_url || row?.productUrl || ''
  return typeof url === 'string' && /^https?:\/\//.test(url) ? url : ''
}
</script>
<template>
  <div class="pt">
    <div class="pt__toolbar">
      <button
        type="button"
        class="pt__problem-btn"
        :class="{ 'is-active': onlyProblems }"
        @click="onlyProblems = !onlyProblems"
      >
        仅看问题商品（{{ problemCount }}）
      </button>
      <span class="pt__hint">有商品链接时，点击商品名称打开 Ozon 详情</span>
      <span class="pt__count">{{ displayRows.length }} / {{ rows.length }} 商品</span>
    </div>
    <div class="pt__wrap">
      <table class="pt__table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>商品名</th>
            <th>价格</th>
            <th class="pt__th-sort" @click="toggleSort('stock')">库存 <span class="pt__arrow">{{ sortArrow('stock') }}</span></th>
            <th class="pt__th-sort" @click="toggleSort('exposure')">曝光 <span class="pt__arrow">{{ sortArrow('exposure') }}</span></th>
            <th class="pt__th-sort" @click="toggleSort('sessions')">访问 <span class="pt__arrow">{{ sortArrow('sessions') }}</span></th>
            <th class="pt__th-sort" @click="toggleSort('cart')">加购 <span class="pt__arrow">{{ sortArrow('cart') }}</span></th>
            <th class="pt__th-sort" @click="toggleSort('ordered_units')">下单 <span class="pt__arrow">{{ sortArrow('ordered_units') }}</span></th>
            <th>转化率</th>
            <th>收入</th>
            <th>诊断</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.sku" class="pt__row">
            <td class="pt__sku">{{ row.sku }}</td>
            <td class="pt__title">
              <a
                v-if="productUrl(row)"
                class="pt__title-link"
                :href="productUrl(row)"
                target="_blank"
                rel="noopener"
              >{{ row.title || '—' }}</a>
              <span v-else>{{ row.title || '—' }}</span>
            </td>
            <td class="pt__price">
              <span class="pt__price-now">{{ fmtRub(row.price) || '—' }}</span>
              <span
                v-if="row.price_action && row.price && Number(row.price_action) > Number(row.price)"
                class="pt__price-old"
              >{{ fmtRub(row.price_action) }}</span>
            </td>
            <td :class="{ 'pt__val--danger': row.stock === 0 }">{{ fmt(row.stock) }}</td>
            <td>{{ fmt(row.exposure) }}</td>
            <td>{{ fmt(row.sessions) }}</td>
            <td>{{ fmt(row.cart) }}</td>
            <td>{{ fmt(row.ordered_units) }}</td>
            <td>{{ row.conv_cart_pct != null ? row.conv_cart_pct + '%' : '—' }}</td>
            <td>{{ fmtRub(row.revenue) || '—' }}</td>
            <td class="pt__tags">
              <SBadge
                v-for="tag in (row.diagnostics || [])"
                :key="tag"
                :variant="badgeVariant(tag)"
                style="margin-right:4px"
              >{{ diagText(tag) }}</SBadge>
              <SBadge v-if="!row.diagnostics || row.diagnostics.length === 0" variant="success">正常</SBadge>
            </td>
          </tr>
          <tr v-if="displayRows.length === 0">
            <td colspan="11" class="pt__empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<style scoped>
.pt { }
.pt__toolbar { display: flex; align-items: center; gap: var(--sp-4); padding: var(--sp-3) 0; font-size: var(--fs-sm); }
.pt__problem-btn { background: #fff; border: 1px solid var(--c-border); border-radius: var(--r-sm); padding: 5px 12px; font-size: var(--fs-sm); color: var(--c-text-2); cursor: pointer; transition: .15s; }
.pt__problem-btn:hover { border-color: var(--c-primary-200); color: var(--c-primary); }
.pt__problem-btn.is-active { background: var(--c-primary); border-color: var(--c-primary); color: #fff; }
.pt__hint { color: var(--c-text-4); font-size: var(--fs-xs); }
.pt__count { color: var(--c-text-4); margin-left: auto; }
.pt__wrap { overflow-x: auto; }
.pt__table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.pt__table th { background: var(--c-bg); color: var(--c-text-3); font-weight: 600; padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.pt__th-sort { cursor: pointer; user-select: none; }
.pt__th-sort:hover { color: var(--c-primary); }
.pt__arrow { color: var(--c-primary); font-weight: 700; }
.pt__table td { padding: 8px 10px; border-bottom: 1px solid var(--c-border-light, var(--c-border)); color: var(--c-text-2); }
.pt__row:hover td { background: var(--c-bg); }
.pt__sku { color: var(--c-text-4); font-size: var(--fs-xs); }
.pt__title { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-text); }
.pt__title-link { color: var(--c-primary); text-decoration: none; font-weight: 600; }
.pt__title-link:hover { text-decoration: underline; }
.pt__price { white-space: nowrap; }
.pt__price-now { color: var(--c-success); font-weight: 600; }
.pt__price-old { color: var(--c-text-4); text-decoration: line-through; margin-left: 6px; font-size: var(--fs-xs); }
.pt__val--danger { color: var(--c-danger); }
.pt__tags { white-space: nowrap; }
.pt__empty { text-align: center; color: var(--c-text-4); padding: 24px; }
</style>
