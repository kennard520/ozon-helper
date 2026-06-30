<script setup>
import { computed } from 'vue'

const props = defineProps({
  url: { type: String, required: true },
  localUrl: { type: String, default: '' },
  type: { type: String, default: '' },
  source: { type: String, default: '' },
  selected: { type: Boolean, default: false },
  badge: { type: String, default: '' },
  selectable: { type: Boolean, default: false },
  showSelectControl: { type: Boolean, default: true },
})
const emit = defineEmits(['zoom', 'toggle-select'])
const src = computed(() => props.localUrl || props.url)
const sourceLabel = computed(() => (props.source === 'generated' ? '生成' : props.source === 'collected' ? '采集' : ''))

function onImgClick(e) {
  e.stopPropagation()
  emit('zoom', src.value)
}
</script>

<template>
  <div class="img-card" :class="{ 'is-selected': selected }">
    <img :src="src" loading="lazy" alt="" @click="onImgClick" />
    <button
      v-if="selectable && showSelectControl"
      class="img-card__select"
      :class="{ 'is-selected': selected }"
      :title="selected ? '取消选择' : '选择图片'"
      :aria-label="selected ? '取消选择' : '选择图片'"
      @click.stop="emit('toggle-select')"
    >
      <span v-if="selected">✓</span>
    </button>
    <button class="img-card__zoom" title="放大查看" aria-label="放大查看" @click.stop="emit('zoom', src)">
      🔍
    </button>
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
.img-card img{width:100%;height:100%;object-fit:cover;display:block;cursor:zoom-in}
.img-card__type{position:absolute;left:3px;top:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(124,58,237,.85);color:#fff}
.img-card__src{position:absolute;right:3px;top:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff}
.img-card__badge{position:absolute;left:3px;bottom:3px;font-size:10px;padding:1px 5px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff}
.img-card__select{position:absolute;left:4px;top:4px;width:20px;height:20px;border:1px solid rgba(255,255,255,.9);
  border-radius:5px;background:rgba(31,39,51,.46);color:#fff;cursor:pointer;font-size:13px;line-height:18px;
  display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.18);z-index:2}
.img-card__select.is-selected{background:var(--c-primary,#7c3aed);border-color:var(--c-primary,#7c3aed)}
.img-card__select:hover{background:var(--c-primary,#7c3aed);border-color:var(--c-primary,#7c3aed)}
.img-card__zoom{position:absolute;right:3px;bottom:3px;border:none;cursor:pointer;
  font-size:11px;line-height:1;padding:2px 4px;border-radius:6px;
  background:rgba(0,0,0,.5);color:#fff;opacity:0;transition:.15s;z-index:2}
.img-card:hover .img-card__zoom{opacity:1}
.img-card__actions{position:absolute;inset:auto 0 0 0;display:flex;gap:2px;justify-content:center;
  padding:2px;background:rgba(255,255,255,.9);opacity:0;transition:.15s;z-index:3}
.img-card:hover .img-card__actions{opacity:1}
</style>
