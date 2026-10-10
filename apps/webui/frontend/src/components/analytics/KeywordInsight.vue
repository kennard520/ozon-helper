<script setup>
import { computed, ref } from 'vue'
import SBadge from '../../ui/SBadge.vue'

const props = defineProps({
  bySku: { type: Object, default: () => ({}) }, // { sku: [{query, searches, ctr, position, orders, gmv}] }
  dateFrom: { type: String, default: '' },
  dateTo: { type: String, default: '' },
  dateAdjusted: { type: Boolean, default: false },
})

const sortState = ref({ key: 'searches', dir: 'desc' })

const rangeLabel = computed(() => {
  if (!props.dateFrom || !props.dateTo) return ''
  return `${props.dateFrom} ~ ${props.dateTo}`
})

const keywordRules = {
  opportunity: '机会词：搜索量高，但是点击率低，searches > 500 && 点击率 < 3%。适合优化标题、主图、价格或首图卖点去抢流量。',
  pollution: '污染词：搜索量高，但是没有订单，searches > 500 && orders === 0。可能是引流不精准，也可能是价格、图片、评价或详情承接不足。',
  covered: '已覆盖：这个词带来了订单，orders > 0。说明这个词已经能成交，重点维护排名、库存和价格。',
  ctr: '点击率：Ozon 字段 view_conversion，表示用户搜索该词后看到商品并点进来的比例。Ozon 返回值已经是百分数，11.18 表示 11.18%。',
  verdict: '判定为本系统按搜索词数据自动计算，不是 Ozon 官方标签。优先级：已覆盖 > 污染词 > 机会词。',
}

const allWords = computed(() => {
  const flat = []
  for (const [sku, words] of Object.entries(props.bySku)) {
    for (const w of words) flat.push({ ...w, sku })
  }
  return flat
})

const opportunity = computed(() => allWords.value.filter(w => w.searches > 500 && Number(w.ctr || 0) < 3))
const pollution = computed(() => allWords.value.filter(w => w.searches > 500 && w.orders === 0))
const covered = computed(() => allWords.value.filter(w => w.orders > 0))

function verdict(w) {
  if (w.orders > 0) return { label: '已覆盖', variant: 'success', rank: 3 }
  if (w.searches > 500 && w.orders === 0) return { label: '污染词', variant: 'warn', rank: 2 }
  if (w.searches > 500 && Number(w.ctr || 0) < 3) return { label: '机会词', variant: 'info', rank: 1 }
  return null
}

function numeric(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function sortValue(w, key) {
  if (key === 'query') return w.query || ''
  if (key === 'sku') return String(w.sku || '')
  if (key === 'verdict') return verdict(w)?.rank || 0
  if (key === 'ctr') return numeric(w.ctr)
  return numeric(w[key])
}

const sortedWords = computed(() => {
  const { key, dir } = sortState.value
  const factor = dir === 'asc' ? 1 : -1
  return [...allWords.value].sort((a, b) => {
    const av = sortValue(a, key)
    const bv = sortValue(b, key)
    if (typeof av === 'string' || typeof bv === 'string') {
      return String(av).localeCompare(String(bv), 'zh-CN') * factor
    }
    return (av - bv) * factor
  })
})

function toggleSort(key) {
  if (sortState.value.key === key) {
    sortState.value = { key, dir: sortState.value.dir === 'asc' ? 'desc' : 'asc' }
    return
  }
  const ascFirst = key === 'query' || key === 'sku'
  sortState.value = { key, dir: ascFirst ? 'asc' : 'desc' }
}

function sortMark(key) {
  if (sortState.value.key !== key) return ''
  return sortState.value.dir === 'asc' ? '↑' : '↓'
}

function fmtPct(v) {
  if (v == null) return '—'
  return `${Number(v).toFixed(2)}%`
}

function fmtRub(v) {
  if (v == null) return '—'
  return '₽' + Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 0 })
}
</script>

