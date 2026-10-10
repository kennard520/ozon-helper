<script setup>
defineProps({ active: Boolean, closable: Boolean })
const emit = defineEmits(['close', 'click'])
</script>
<template>
  <span class="s-chip" :class="{ 'is-active': active }" @click="emit('click')">
    <slot />
    <span v-if="closable" class="s-chip__close" @click.stop="emit('close')">×</span>
  </span>
</template>
<style scoped>
.s-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:var(--r-sm);
  font-size:var(--fs-sm);border:1px solid var(--c-border);background:#fff;cursor:pointer;color:var(--c-text-2)}
.s-chip.is-active{border-color:var(--c-primary);background:var(--c-primary-50);color:var(--c-primary)}
.s-chip__close{color:var(--c-text-3);font-size:14px;line-height:1}
.s-chip__close:hover{color:var(--c-danger)}
</style>
