<script setup>
import { useWorkbenchStore, variantColor, variantColorName } from '../../stores/workbench.js'
import { useAppStore } from '../../stores/app.js'
import { usePipeline } from '../../composables/usePipeline.js'
import SButton from '../../ui/SButton.vue'
import SBadge from '../../ui/SBadge.vue'

const wb = useWorkbenchStore()
const store = useAppStore()
const pipe = usePipeline(wb, store)

const emit = defineEmits(['publish-one'])

function stepState(stepId) {
  if (pipe.stepStatus[stepId] === 'running') return 'running'
  if (pipe.stepStatus[stepId] === 'submitted') return 'submitted'
  if (pipe.stepLocked(stepId)) return 'locked'
  if (wb.currentStepDone(stepId)) return 'done'
  return 'idle'
}

function isLocked(stepId) {
  return stepId !== 'publish' && pipe.stepLocked(stepId)
}

function isPollingStep(stepId) {
  if (stepId !== 'content') return false
  if (pipe.stepStatus.content === 'submitted') return true
  const status = pipe.textJob.value && pipe.textJob.value.status
  return !!status && status !== 'done' && status !== 'failed'
}

function statusText(step) {
  if (isLocked(step.id)) return '待前置步骤'
  if (step.id === 'content' && pipe.stepStatus[step.id] === 'submitted') return '生成中（已提交，轮询中）'
  if (step.id === 'content' && pipe.textJob.value && pipe.textJob.value.status === 'running') {
    return `生成中（${pipe.textJob.value.current_step || '后台'}）`
  }
  if (step.id === 'content' && pipe.textJob.value && pipe.textJob.value.status === 'failed') return '生成失败'
  if (wb.currentStepDone(step.id)) return '已完成 ✓'
  return '未开始'
}

function statusVariant(step) {
  if (step.id === 'content' && pipe.textJob.value && pipe.textJob.value.status === 'failed') return 'danger'
  if (wb.currentStepDone(step.id)) return 'success'
  return 'neutral'
}
</script>

<template>
  <div class="pp-wrap">
    <div class="pp-header">
      <div class="pp-header__titles">
        <h2 class="pp-title">AI 智能上架工作台</h2>
        <p class="pp-subtitle">选择变体 → 跑流水线 → 合并发布</p>
      </div>
    </div>

    <div class="pp-ctx" :class="{ 'pp-ctx--empty': !wb.currentVariant }">
      <template v-if="wb.currentVariant">
        <span class="pp-ctx__dot" :style="{ background: variantColor(wb.currentVariant) }"></span>
        <span class="pp-ctx__text">正在操作:{{ wb.currentVariant.spec || variantColorName(wb.currentVariant) || '当前变体' }}</span>
      </template>
      <template v-else>
        <span class="pp-ctx__text">请在上方选择一个变体</span>
      </template>
    </div>

    <div class="pp-steps">
      <div
        v-for="(step, i) in pipe.WF"
        :key="step.id"
        class="pp-step"
        :class="[`pp-step--${stepState(step.id)}`]"
      >
        <span v-if="isPollingStep(step.id)" class="pp-step__spinner" aria-label="轮询状态"></span>
        <div class="pp-step__meta">
          <span class="pp-step__num" :class="`pp-step__num--${stepState(step.id)}`">
            <template v-if="stepState(step.id) === 'done'">✓</template>
            <template v-else-if="stepState(step.id) === 'locked'">!</template>
            <template v-else>{{ i + 1 }}</template>
          </span>
          <div class="pp-step__info">
            <span class="pp-step__label">{{ step.label }}</span>
            <span class="pp-step__eta">{{ step.eta }}</span>
          </div>
        </div>

        <div class="pp-step__foot">
          <div class="pp-step__progress">
            <SBadge :variant="statusVariant(step)">{{ statusText(step) }}</SBadge>
          </div>

          <div class="pp-step__action">
            <SButton
              v-if="step.id === 'publish'"
              variant="ghost"
              size="sm"
              :disabled="!!pipe.batchRunningOp.value"
              @click="emit('publish-one')"
            >发布</SButton>
            <SButton
              v-else
              variant="ghost"
              size="sm"
              :loading="pipe.stepStatus[step.id] === 'running'"
              :disabled="!!pipe.batchRunningOp.value || isLocked(step.id)"
              @click="pipe.runStep(step.id)"
            >{{ isLocked(step.id) ? '锁定' : (wb.currentStepDone(step.id) ? '重跑' : '运行') }}</SButton>
          </div>
        </div>
      </div>
    </div>
    <div v-if="pipe.textJob.value && pipe.textJob.value.status === 'failed' && pipe.textJob.value.error" class="pp-error">
      {{ pipe.textJob.value.error }}
    </div>
  </div>
