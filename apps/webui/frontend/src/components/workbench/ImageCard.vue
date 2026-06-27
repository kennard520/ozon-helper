<script setup>
import { computed } from 'vue'

const props = defineProps({
  url: { type: String, required: true },
  localUrl: { type: String, default: '' },
  type: { type: String, default: '' },
  source: { type: String, default: '' },
  selected: { type: Boolean, default: false },
  badge: { type: String, default: '' },
})
const src = computed(() => props.localUrl || props.url)
const sourceLabel = computed(() => (props.source === 'generated' ? '生成' : props.source === 'collected' ? '采集' : ''))
</script>

<template>
  <div class="img-card" :class="{ 'is-selected': selected }">
    <img :src="src" loading="lazy" alt="" />
    <span v-if="type" class="img-card__type">{{ type }}</span>
    <span v-if="sourceLabel" class="img-card__src">{{ sourceLabel }}</span>
    <span v-if="badge" class="img-card__badge">{{ badge }}</span>
    <div class="img-card__actions"><slot name="actions" /></div>
  </div>
</template>

<style scoped>
.img-card{position:relative;width:88px;height:88px;border-radius:var(--r-sm,8px);overflow:hidden;
  border:1px solid var(--c-border,#e5e7eb);background:#fafafa}
.img-card.is-selected{outline:2px solid var(--c-primary,#7c3aed);outline-offset:1px}
.img-card img{width:100%;height:100%;object-fit:cover;display:block}
.img-card__type{position:absolute;left:3px;top:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(124,58,237,.85);color:#fff}
.img-card__src{position:absolute;right:3px;top:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff}
.img-card__badge{position:absolute;left:3px;bottom:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff}
.img-card__actions{position:absolute;inset:auto 0 0 0;display:flex;gap:2px;justify-content:center;
  padding:2px;background:rgba(255,255,255,.9);opacity:0;transition:.15s}
.img-card:hover .img-card__actions{opacity:1}
</style>
