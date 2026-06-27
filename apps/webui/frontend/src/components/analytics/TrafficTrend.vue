<script setup>
import { computed } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] }, // [{sku, day, hits_view, session_view, hits_tocart, ordered_units}]
})

// 按 day 聚合
const byDay = computed(() => {
  const map = {}
  for (const r of props.rows) {
    if (!map[r.day]) map[r.day] = { day: r.day, hits_view: 0, session_view: 0, hits_tocart: 0, ordered_units: 0 }
    map[r.day].hits_view += r.hits_view || 0
    map[r.day].session_view += r.session_view || 0
    map[r.day].hits_tocart += r.hits_tocart || 0
    map[r.day].ordered_units += r.ordered_units || 0
  }
  return Object.values(map).sort((a, b) => a.day.localeCompare(b.day))
})

const maxView = computed(() => Math.max(1, ...byDay.value.map(d => d.hits_view)))

function barH(v) { return Math.max(2, Math.round((v / maxView.value) * 80)) }
</script>
<template>
  <div class="tt">
    <div v-if="byDay.length === 0" class="tt__empty">暂无流量趋势数据</div>
    <div v-else class="tt__chart">
      <div class="tt__legend">
        <span class="tt__dot tt__dot--view"></span>曝光
        <span class="tt__dot tt__dot--session" style="margin-left:12px"></span>访问
        <span class="tt__dot tt__dot--cart" style="margin-left:12px"></span>加购
      </div>
      <div class="tt__bars">
        <div v-for="d in byDay" :key="d.day" class="tt__bar-group">
          <div class="tt__bars-inner">
            <div class="tt__bar tt__bar--view" :style="{ height: barH(d.hits_view) + 'px' }" :title="`曝光 ${d.hits_view}`"></div>
            <div class="tt__bar tt__bar--session" :style="{ height: barH(d.session_view) + 'px' }" :title="`访问 ${d.session_view}`"></div>
            <div class="tt__bar tt__bar--cart" :style="{ height: barH(d.hits_tocart) + 'px' }" :title="`加购 ${d.hits_tocart}`"></div>
          </div>
          <div class="tt__day-label">{{ d.day.slice(5) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.tt { }
.tt__empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-4) 0; }
.tt__legend { display: flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: var(--c-text-3); margin-bottom: var(--sp-3); }
.tt__dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; }
.tt__dot--view { background: var(--c-primary); }
.tt__dot--session { background: var(--c-info, #3b82f6); }
.tt__dot--cart { background: var(--c-success, #10b981); }
.tt__chart { overflow-x: auto; }
.tt__bars { display: flex; align-items: flex-end; gap: 2px; min-height: 100px; padding-bottom: 24px; position: relative; }
.tt__bar-group { display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 20px; }
.tt__bars-inner { display: flex; align-items: flex-end; gap: 1px; }
.tt__bar { width: 6px; border-radius: 2px 2px 0 0; transition: height 0.2s; }
.tt__bar--view { background: var(--c-primary); }
.tt__bar--session { background: var(--c-info, #3b82f6); }
.tt__bar--cart { background: var(--c-success, #10b981); }
.tt__day-label { font-size: 10px; color: var(--c-text-4); margin-top: 4px; white-space: nowrap; }
</style>
