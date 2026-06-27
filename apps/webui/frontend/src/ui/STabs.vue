<script setup>
defineProps({ items: { type: Array, default: () => [] }, activeKey: String })
const emit = defineEmits(['change'])
</script>
<template>
  <div class="s-tabs">
    <button v-for="it in items" :key="it.key" class="s-tabs__item"
            :class="{ 'is-active': it.key === activeKey }" @click="emit('change', it.key)">
      {{ it.label }}<span v-if="it.count != null" class="s-tabs__cnt">{{ it.count }}</span>
    </button>
  </div>
</template>
<style scoped>
.s-tabs{display:flex;gap:var(--sp-4);border-bottom:1px solid var(--c-border)}
.s-tabs__item{background:none;border:none;padding:8px 2px;font-size:var(--fs-md);color:var(--c-text-3);
  cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.s-tabs__item.is-active{color:var(--c-primary);border-bottom-color:var(--c-primary);font-weight:600}
.s-tabs__cnt{margin-left:6px;font-size:var(--fs-xs);color:var(--c-text-4)}
</style>
