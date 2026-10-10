<template>
  <div class="category-select">
    <el-select
      :model-value="selectedKey"
      :loading="loading"
      :remote-method="search"
      filterable
      remote
      clearable
      reserve-keyword
      placeholder="搜索类目或类型"
      style="width:100%"
      @change="onSelectChange"
      @focus="ensureInitialOptions"
    >
      <el-option
        v-for="item in options"
        :key="item.value"
        :label="item.label"
        :value="item.value"
      >
        <div class="cat-option">
          <span class="cat-option__name">{{ item.name }}</span>
          <span class="cat-option__path">{{ item.path }}</span>
        </div>
      </el-option>
    </el-select>
    <div v-if="currentPath" class="cat-path">{{ currentPath }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ cat: '', type: '' }) },
})
const emit = defineEmits(['update:modelValue'])

const options = ref([])
const currentPath = ref('')
const loading = ref(false)
let searchSeq = 0

const selectedKey = computed(() => {
  if (props.modelValue && props.modelValue.cat && props.modelValue.type) {
    return `${props.modelValue.cat}-${props.modelValue.type}`
  }
  return ''
})

function toOption(item) {
  const cat = item.description_category_id ?? item.cat ?? item.category_id
  const type = item.type_id ?? item.type
  const name = item.type_name || item.name || item.label || ''
  const path = item.path || name || `类目 ${cat}-${type}`
  return {
    value: `${cat}-${type}`,
    cat: String(cat ?? ''),
    type: String(type ?? ''),
    name,
    path,
    label: path,
  }
}

function mergeOption(option) {
  if (!option.cat || !option.type) return
  const next = options.value.filter((x) => x.value !== option.value)
  options.value = [option, ...next].slice(0, 80)
}

async function resolveCurrent(mv) {
  if (!mv || !mv.cat || !mv.type) {
    currentPath.value = ''
    return
  }
  if (mv.path) {
    currentPath.value = mv.path
    mergeOption(toOption({ description_category_id: mv.cat, type_id: mv.type, path: mv.path }))
    return
  }
  try {
    const r = await api.categoryResolve(mv.cat, mv.type)
    const leaf = r.leaf || {}
    const option = toOption({
      description_category_id: mv.cat,
      type_id: mv.type,
      type_name: leaf.type_name,
      path: leaf.path || leaf.type_name || `类目 ${mv.cat}-${mv.type}`,
    })
    currentPath.value = option.path
    mergeOption(option)
  } catch {
    currentPath.value = `类目 ${mv.cat}-${mv.type}`
    mergeOption(toOption({ description_category_id: mv.cat, type_id: mv.type, path: currentPath.value }))
  }
}

async function search(query) {
  const q = String(query || '').trim()
  const seq = ++searchSeq
  loading.value = true
  try {
    const r = await api.categorySearch(q, 50)
    if (seq !== searchSeq) return
    options.value = (r.results || [])
      .map(toOption)
      .filter((x) => x.cat && x.type)
  } catch (e) {
    if (seq === searchSeq) {
      ElMessage.warning((e && e.message) || '类目搜索失败，请先在设置里配置 Ozon API')
    }
  } finally {
    if (seq === searchSeq) loading.value = false
  }
}

function ensureInitialOptions() {
  if (!options.value.length) search('')
}

watch(() => props.modelValue, resolveCurrent, { immediate: true })

function onSelectChange(value) {
  if (!value) {
    emit('update:modelValue', { cat: '', type: '', path: '' })
    return
  }
  const option = options.value.find((x) => x.value === value)
  const [cat, type] = String(value).split('-')
  emit('update:modelValue', { cat, type, path: option?.path || `${cat}-${type}` })
}

defineExpose({ options, currentPath, selectedKey, search, onSelectChange })
</script>

<style scoped>
.cat-path {
  margin-top: 4px;
  font-size: 12px;
  color: var(--c-text-3);
}

.cat-option {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.cat-option__name {
  color: var(--c-text);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cat-option__path {
  color: var(--c-text-3);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
