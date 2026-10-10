<script setup>
import { computed } from 'vue'
import { useWorkbenchStore, variantColor, variantColorName } from '../../stores/workbench.js'
import { useAppStore } from '../../stores/app.js'
import { usePipeline } from '../../composables/usePipeline.js'
import SButton from '../../ui/SButton.vue'
import SBadge from '../../ui/SBadge.vue'

const emit = defineEmits(['publish-one'])

const wb = useWorkbenchStore()
const store = useAppStore()
const pipe = usePipeline(wb, store)

const CARDS = [
  {
    id: 'understand',
    no: 1,
    title: '理解/准备',
    eta: '~30s',
    backend: ['understand'],
    action: '运行',
  },
  {
    id: 'category',
    no: 2,
    title: 'AI 分类',
    eta: '~30s',
    backend: ['category_recognition'],
    action: '运行',
  },
  {
    id: 'content',
    no: 3,
    title: 'AI 生成内容',
    eta: '~2min（后台）',
    backend: ['ai_text'],
    action: '运行',
  },
  {
    id: 'images',
    no: 4,
    title: '图集/出图',
    eta: '~2-3min',
    backend: ['ai_image', 'media'],
    action: '运行',
  },
  {
    id: 'rich',
    no: 5,
    title: '富文本',
    eta: '即时',
    backend: ['rich_content'],
    action: '运行',
  },
  {
    id: 'publish',
    no: 6,
    title: '发布',
    eta: '~30s',
    backend: ['preflight', 'publish'],
    action: '发布',
  },
]

const currentName = computed(() => {
  const v = wb.currentVariant
  return v ? (v.spec || variantColorName(v) || '当前变体') : ''
})

function backendSteps(card) {
  const steps = (pipe.pipeline.value && pipe.pipeline.value.steps) || []
  return steps.filter((step) => card.backend.includes(step.id))
}

function cardState(card) {
  const serverSteps = backendSteps(card)
  const local = pipe.stepStatus[card.id]
  const statuses = serverSteps.map((s) => String(s.status || ''))

  if (statuses.some((s) => s === 'failed')) return 'failed'
  if (statuses.some((s) => s === 'cancelled')) return 'cancelled'
  if (statuses.some((s) => s === 'blocked')) return 'locked'
  if (card.id === 'publish' && hasPublishRisk(serverSteps)) return 'warning'
  if (wb.currentStepDone(card.id) || (serverSteps.length && statuses.every((s) => s === 'done' || s === 'skipped'))) return 'done'
  if (local === 'running' || local === 'submitted' || statuses.some((s) => s === 'running' || s === 'submitted')) return 'running'
  if (pipe.stepLocked(card.id)) return 'locked'
  return 'idle'
}

function hasPublishRisk(serverSteps) {
  return serverSteps.some((step) => {
    const status = String(step.status || '')
    return status === 'warning' || (step.checks && step.checks.length) || (step.errors && step.errors.length)
  })
}

function statusText(card) {
  const state = cardState(card)
  if (state === 'done') return '已完成'
  if (state === 'running') return card.id === 'content' && pipe.textJob.value && pipe.textJob.value.current_step
    ? `生成中：${pipe.textJob.value.current_step}`
    : '进行中'
  if (state === 'failed') return '失败'
  if (state === 'cancelled') return '已取消'
  if (state === 'locked') return '待前置'
  if (state === 'warning') return '有风险'
  return '未开始'
}

function statusVariant(card) {
  const state = cardState(card)
  if (state === 'done') return 'success'
  if (state === 'failed' || state === 'locked' || state === 'cancelled') return 'danger'
  if (state === 'warning') return 'warn'
  if (state === 'running') return 'primary'
  return 'neutral'
}

function failureReason(card) {
  if (card.id === 'content' && pipe.textJob.value && ['failed', 'cancelled'].includes(String(pipe.textJob.value.status || '').toLowerCase())) {
    return pipe.textJob.value.error || 'AI 生成失败'
  }
  const step = backendSteps(card).find((s) => (s.errors && s.errors.length) || s.error)
  if (!step) return ''
  return step.error || step.errors[0]
}

function riskMessages(card) {
  if (card.id !== 'publish') return []
  const messages = []
  for (const step of backendSteps(card)) {
    for (const check of step.checks || []) {
      messages.push(check.message || check.label)
    }
    for (const error of step.errors || []) messages.push(error)
  }
  return messages.filter(Boolean).slice(0, 3)
}

function isRunning(card) {
  return cardState(card) === 'running'
}

function isLocked(card) {
  if (card.id === 'publish') return pipe.stepLocked(card.id)
  return pipe.stepLocked(card.id)
}

