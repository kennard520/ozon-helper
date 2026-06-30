<script setup>
import { computed } from 'vue'
import { ElSelect, ElOption, ElInput } from 'element-plus'

const props = defineProps({
  def: { type: Object, required: true },
  modelValue: { type: Array, default: () => [] },   // canonical [{dictionary_value_id?, value}]
  options: { type: Array, default: () => [] },        // [{id, value}]
  loading: { type: Boolean, default: false },
  oversized: { type: Boolean, default: false },
  missing: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'ensure', 'search'])

const isDict = computed(() => Number(props.def.dictionary_id) > 0)
const multiple = computed(() => !!props.def.is_collection)

// 下拉选中态：单选=标量 id，多选=id 数组
const selected = computed(() => {
  const ids = (props.modelValue || []).map((v) => v.dictionary_value_id).filter((x) => x != null)
  return multiple.value ? ids : (ids[0] ?? '')
})
// 文本态
const textVal = computed(() => (props.modelValue || []).map((v) => v.value || '').filter(Boolean).join(' , '))

function optById(id) {
  const o = props.options.find((x) => x.id === id)
  return o ? { dictionary_value_id: o.id, value: o.value } : { dictionary_value_id: id, value: String(id) }
}
function onPick(val) {
  const ids = Array.isArray(val) ? val : (val == null || val === '' ? [] : [val])
  emit('update:modelValue', ids.map(optById))
}
function onText(v) {
  const t = String(v || '').trim()
  emit('update:modelValue', t ? [{ value: t }] : [])
}
</script>

<template>
  <div class="attr-field" :class="{ 'attr-field--missing': missing }">
    <label class="attr-field__label">
      <span v-if="def.is_required" class="attr-field__req">*</span>{{ def.name }}
    </label>
    <ElSelect
      v-if="isDict"
      :model-value="selected"
      :multiple="multiple"
      :multiple-limit="def.max_value_count || 0"
      filterable clearable
      :remote="oversized"
      :remote-method="(q) => emit('search', q)"
      :loading="loading"
      placeholder="选择或搜索"
      style="width:100%"
      @visible-change="(open) => open && emit('ensure')"
      @change="onPick"
    >
      <ElOption v-for="o in options" :key="o.id" :label="o.value" :value="o.id" />
    </ElSelect>
    <ElInput v-else :model-value="textVal" placeholder="填写" @input="onText" @change="onText" />
  </div>
</template>

<style scoped>
.attr-field{margin-bottom:var(--sp-3, 12px)}
.attr-field__label{display:block;font-size:var(--fs-sm,13px);color:var(--c-text-2,#555);margin-bottom:4px}
.attr-field__req{color:var(--c-danger,#e5484d);margin-right:2px}
.attr-field--missing :deep(.el-select),.attr-field--missing :deep(.el-input){outline:1px solid var(--c-danger,#e5484d);border-radius:6px}
</style>