<template>
  <div class="ki">
    <div class="ki__title">搜索词洞察</div>
    <div class="ki__subtitle">区分引流词的价值：机会词去抢、污染词去剔、已覆盖去守</div>
    <div v-if="rangeLabel" class="ki__range">
      {{ rangeLabel }}<span v-if="dateAdjusted"> · T+3</span>
    </div>
    <div v-if="allWords.length === 0" class="ki__empty">暂无搜索词数据（搜索词数据有 T+3 滞后）</div>
    <div v-else>
      <div class="ki__cards">
        <div class="ki__card ki__card--opportunity">
          <div class="ki__card-title">
            机会词
            <button class="ki__help" type="button" :title="keywordRules.opportunity" aria-label="机会词说明">?</button>
            <SBadge variant="primary">{{ opportunity.length }}</SBadge>
          </div>
          <div class="ki__card-desc">搜索量高，但是点击率低</div>
        </div>
        <div class="ki__card ki__card--pollution">
          <div class="ki__card-title">
            污染词
            <button class="ki__help" type="button" :title="keywordRules.pollution" aria-label="污染词说明">?</button>
            <SBadge variant="warn">{{ pollution.length }}</SBadge>
          </div>
          <div class="ki__card-desc">搜索量高，但是没有订单</div>
        </div>
        <div class="ki__card ki__card--covered">
          <div class="ki__card-title">
            已覆盖
            <button class="ki__help" type="button" :title="keywordRules.covered" aria-label="已覆盖说明">?</button>
            <SBadge variant="success">{{ covered.length }}</SBadge>
          </div>
          <div class="ki__card-desc">这个词已经带来订单</div>
        </div>
      </div>
      <div class="ki__table-wrap">
        <table class="ki__table">
          <thead>
            <tr>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('query')">搜索词 {{ sortMark('query') }}</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('sku')">SKU {{ sortMark('sku') }}</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('searches')">搜索量 {{ sortMark('searches') }}</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('ctr')">点击率 {{ sortMark('ctr') }}</button>
                <button class="ki__help" type="button" :title="keywordRules.ctr" aria-label="点击率说明">?</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('position')">位置 {{ sortMark('position') }}</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('orders')">订单 {{ sortMark('orders') }}</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('gmv')">GMV {{ sortMark('gmv') }}</button>
              </th>
              <th>
                <button class="ki__sort" type="button" @click="toggleSort('verdict')">判定 {{ sortMark('verdict') }}</button>
                <button class="ki__help" type="button" :title="keywordRules.verdict" aria-label="判定说明">?</button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in sortedWords" :key="w.query + w.sku">
              <td>{{ w.query }}</td>
              <td class="ki__sku">{{ w.sku }}</td>
              <td>{{ w.searches }}</td>
              <td>{{ fmtPct(w.ctr) }}</td>
              <td>{{ w.position != null ? w.position : '—' }}</td>
              <td>{{ w.orders }}</td>
              <td>{{ fmtRub(w.gmv) }}</td>
              <td>
                <SBadge v-if="verdict(w)" :variant="verdict(w).variant">{{ verdict(w).label }}</SBadge>
                <span v-else class="ki__verdict-none">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="ki__note">搜索词数据存在 T+3 天滞后，且受 Ozon 隐私阈值过滤（低搜索量词不返回）。判定标签为系统规则，不是 Ozon 官方标签。</p>
    </div>
  </div>
</template>

<style scoped>
.ki { }
.ki__title { font-size: var(--fs-lg); font-weight: 700; color: var(--c-text); margin-bottom: 2px; }
.ki__subtitle { font-size: var(--fs-xs); color: var(--c-text-3); margin-bottom: var(--sp-4); }
.ki__range { font-size: var(--fs-xs); color: var(--c-text-4); margin: calc(-1 * var(--sp-2)) 0 var(--sp-3); }
.ki__verdict-none { color: var(--c-text-4); }
.ki__empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-4) 0; }
.ki__cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--sp-3); margin-bottom: var(--sp-4); }
.ki__card { background: var(--c-bg); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: var(--sp-3) var(--sp-4); }
.ki__card-title { font-weight: 600; color: var(--c-text); display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ki__card-desc { font-size: var(--fs-xs); color: var(--c-text-3); }
.ki__help {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--c-border);
  background: #fff;
  color: var(--c-text-4);
  font-size: 12px;
  line-height: 16px;
  padding: 0;
  cursor: help;
}
.ki__table-wrap { overflow-x: auto; }
.ki__table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.ki__table th { background: var(--c-bg); color: var(--c-text-3); font-weight: 600; padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.ki__table td { padding: 7px 10px; border-bottom: 1px solid var(--c-border-light, var(--c-border)); color: var(--c-text-2); }
.ki__sort {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  padding: 0;
  cursor: pointer;
}
.ki__sku { color: var(--c-text-4); font-size: var(--fs-xs); }
.ki__note { font-size: var(--fs-xs); color: var(--c-text-4); margin-top: var(--sp-3); }
</style>
