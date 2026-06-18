<template>
  <div class="rich-preview" v-if="blocks.length">
    <div v-for="(b, i) in blocks" :key="i" class="rich-block">
      <img v-if="b.img" :src="b.img" class="rich-img" loading="lazy" referrerpolicy="no-referrer" />
      <div v-if="b.title" class="rich-title">{{ b.title }}</div>
      <div v-if="b.text" class="rich-text">{{ b.text }}</div>
    </div>
  </div>
  <div v-else class="rich-empty">（无富文本）</div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ richJson: { type: Object, default: null } })

function fieldText(f) {
  if (!f) return ''
  const out = []
  if (Array.isArray(f.content)) out.push(...f.content)
  else if (typeof f.content === 'string') out.push(f.content)
  if (Array.isArray(f.items)) {
    for (const it of f.items) if (it && it.content) out.push(it.content)
  }
  return out.filter(Boolean).join('\n')
}

const blocks = computed(() => {
  const rj = props.richJson
  const content = rj && rj.content
  if (!Array.isArray(content)) return []
  const out = []
  for (const c of content) {
    for (const b of (c && c.blocks) || []) {
      if (!b) continue
      const img = (b.img && (b.img.src || b.img.srcMobile)) || ''
      const title = fieldText(b.title)
      const text = fieldText(b.text)
      if (img || title || text) out.push({ img, title, text })
    }
  }
  return out
})
</script>

<style scoped>
.rich-preview { max-height: 420px; overflow: auto; border: 1px solid var(--c-border-soft); border-radius: 6px; padding: 8px; background: var(--c-surface-2); }
.rich-block { margin-bottom: 12px; }
.rich-img { max-width: 100%; display: block; border-radius: 4px; }
.rich-title { font-weight: 600; margin: 6px 0 2px; }
.rich-text { white-space: pre-wrap; color: var(--c-text); font-size: 13px; }
.rich-empty { color: var(--c-text-3); font-size: 13px; padding: 8px; }
</style>
