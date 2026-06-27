<script setup>
defineProps({ title: String, subtitle: String })
</script>
<template>
  <div class="s-sec">
    <div class="s-sec__l"><span class="s-sec__bar"></span>
      <div><div class="s-sec__t">{{ title }}</div>
        <div v-if="subtitle" class="s-sec__s">{{ subtitle }}</div></div></div>
    <div class="s-sec__a"><slot name="actions" /></div>
  </div>
</template>
<style scoped>
.s-sec{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-4)}
.s-sec__l{display:flex;align-items:center;gap:var(--sp-3)}
.s-sec__bar{width:4px;height:18px;border-radius:2px;background:var(--c-primary)}
.s-sec__t{font-size:var(--fs-xl);font-weight:700;color:var(--c-text)}
.s-sec__s{font-size:var(--fs-sm);color:var(--c-text-3);margin-top:2px}
</style>
