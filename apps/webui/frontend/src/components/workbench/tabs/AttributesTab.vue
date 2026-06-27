<script setup>
import { ref, computed, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useAttributes } from '../../../composables/useAttributes.js'
import AttrField from '../AttrField.vue'
import { SButton, SAlert } from '../../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['saved'])
const draftRef = toRef(props, 'draft')
const a = useAttributes(draftRef)

const optionalOpen = ref(false)
const missingSet = computed(() => new Set(a.missingIds.value))

function onUpdate(def, val) { a.setValue(def.id, val) }

async function doAiFill() {
  const r = await a.aiFill()
  if (r && r.error) ElMessage.warning(`AI 填充失败：${r.error}`)
  else ElMessage.success(`AI 已填充 ${r.mapped_count ?? 0} 项`)
  emit('saved')
}
async function doSave() { await a.save(); emit('saved'); ElMessage.success('已保存') }
</script>

<template>
  <div class="attrs-tab">
    <div class="attrs-tab__bar">
      <SButton variant="primary" :loading="a.loading.value" @click="doAiFill">AI 填充特征</SButton>
      <SButton @click="doSave">保存</SButton>
    </div>

    <SAlert v-if="a.missingIds.value.length" variant="warn" :title="`还缺 ${a.missingIds.value.length} 项必填特征`" />

    <div v-if="a.groups.value.aspects.length" class="attrs-tab__group">
      <div class="attrs-tab__glabel">区别特征（变体维度）— 合并成一张卡时各变体靠它区分</div>
      <AttrField
        v-for="def in a.groups.value.aspects" :key="def.id" :def="def"
        :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
        :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="missingSet.has(def.id)"
        @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
      />
    </div>

    <div v-if="a.groups.value.required.length" class="attrs-tab__group">
      <div class="attrs-tab__glabel">必填（{{ a.groups.value.required.length }}）</div>
      <AttrField
        v-for="def in a.groups.value.required" :key="def.id" :def="def"
        :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
        :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="missingSet.has(def.id)"
        @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
      />
      <div class="attrs-tab__hint">品牌在「商品信息」tab 填。</div>
    </div>

    <div v-if="a.groups.value.optional.length" class="attrs-tab__group">
      <SButton size="sm" @click="optionalOpen = !optionalOpen">
        {{ optionalOpen ? '收起可选项' : `展开可选项（${a.groups.value.optional.length}）` }}
      </SButton>
      <template v-if="optionalOpen">
        <AttrField
          v-for="def in a.groups.value.optional" :key="def.id" :def="def"
          :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
          :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="false"
          @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
        />
      </template>
    </div>

    <div v-if="!a.groups.value.aspects.length && !a.groups.value.required.length && !a.groups.value.optional.length"
         class="attrs-tab__empty">先在「商品信息」tab 选好类目，再填特征。</div>
  </div>
</template>

<style scoped>
.attrs-tab{padding:var(--sp-3,12px)}
.attrs-tab__bar{display:flex;gap:var(--sp-2,8px);margin-bottom:var(--sp-3,12px)}
.attrs-tab__group{margin-top:var(--sp-4,16px)}
.attrs-tab__glabel{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555);margin-bottom:var(--sp-2,8px)}
.attrs-tab__hint,.attrs-tab__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888);margin-top:var(--sp-2,8px)}
</style>