function runCard(card) {
  if (card.id === 'publish') {
    emit('publish-one')
    return
  }
  pipe.runStep(card.id)
}
</script>

<template>
  <div class="pp-wrap">
    <header class="pp-head">
      <div>
        <h2 class="pp-title">AI 智能上架工作台</h2>
        <p class="pp-subtitle">先选分类，再生成内容；细分任务在后台自动完成。</p>
      </div>
      <div v-if="wb.currentVariant" class="pp-variant">
        <span class="pp-variant__dot" :style="{ background: variantColor(wb.currentVariant) }"></span>
        <span>{{ currentName }}</span>
      </div>
    </header>

    <div v-if="!wb.currentVariant" class="pp-empty">请先在上方选择一个变体</div>

    <section v-else class="pp-cards">
      <div
        v-for="card in CARDS"
        :key="card.id"
        class="pp-card"
        :class="`pp-card--${cardState(card)}`"
      >
        <div class="pp-card__main">
          <span class="pp-card__num">{{ card.no }}</span>
          <div class="pp-card__text">
            <strong>{{ card.title }}</strong>
            <span>{{ card.eta }}</span>
          </div>
        </div>

        <div class="pp-card__bottom">
          <SBadge :variant="statusVariant(card)">{{ statusText(card) }}</SBadge>
          <SButton
            variant="ghost"
            size="sm"
            :loading="isRunning(card)"
            :disabled="!!pipe.batchRunningOp.value || isLocked(card)"
            @click="runCard(card)"
          >{{ card.action }}</SButton>
        </div>

        <p v-if="failureReason(card)" class="pp-card__reason">{{ failureReason(card) }}</p>
        <div v-if="riskMessages(card).length" class="pp-risks">
          <button
            v-for="(msg, idx) in riskMessages(card)"
            :key="idx"
            class="pp-risk"
            type="button"
          >{{ msg }}</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.pp-wrap{display:flex;flex-direction:column;gap:12px}
.pp-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.pp-title{margin:0;font-size:var(--fs-lg);font-weight:700;color:var(--c-text-1)}
.pp-subtitle{margin:2px 0 0;font-size:var(--fs-sm);color:var(--c-text-3)}
.pp-variant{display:flex;align-items:center;gap:8px;max-width:42%;padding:7px 10px;border:1px solid var(--c-border);border-radius:var(--r-sm);background:#fff;font-size:var(--fs-sm);color:var(--c-text-2)}
.pp-variant__dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.pp-empty{padding:12px;border:1px dashed var(--c-border);border-radius:var(--r-sm);color:var(--c-text-3);font-size:var(--fs-sm)}
.pp-cards{display:grid;grid-template-columns:repeat(3,minmax(190px,1fr));gap:12px}
.pp-card{display:flex;flex-direction:column;gap:12px;min-height:112px;padding:14px 16px;border:1px solid var(--c-border);border-radius:8px;background:#fff}
.pp-card--running{border-color:var(--c-primary-200);background:var(--c-primary-50,#f0f5ff)}
.pp-card--failed,.pp-card--locked,.pp-card--cancelled{background:#fff5f5}
.pp-card--warning{border-color:rgba(245,158,11,.45);background:rgba(245,158,11,.06)}
.pp-card__main{display:flex;align-items:flex-start;gap:12px;min-width:0}
.pp-card__num{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex:0 0 auto;background:var(--c-primary-100,#efe7ff);color:var(--c-primary,#7c3aed);font-size:var(--fs-sm);font-weight:800}
.pp-card__text{display:flex;flex-direction:column;gap:3px;min-width:0}
.pp-card__text strong{font-size:var(--fs-md);color:var(--c-text-1);line-height:1.25}
.pp-card__text span{font-size:var(--fs-sm);color:var(--c-text-3)}
.pp-card__bottom{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:auto}
.pp-card__reason{margin:0;color:var(--c-danger,#dc2626);font-size:var(--fs-xs);line-height:1.4;overflow-wrap:anywhere}
.pp-risks{display:flex;flex-wrap:wrap;gap:4px}
.pp-risk{max-width:100%;padding:2px 6px;border:1px solid rgba(245,158,11,.35);border-radius:var(--r-sm);background:rgba(245,158,11,.1);color:var(--c-text-2);font-size:var(--fs-xs);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media (max-width: 1020px){
  .pp-cards{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width: 620px){
  .pp-head{flex-direction:column}
  .pp-variant{max-width:none;width:100%}
  .pp-cards{grid-template-columns:1fr}
}
</style>
