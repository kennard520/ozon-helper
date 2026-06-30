<script setup>
import { computed } from 'vue'
import SStatCard from '../../ui/SStatCard.vue'

const props = defineProps({
  grandTotal: { type: Object, default: null },
})

// ₽（卢布）格式化 — 本页 GMV/收入均为俄罗斯店卢布，绝不用 ¥
function fmtRub(v) {
  if (v == null) return '—'
  return '₽' + Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}
// 普通整数（带万级缩写）
function fmtNum(v) {
  if (v == null) return '—'
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return Number(v).toLocaleString('zh-CN')
}

// 会话率 = 访问 / 曝光
const sessionRate = computed(() => {
  const gt = props.grandTotal
  if (!gt || !gt.exposure) return null
  return Math.round((gt.sessions / gt.exposure) * 1000) / 10
})

// 加购转化危险态：值为 0 或极低（< 1%）
const cartDanger = computed(() => {
  const gt = props.grandTotal
  if (!gt) return false
  const v = gt.conv_cart_pct
  return v == null || v <= 0 || v < 1
})

// GMV/下单危险态：收入为 0 或无成交
const gmvDanger = computed(() => {
  const gt = props.grandTotal
  if (!gt) return false
  return !gt.revenue || gt.revenue <= 0 || !gt.ordered_units
})
</script>
<template>
  <div class="kpi-cards" v-if="grandTotal">
    <SStatCard
      label="总曝光"
      :value="fmtNum(grandTotal.exposure)"
      hint="impressions"
    />
    <SStatCard
      label="总访问/会话"
      :value="fmtNum(grandTotal.sessions)"
      :hint="sessionRate != null ? `会话率 ${sessionRate}%` : 'sessions'"
    />
    <SStatCard
      label="加购转化"
      :value="grandTotal.conv_cart_pct != null ? grandTotal.conv_cart_pct + '%' : '—'"
      :hint="`${fmtNum(grandTotal.cart)} 次加购`"
      :danger="cartDanger"
    />
    <SStatCard
      label="GMV/下单"
      :value="fmtRub(grandTotal.revenue)"
      :hint="`${fmtNum(grandTotal.ordered_units)} 单`"
      :danger="gmvDanger"
    />
  </div>
  <div v-else class="kpi-cards--empty">暂无汇总数据</div>
</template>
<style scoped>
.kpi-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--sp-4); }
.kpi-cards--empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-3) 0; }
</style>
