<script setup>
defineProps({ label: String, value: [String, Number], hint: String, danger: Boolean })
</script>
<template>
  <div class="s-stat">
    <div class="s-stat__l">{{ label }}</div>
    <div class="s-stat__v" :class="{ 'is-danger': danger }">{{ value }}</div>
    <div v-if="hint" class="s-stat__h">{{ hint }}</div>
  </div>
</template>
<style scoped>
.s-stat{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-md);padding:var(--sp-4);box-shadow:var(--sh-card)}
.s-stat__l{font-size:var(--fs-sm);color:var(--c-text-3)}
.s-stat__v{font-size:var(--fs-2xl);font-weight:700;color:var(--c-text);margin-top:6px}
.s-stat__v.is-danger{color:var(--c-danger)}
.s-stat__h{font-size:var(--fs-xs);color:var(--c-text-4);margin-top:4px}
</style>
