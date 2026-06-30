<script setup>
defineProps({ variant: { type: String, default: 'info' }, title: String })
</script>
<template>
  <div class="s-alert" :class="`s-alert--${variant}`">
    <div class="s-alert__c">
      <div class="s-alert__t">{{ title }}</div>
      <div v-if="$slots.default" class="s-alert__d"><slot /></div>
    </div>
    <div class="s-alert__a"><slot name="actions" /></div>
  </div>
</template>
<style scoped>
.s-alert{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-4);
  padding:var(--sp-3) var(--sp-4);border-radius:var(--r-md);border:1px solid transparent}
.s-alert--danger{background:var(--c-danger-bg);border-color:#fecaca}
.s-alert--warn{background:var(--c-warn-bg);border-color:#fde68a}
.s-alert--info{background:var(--c-info-bg);border-color:#bfdbfe}
.s-alert--success{background:var(--c-success-bg);border-color:#a7f3d0}
.s-alert__t{font-weight:600;color:var(--c-text)}
.s-alert__d{font-size:var(--fs-sm);color:var(--c-text-2);margin-top:2px}
</style>
