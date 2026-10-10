<template>
  <div class="variant-list" v-if="variants.length">
    <div class="variant-head">变体（{{ variants.length }}）<span v-if="group" class="variant-group">组 {{ group }}</span></div>
    <div class="variant-grid">
      <a
        v-for="(v, i) in variants"
        :key="v.sku || i"
        class="variant-cell"
        :class="{ active: v.active, off: !v.available }"
        :href="v.link || '#'"
        target="_blank"
        rel="noreferrer"
        :title="(v.aspect ? v.aspect + ': ' : '') + (v.label || v.sku)"
      >
        <img v-if="v.cover" :src="v.cover" class="variant-img" loading="lazy" referrerpolicy="no-referrer" />
        <div v-else class="variant-img variant-img-empty">无图</div>
        <div class="variant-label">{{ v.label || v.sku }}</div>
        <div class="variant-meta">
          <span v-if="v.price != null">{{ v.price }} ₽</span>
          <span v-if="!v.available" class="variant-off">缺货</span>
        </div>
      </a>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  variants: { type: Array, default: () => [] },
  group: { type: String, default: '' }
})
const variants = computed(() => (Array.isArray(props.variants) ? props.variants : []))
const group = computed(() => props.group || '')
</script>

<style scoped>
.variant-list { margin-top: 12px; }
.variant-head { font-size: 13px; color: var(--c-text-2); margin-bottom: 6px; }
.variant-group { color: var(--c-text-3); margin-left: 8px; }
.variant-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(88px, 1fr)); gap: 8px; max-height: 320px; overflow: auto; }
.variant-cell { display: block; border: 1px solid var(--c-border-soft); border-radius: 6px; padding: 4px; text-decoration: none; color: var(--c-text); }
.variant-cell.active { border-color: var(--c-info); }
.variant-cell.off { opacity: 0.55; }
.variant-img { width: 100%; height: 72px; object-fit: cover; border-radius: 4px; display: block; }
.variant-img-empty { display: flex; align-items: center; justify-content: center; background: var(--c-surface-2); color: var(--c-text-disabled); font-size: 12px; }
.variant-label { font-size: 12px; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.variant-meta { font-size: 11px; color: var(--c-info); display: flex; justify-content: space-between; }
.variant-off { color: var(--c-danger); }
</style>
