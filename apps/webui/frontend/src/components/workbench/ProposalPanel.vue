<script setup>
import { toRef } from 'vue'
import { ElInput, ElMessage } from 'element-plus'
import { useProposal } from '../../composables/useProposal.js'
import { SButton, SBadge } from '../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['applied'])
const draftRef = toRef(props, 'draft')
const p = useProposal(draftRef, { onApplied: (r) => emit('applied', r) })

async function doGen(mode) {
  try { await p.generate(mode); ElMessage.success('已生成草案') }
  catch (e) { ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`) }
}
async function doApply() {
  try {
    const r = await p.apply()
    if (r && r.unmapped && r.unmapped.length) ElMessage.warning(`${r.unmapped.length} 项未匹配字典，请在特征 tab 手动确认`)
    else ElMessage.success('已应用到商品')
  } catch (e) { ElMessage.warning(`应用失败：${e && e.message ? e.message : e}`) }
}
async function doDiscard() {
  try { await p.discard(); ElMessage.success('已放弃草案') }
  catch (e) { ElMessage.warning(`放弃失败：${e && e.message ? e.message : e}`) }
}
</script>

<template>
  <section class="prop">
    <!-- 空态 -->
    <div v-if="!p.hasProposal.value" class="prop__empty">
      <span class="prop__title">AI 文案草案</span>
      <SButton size="sm" variant="primary" :loading="p.loading.value" @click="doGen('full')">生成草案</SButton>
      <SButton size="sm" :loading="p.loading.value" @click="doGen('copy')">快速文案</SButton>
    </div>

    <!-- 审阅态 -->
    <div v-else class="prop__body">
      <div class="prop__head">
        <span class="prop__title">AI 待确认草案</span>
        <SButton size="sm" variant="primary" :loading="p.loading.value" @click="doApply">应用到商品</SButton>
        <SButton size="sm" @click="doDiscard">放弃</SButton>
        <SButton size="sm" @click="doGen('full')">重新生成</SButton>
      </div>

      <div class="prop__field">
        <label>俄语标题</label>
        <ElInput :model-value="(p.proposal.value.fields || {}).ozon_title || ''" @change="(v) => p.editField('ozon_title', v)" />
      </div>
      <div class="prop__field">
        <label>简介</label>
        <ElInput type="textarea" :autosize="{ minRows: 3, maxRows: 12 }"
          :model-value="(p.proposal.value.fields || {}).description || ''" @change="(v) => p.editField('description', v)" />
      </div>
      <div class="prop__field">
        <label>标签 #Хештеги</label>
        <ElInput :model-value="p.tags.value" @change="(v) => p.editTags(v)" />
      </div>

      <div v-if="p.aiAttrs.value.length" class="prop__attrs">
        <div class="prop__sub">AI 属性</div>
        <div v-for="a in p.aiAttrs.value" :key="a.id" class="prop__attr">
          <span class="prop__attr-name">{{ a.name }}</span>
          <ElInput :model-value="a.value" size="small" @change="(v) => p.editAttr(a.id, v)" />
          <SButton size="sm" @click="p.deleteAttr(a.id)">删</SButton>
        </div>
      </div>

      <div v-if="p.missingAttrs.value.length" class="prop__attrs">
        <div class="prop__sub">缺失必填（请补）</div>
        <div v-for="a in p.missingAttrs.value" :key="a.id" class="prop__attr">
          <span class="prop__attr-name"><SBadge variant="warn">必填</SBadge>{{ a.name }}</span>
          <ElInput :model-value="a.value" size="small" placeholder="补填" @change="(v) => p.editAttr(a.id, v)" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.prop{border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);background:var(--c-primary-50,#faf7ff);padding:var(--sp-3,12px);margin-bottom:var(--sp-4,16px)}
.prop__empty,.prop__head{display:flex;align-items:center;gap:var(--sp-2,8px)}
.prop__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.prop__field{margin-top:var(--sp-3,12px)}
.prop__field label{display:block;font-size:var(--fs-sm,13px);color:var(--c-text-2,#555);margin-bottom:4px}
.prop__attrs{margin-top:var(--sp-3,12px)}
.prop__sub{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555);margin-bottom:6px}
.prop__attr{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:6px}
.prop__attr-name{min-width:120px;font-size:var(--fs-sm,13px);display:flex;align-items:center;gap:4px}
</style>
