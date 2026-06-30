<script setup>
defineProps({ padding: { type: String, default: 'var(--sp-5)' } })
</script>
<template>
  <div class="s-card">
    <div v-if="$slots.header" class="s-card__h"><slot name="header" /></div>
    <div class="s-card__b" :style="{ padding }"><slot /></div>
    <div v-if="$slots.footer" class="s-card__f"><slot name="footer" /></div>
  </div>
</template>
<style scoped>
.s-card{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);box-shadow:var(--sh-card);overflow:hidden}
.s-card__h{padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border);font-weight:600;color:var(--c-text)}
.s-card__f{padding:var(--sp-3) var(--sp-5);border-top:1px solid var(--c-border)}
</style>
