<script setup>
import SStatCard from '../../ui/SStatCard.vue'

const props = defineProps({
  grandTotal: { type: Object, default: null },
})

function fmt(v, unit = '') {
  if (v == null) return '—'
  if (unit === '¥') return '¥' + Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return String(v)
}
</script>
<template>
  <div class="kpi-cards" v-if="grandTotal">
    <SStatCard label="总曝光" :value="fmt(grandTotal.exposure)" hint="impressions" />
    <SStatCard label="总访问" :value="fmt(grandTotal.sessions)" hint="sessions" />
    <SStatCard label="加购转化" :value="grandTotal.conv_cart_pct != null ? grandTotal.conv_cart_pct + '%' : '—'" hint="加购/访问" />
    <SStatCard label="GMV" :value="fmt(grandTotal.revenue, '¥')" hint="收入" />
  </div>
  <div v-else class="kpi-cards--empty">暂无汇总数据</div>
</template>
<style scoped>
.kpi-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--sp-4); }
.kpi-cards--empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-3) 0; }
</style>
