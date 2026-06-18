<template>
  <div class="category-tree-select">
    <el-tree-select
      :model-value="selectedKey"
      :data="treeData"
      filterable
      clearable
      check-strictly
      :render-after-expand="false"
      node-key="value"
      placeholder="点选或搜索类目（只能选末级类型）"
      style="width:100%"
      @change="onSelectChange"
    />
    <div v-if="currentPath" class="cat-path">{{ currentPath }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ cat: '', type: '' }) },
})
const emit = defineEmits(['update:modelValue'])

const treeData = ref([])
const currentPath = ref('')

const selectedKey = computed(() => {
  if (props.modelValue && props.modelValue.cat && props.modelValue.type) {
    return `${props.modelValue.cat}-${props.modelValue.type}`
  }
  return ''
})

onMounted(async () => {
  try {
    const r = await api.categoryTree()
    treeData.value = r.tree || []
  } catch (e) {
    ElMessage.warning((e && e.message) || '类目树加载失败，请先在设置里配置 Ozon API')
  }
})

watch(() => props.modelValue, async (mv) => {
  if (!mv || !mv.cat || !mv.type) { currentPath.value = ''; return }
  if (mv.path) { currentPath.value = mv.path; return }
  try {
    const r = await api.categoryResolve(mv.cat, mv.type)
    const leaf = r.leaf || {}
    currentPath.value = leaf.path || leaf.type_name || `类目 ${mv.cat}-${mv.type}`
  } catch {
    currentPath.value = `类目 ${mv.cat}-${mv.type}`
  }
}, { immediate: true })

function findLabel(nodes, value) {
  for (const n of nodes || []) {
    if (n.value === value) return n.label
    if (n.children) {
      const got = findLabel(n.children, value)
      if (got) return got
    }
  }
  return ''
}

function onSelectChange(value) {
  if (!value) {
    emit('update:modelValue', { cat: '', type: '', path: '' })
    return
  }
  const [cat, type] = String(value).split('-')
  const label = findLabel(treeData.value, value)
  emit('update:modelValue', { cat, type, path: label || `${cat}-${type}` })
}

defineExpose({ treeData, currentPath, selectedKey, onSelectChange, findLabel })
</script>

<style scoped>
.cat-path { margin-top: 4px; font-size: 12px; color: var(--c-text-3); }
</style>