</template>

<style scoped>
.pp-wrap{display:flex;flex-direction:column;gap:var(--sp-4)}
.pp-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp-3);flex-wrap:wrap}
.pp-header__titles{display:flex;flex-direction:column;gap:2px}
.pp-title{font-size:var(--fs-lg);font-weight:700;color:var(--c-text-1);margin:0}
.pp-subtitle{font-size:var(--fs-sm);color:var(--c-text-3);margin:0}
.pp-ctx{display:flex;align-items:center;gap:var(--sp-3);background:var(--c-primary-50);border:1px solid var(--c-primary-200);border-radius:var(--r-sm);padding:8px 14px}
.pp-ctx__dot{width:14px;height:14px;border-radius:50%;flex-shrink:0;box-shadow:0 0 0 1px rgba(0,0,0,.08) inset}
.pp-ctx__text{font-size:var(--fs-sm);color:var(--c-text-2)}
.pp-ctx--empty{background:var(--c-bg);border-color:var(--c-border)}
.pp-ctx--empty .pp-ctx__text{color:var(--c-text-4)}
.pp-steps{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:var(--sp-2)}
.pp-step{position:relative;display:flex;flex-direction:column;align-items:stretch;gap:var(--sp-2);padding:10px 12px;border-radius:var(--r-md);border:1px solid var(--c-border);background:#fff;transition:background .15s}
.pp-step__spinner{position:absolute;top:8px;right:8px;width:16px;height:16px;border-radius:50%;border:2px solid var(--c-primary-100,#dce8ff);border-top-color:var(--c-primary,#2563eb);animation:pp-spin .8s linear infinite}
@keyframes pp-spin{to{transform:rotate(360deg)}}
.pp-step--running,.pp-step--submitted{background:var(--c-primary-50,#f0f5ff);border-color:var(--c-primary-200,#bfcfff)}
.pp-step--locked{background:var(--c-bg);border-color:var(--c-border)}
.pp-step--locked .pp-step__label{color:var(--c-text-3)}
.pp-step__meta{display:flex;align-items:center;gap:var(--sp-3);min-width:0}
.pp-step__num{width:22px;height:22px;border-radius:50%;background:var(--c-primary-100,#dce8ff);color:var(--c-primary);font-size:var(--fs-xs);font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;border:1px solid transparent;transition:background .15s,color .15s,border-color .15s}
.pp-step__num--done{background:var(--c-success-bg);color:var(--c-success)}
.pp-step__num--running,.pp-step__num--submitted{background:var(--c-primary);color:var(--c-white);animation:pp-pulse 1.2s ease-in-out infinite}
.pp-step__num--locked{background:var(--c-bg);color:var(--c-text-4);border-color:var(--c-border)}
@keyframes pp-pulse{0%,100%{box-shadow:0 0 0 0 var(--c-primary-200)}50%{box-shadow:0 0 0 5px transparent}}
.pp-step__info{display:flex;flex-direction:column;gap:1px;min-width:0}
.pp-step__label{font-size:var(--fs-md);font-weight:600;color:var(--c-text-1)}
.pp-step__eta{font-size:var(--fs-xs);color:var(--c-text-3)}
.pp-step__progress,.pp-step__action{flex-shrink:0}
.pp-step__foot{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-2);margin-top:auto}
.pp-error{border:1px solid var(--c-danger,#dc2626);background:#fff5f5;color:var(--c-danger,#dc2626);border-radius:var(--r-sm);padding:8px 12px;font-size:var(--fs-sm);overflow-wrap:anywhere}
</style>
