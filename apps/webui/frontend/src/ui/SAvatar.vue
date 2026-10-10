<script setup>
const props = defineProps({ name: String, size: { type: Number, default: 40 } })
const initial = () => (props.name || '?').trim().charAt(0).toUpperCase()
</script>
<template>
  <div class="s-avatar" :style="{ width: size+'px', height: size+'px', fontSize: (size*0.4)+'px' }">{{ initial() }}</div>
</template>
<style scoped>
.s-avatar{display:inline-flex;align-items:center;justify-content:center;border-radius:var(--r-md);
  background:var(--c-primary-100);color:var(--c-primary);font-weight:700}
</style>
