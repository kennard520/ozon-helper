<script setup>
defineProps({ variant: { type: String, default: 'neutral' } })
</script>
<template><span class="s-badge" :class="`s-badge--${variant}`"><slot /></span></template>
<style scoped>
.s-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:999px;
  font-size:var(--fs-xs);font-weight:600;line-height:1.6}
.s-badge--success{background:var(--c-success-bg);color:var(--c-success)}
.s-badge--danger{background:var(--c-danger-bg);color:var(--c-danger)}
.s-badge--info{background:var(--c-info-bg);color:var(--c-info)}
.s-badge--warn{background:var(--c-warn-bg);color:var(--c-warn)}
.s-badge--primary{background:var(--c-primary-100);color:var(--c-primary)}
.s-badge--neutral{background:var(--c-bg);color:var(--c-text-3)}
</style>
