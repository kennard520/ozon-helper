<script setup>
const props = defineProps({
  grandTotal: { type: Object, default: null },
})

function pct(a, b) {
  if (!b || b === 0) return '—'
  return (a / b * 100).toFixed(1) + '%'
}

function fmt(v) {
  if (v == null) return '—'
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return String(v)
}
</script>
<template>
  <div class="funnel" v-if="grandTotal">
    <div class="funnel__step">
      <div class="funnel__label">曝光</div>
      <div class="funnel__value">{{ fmt(grandTotal.exposure) }}</div>
    </div>
    <div class="funnel__arrow">▶</div>
    <div class="funnel__step">
      <div class="funnel__label">访问</div>
      <div class="funnel__value">{{ fmt(grandTotal.sessions) }}</div>
      <div class="funnel__rate">{{ pct(grandTotal.sessions, grandTotal.exposure) }}</div>
    </div>
    <div class="funnel__arrow">▶</div>
    <div class="funnel__step">
      <div class="funnel__label">加购</div>
      <div class="funnel__value">{{ fmt(grandTotal.cart) }}</div>
      <div class="funnel__rate">{{ pct(grandTotal.cart, grandTotal.sessions) }}</div>
    </div>
    <div class="funnel__arrow">▶</div>
    <div class="funnel__step">
      <div class="funnel__label">下单</div>
      <div class="funnel__value">{{ fmt(grandTotal.ordered_units) }}</div>
      <div class="funnel__rate">{{ pct(grandTotal.ordered_units, grandTotal.cart) }}</div>
    </div>
  </div>
  <div v-else class="funnel funnel--empty">暂无数据</div>
</template>
<style scoped>
.funnel { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-4) 0; flex-wrap: wrap; }
.funnel--empty { color: var(--c-text-4); font-size: var(--fs-sm); }
.funnel__step { text-align: center; min-width: 72px; background: var(--c-bg); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: var(--sp-3) var(--sp-4); }
.funnel__label { font-size: var(--fs-xs); color: var(--c-text-3); }
.funnel__value { font-size: var(--fs-xl); font-weight: 700; color: var(--c-text); margin: 4px 0; }
.funnel__rate { font-size: var(--fs-xs); color: var(--c-text-4); }
.funnel__arrow { color: var(--c-text-4); font-size: var(--fs-sm); }
</style>
