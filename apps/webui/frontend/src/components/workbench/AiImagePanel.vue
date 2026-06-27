<script setup>
import { ref, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useImagePlan } from '../../composables/useImagePlan.js'
import { SButton, SBadge } from '../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['changed'])
const draftRef = toRef(props, 'draft')
const p = useImagePlan(draftRef, { onChange: () => emit('changed') })

const designLoading = ref(false)
onMounted(() => { p.loadPlan() })

async function doDesign() {
  designLoading.value = true
  try { await p.designPlan(10); ElMessage.success('已生成图集方案') }
  catch (e) { ElMessage.warning(`设计失败：${e && e.message ? e.message : e}`) }
  finally { designLoading.value = false }
}
async function doGen(slotId) {
  try { await p.generateSlot(slotId) }
  catch (e) { ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`) }
}
async function doGenAll() {
  try { await p.generateAll(); ElMessage.success('已出全部') }
  catch (e) { ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`) }
}
const ACTION_LABEL = { white: '白底', localize: '俄化', scene: '场景', infographic: '信息图' }
</script>

<template>
  <section class="ai-panel">
    <div class="ai-panel__bar">
      <span class="ai-panel__title">AI 出图</span>
      <SButton size="sm" variant="primary" :loading="designLoading" @click="doDesign">AI 设计图集</SButton>
      <SButton size="sm" @click="p.loadPlan(true)">刷新计划</SButton>
      <SButton v-if="p.todoCount.value" size="sm" @click="doGenAll">一键出全部（{{ p.todoCount.value }}）</SButton>
    </div>

    <div v-if="p.plan.value.length" class="ai-panel__slots">
      <div v-for="s in p.plan.value" :key="s.slot_id" class="ai-slot">
        <span class="ai-slot__label">{{ s.label || s.slot_id }}</span>
        <SBadge variant="info">{{ ACTION_LABEL[s.action] || s.action }}</SBadge>
        <SBadge :variant="s.status === 'applied' ? 'success' : 'neutral'">
          {{ s.status === 'applied' ? '已出图' : '待做' }}
        </SBadge>
        <SButton size="sm" :loading="!!p.genState[s.slot_id]" @click="doGen(s.slot_id)">
          {{ s.status === 'applied' ? '重出' : '生成' }}
        </SButton>
      </div>
    </div>
    <div v-else class="ai-panel__empty">点「AI 设计图集」据看图理解设计槽位方案。</div>
  </section>
</template>

<style scoped>
.ai-panel{margin-bottom:var(--sp-5,20px);padding:var(--sp-3,12px);border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);background:var(--c-primary-50,#faf7ff)}
.ai-panel__bar{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-2,8px)}
.ai-panel__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.ai-panel__slots{display:flex;flex-direction:column;gap:6px}
.ai-slot{display:flex;align-items:center;gap:var(--sp-2,8px);font-size:var(--fs-sm,13px)}
.ai-slot__label{min-width:120px}
.ai-panel__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888)}
</style>
