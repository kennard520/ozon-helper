<script setup>
import { useWorkbenchStore } from '../../stores/workbench.js'
import { useAppStore } from '../../stores/app.js'
import { usePipeline } from '../../composables/usePipeline.js'
import SButton from '../../ui/SButton.vue'
import SBadge from '../../ui/SBadge.vue'

const wb = useWorkbenchStore()
const store = useAppStore()
const pipe = usePipeline(wb, store)

const emit = defineEmits(['publish-group'])

function prog(stepId) {
  return wb.stepProgress(stepId)
}
</script>
<template>
  <div class="pp-wrap">
    <!-- 头部 -->
    <div class="pp-header">
      <div class="pp-header__titles">
        <h2 class="pp-title">AI 智能上架工作台</h2>
        <p class="pp-subtitle">选择变体 → 跑流水线 → 合并发布</p>
      </div>
      <SButton
        variant="primary"
        :loading="!!pipe.batchRunningOp.value"
        @click="pipe.runAll()"
      >⚡ 一键跑完已选 ({{ wb.selectedVariantIds.size }})</SButton>
    </div>

    <!-- 已选提示 -->
    <div class="pp-sel-hint">{{ wb.selectedVariantIds.size }} 个变体已选中</div>

    <!-- 7 步列表 -->
    <div class="pp-steps">
      <div
        v-for="(step, i) in pipe.WF"
        :key="step.id"
        class="pp-step"
        :class="{ 'pp-step--running': pipe.stepStatus[step.id] === 'running' }"
      >
        <!-- 序号 + 元信息 -->
        <div class="pp-step__meta">
          <span class="pp-step__num">{{ i + 1 }}</span>
          <div class="pp-step__info">
            <span class="pp-step__label">{{ step.label }}</span>
            <span class="pp-step__eta">{{ step.eta }}</span>
          </div>
        </div>

        <!-- 进度徽标 -->
        <div class="pp-step__progress">
          <template v-if="prog(step.id).total > 0">
            <SBadge
              v-if="prog(step.id).done === prog(step.id).total"
              variant="success"
            >已完成 {{ prog(step.id).done }}/{{ prog(step.id).total }}</SBadge>
            <SBadge v-else variant="neutral">
              部分 {{ prog(step.id).done }}/{{ prog(step.id).total }}
            </SBadge>
          </template>
          <SBadge v-else variant="neutral">未开始</SBadge>
        </div>

        <!-- 动作按钮 -->
        <div class="pp-step__action">
          <SButton
            v-if="step.id === 'publish'"
            variant="ghost"
            size="sm"
            :disabled="!!pipe.batchRunningOp.value"
            @click="emit('publish-group')"
          >发布</SButton>
          <SButton
            v-else
            variant="ghost"
            size="sm"
            :loading="pipe.stepStatus[step.id] === 'running'"
            :disabled="!!pipe.batchRunningOp.value"
            @click="pipe.runStep(step.id)"
          >{{ prog(step.id).done > 0 ? '重跑' : '运行' }}</SButton>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.pp-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.pp-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  flex-wrap: wrap;
}
.pp-header__titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pp-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--c-text-1);
  margin: 0;
}
.pp-subtitle {
  font-size: var(--fs-sm);
  color: var(--c-text-3);
  margin: 0;
}
.pp-sel-hint {
  font-size: var(--fs-sm);
  color: var(--c-text-2);
  background: var(--c-bg);
  border-radius: var(--r-sm);
  padding: 6px 12px;
}
.pp-steps {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pp-step {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 10px 12px;
  border-radius: var(--r-md);
  border: 1px solid var(--c-border);
  background: #fff;
  transition: background .15s;
}
.pp-step--running {
  background: var(--c-primary-50, #f0f5ff);
  border-color: var(--c-primary-200, #bfcfff);
}
.pp-step__meta {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex: 1;
  min-width: 0;
}
.pp-step__num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--c-primary-100, #dce8ff);
  color: var(--c-primary);
  font-size: var(--fs-xs);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.pp-step__info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.pp-step__label {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-text-1);
}
.pp-step__eta {
  font-size: var(--fs-xs);
  color: var(--c-text-3);
}
.pp-step__progress {
  flex-shrink: 0;
}
.pp-step__action {
  flex-shrink: 0;
}
</style>
