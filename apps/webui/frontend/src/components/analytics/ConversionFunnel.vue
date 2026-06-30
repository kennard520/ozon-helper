<script setup>
import { computed } from 'vue'

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

// 四级数据
const steps = computed(() => {
  const gt = props.grandTotal
  if (!gt) return []
  const list = [
    { key: 'exposure', label: '曝光', value: gt.exposure || 0, prev: null },
    { key: 'sessions', label: '访问', value: gt.sessions || 0, prev: gt.exposure || 0 },
    { key: 'cart', label: '加购', value: gt.cart || 0, prev: gt.sessions || 0 },
    { key: 'ordered_units', label: '下单', value: gt.ordered_units || 0, prev: gt.cart || 0 },
  ]
  const max = Math.max(1, ...list.map(s => s.value))
  // 找断点：第一个从上一级急剧跌落（转化率 < 5%）或归零的级
  let breakIdx = -1
  for (let i = 1; i < list.length; i++) {
    const s = list[i]
    if (s.prev > 0 && s.value === 0) { breakIdx = i; break }
    if (s.prev > 0 && (s.value / s.prev) < 0.05) { breakIdx = i; break }
  }
  return list.map((s, i) => {
    // 柱高按量缩放（10~100%）
    const h = Math.round(10 + (s.value / max) * 90)
    let note = ''
    if (i === 0) {
      note = '入口流量'
    } else if (s.value === 0 && s.prev > 0) {
      note = '⚠ 无成交'
    } else if (i === breakIdx) {
      note = '⚠ 断点在此'
    } else {
      note = i === 1 ? '会话率健康' : '转化健康'
    }
    return { ...s, h, note, isBreak: i === breakIdx || (s.value === 0 && s.prev > 0) }
  })
})
</script>
<template>
  <div v-if="!grandTotal" class="funnel funnel--empty">暂无数据</div>
  <div v-else class="funnel-wrap">
    <div class="funnel__sub">找到断点</div>
    <div class="funnel">
      <template v-for="(s, i) in steps" :key="s.key">
        <div class="funnel__step" :class="{ 'is-break': s.isBreak }">
          <div class="funnel__bar-area">
            <div class="funnel__bar" :class="{ 'is-break': s.isBreak }" :style="{ height: s.h + '%' }"></div>
          </div>
          <div class="funnel__label">{{ s.label }}</div>
          <div class="funnel__value">{{ fmt(s.value) }}</div>
          <div v-if="s.prev != null" class="funnel__rate">{{ pct(s.value, s.prev) }}</div>
          <div class="funnel__note" :class="{ 'is-break': s.isBreak }">{{ s.note }}</div>
        </div>
        <div v-if="i < steps.length - 1" class="funnel__arrow">▶</div>
      </template>
    </div>
  </div>
</template>
<style scoped>
.funnel-wrap { padding: var(--sp-3) 0; }
.funnel__sub { font-size: var(--fs-xs); color: var(--c-text-3); margin-bottom: var(--sp-3); }
.funnel { display: flex; align-items: flex-end; gap: var(--sp-3); flex-wrap: wrap; }
.funnel--empty { color: var(--c-text-4); font-size: var(--fs-sm); padding: var(--sp-4) 0; }
.funnel__step { text-align: center; min-width: 80px; flex: 1; background: var(--c-bg); border: 1px solid var(--c-border); border-radius: var(--r-md); padding: var(--sp-3); }
.funnel__step.is-break { border-color: var(--c-danger); background: var(--c-danger-bg); }
.funnel__bar-area { height: 72px; display: flex; align-items: flex-end; justify-content: center; }
.funnel__bar { width: 60%; min-width: 28px; background: var(--c-primary); border-radius: 4px 4px 0 0; transition: height 0.3s; }
.funnel__bar.is-break { background: var(--c-danger); }
.funnel__label { font-size: var(--fs-xs); color: var(--c-text-3); margin-top: 6px; }
.funnel__value { font-size: var(--fs-xl); font-weight: 700; color: var(--c-text); margin: 2px 0; }
.funnel__rate { font-size: var(--fs-xs); color: var(--c-text-4); }
.funnel__note { font-size: var(--fs-xs); color: var(--c-text-3); margin-top: 4px; }
.funnel__note.is-break { color: var(--c-danger); font-weight: 600; }
.funnel__arrow { color: var(--c-text-4); font-size: var(--fs-sm); align-self: center; margin-bottom: 40px; }
</style>
