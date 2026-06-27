<script setup>
import { computed } from 'vue'
import SBadge from '../../ui/SBadge.vue'

const props = defineProps({
  bySku: { type: Object, default: () => ({}) }, // { sku: [{query, searches, ctr, position, orders, gmv}] }
})

// 展平所有词，按 searches 排序
const allWords = computed(() => {
  const flat = []
  for (const [sku, words] of Object.entries(props.bySku)) {
    for (const w of words) flat.push({ ...w, sku })
  }
  return flat.sort((a, b) => b.searches - a.searches)
})

// 机会词：搜索量高但 ctr 低（< 0.03）
const opportunity = computed(() => allWords.value.filter(w => w.searches > 500 && w.ctr < 0.03))
// 污染词：高搜索低订单
const pollution = computed(() => allWords.value.filter(w => w.searches > 500 && w.orders === 0))
// 已覆盖：有订单
const covered = computed(() => allWords.value.filter(w => w.orders > 0))
</script>
<template>
  <div class="ki">
    <div v-if="allWords.length === 0" class="ki__empty">暂无搜索词数据（搜索词数据有 T+3 滞后）</div>
    <div v-else>
      <div class="ki__cards">
        <div class="ki__card ki__card--opportunity">
          <div class="ki__card-title">机会词 <SBadge variant="primary">{{ opportunity.length }}</SBadge></div>
          <div class="ki__card-desc">高搜索量低点击率，可优化标题/主图</div>
        </div>
        <div class="ki__card ki__card--pollution">
          <div class="ki__card-title">污染词 <SBadge variant="warn">{{ pollution.length }}</SBadge></div>
          <div class="ki__card-desc">高搜索量零订单，可能引流不准确</div>
        </div>
        <div class="ki__card ki__card--covered">
          <div class="ki__card-title">已覆盖 <SBadge variant="success">{{ covered.length }}</SBadge></div>
          <div class="ki__card-desc">有下单记录的搜索词</div>
        </div>
      </div>
      <div class="ki__table-wrap">
        <table class="ki__table">
          <thead>
            <tr>
              <th>搜索词</th>
              <th>SKU</th>
              <th>搜索量</th>
              <th>CTR</th>
              <th>位置</th>
              <th>订单</th>
              <th>GMV</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in allWords" :key="w.query + w.sku">
              <td>{{ w.query }}</td>
              <td class="ki__sku">{{ w.sku }}</td>
              <td>{{ w.searches }}</td>
              <td>{{ w.ctr != null ? (w.ctr * 100).toFixed(1) + '%' : '—' }}</td>
              <td>{{ w.position != null ? w.position : '—' }}</td>
              <td>{{ w.orders }}</td>
              <td>{{ w.gmv != null ? '¥' + w.gmv : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="ki__note">搜索词数据存在 T+3 天滞后，且受 Ozon 隐私阈值过滤（低搜索量词不返回）。</p>
    </div>
  </div>
</template>
<style scoped>
.ki { }
.ki__empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-4) 0; }
.ki__cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--sp-3); margin-bottom: var(--sp-4); }
.ki__card { background: var(--c-bg); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: var(--sp-3) var(--sp-4); }
.ki__card-title { font-weight: 600; color: var(--c-text); display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ki__card-desc { font-size: var(--fs-xs); color: var(--c-text-3); }
.ki__table-wrap { overflow-x: auto; }
.ki__table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.ki__table th { background: var(--c-bg); color: var(--c-text-3); font-weight: 600; padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--c-border); }
.ki__table td { padding: 7px 10px; border-bottom: 1px solid var(--c-border-light, var(--c-border)); color: var(--c-text-2); }
.ki__sku { color: var(--c-text-4); font-size: var(--fs-xs); }
.ki__note { font-size: var(--fs-xs); color: var(--c-text-4); margin-top: var(--sp-3); }
</style>
