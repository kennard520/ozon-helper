<template>
  <el-select
    :model-value="selectedId"
    filterable
    remote
    clearable
    :remote-method="debouncedSearch"
    :loading="loading"
    :disabled="!cat || !type"
    :placeholder="!cat || !type ? '先选类目' : '输入品牌名称（≥2字符）'"
    @change="onSelectChange"
  >
    <el-option
      v-for="opt in displayOptions"
      :key="opt.id"
      :label="opt.value"
      :value="opt.id"
    />
  </el-select>
</template>

<script setup>
import { ref, computed } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  cat: { default: null },
  type: { default: null },
  modelValue: {
    type: Object,
    default: () => null
  }
})
const emit = defineEmits(['update:modelValue'])

const options = ref([])
const loading = ref(false)
const hint = ref('')

const selectedId = computed(() => {
  const mv = props.modelValue || {}
  if (mv.brand_id != null && mv.brand_id !== '') return mv.brand_id
  return mv.brand_name ? `name:${mv.brand_name}` : null
})

// 选项里没有当前品牌时，补一个带品牌名标签的合成项，避免显示 brand_id 数字
const displayOptions = computed(() => {
  const opts = options.value || []
  const mv = props.modelValue
  if (mv && mv.brand_name && (mv.brand_id == null || mv.brand_id === '')) {
    return [{ id: `name:${mv.brand_name}`, value: mv.brand_name }, ...opts]
  }
  if (mv && mv.brand_id != null && !opts.some((o) => o.id === mv.brand_id)) {
    return [{ id: mv.brand_id, value: mv.brand_name || String(mv.brand_id) }, ...opts]
  }
  return opts
})

async function onSearch(q) {
  if (!props.cat || !props.type) {
    return
  }
  if (!q || q.length < 2) {
    hint.value = '至少输入2个字符'
    return
  }
  hint.value = ''
  loading.value = true
  try {
    const r = await api.attributeValues(props.cat, props.type, 85, q)
    options.value = r.result || []
  } finally {
    loading.value = false
  }
}

function choose(opt) {
  emit('update:modelValue', {
    brand_id: opt.id,
    brand_name: opt.value
  })
}

function onSelectChange(id) {
  if (id == null || id === '') {     // clearable 清空 → 真正清掉品牌
    emit('update:modelValue', { brand_id: null, brand_name: '' })
    return
  }
  if (typeof id === 'string' && id.startsWith('name:')) {
    emit('update:modelValue', { brand_id: null, brand_name: id.slice(5) })
    return
  }
  const opt = options.value.find(o => o.id === id)
  if (opt) choose(opt)
}

// Debounced wrapper for template binding (220ms)
let _debounceTimer = null
function debouncedSearch(q) {
  clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => onSearch(q), 220)
}

defineExpose({ onSearch, choose, onSelectChange, options, hint })
</script>
