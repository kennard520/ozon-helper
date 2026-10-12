<template>
  <el-dialog
    :model-value="modelValue"
    title="从 Ozon SKU 导入商品"
    width="720px"
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <div class="ozon-import-dialog">
      <div class="sku-row">
        <div class="sku-field">
          <label class="sku-label" for="ozon-sku-input">Ozon SKU</label>
          <el-input
            id="ozon-sku-input"
            v-model="sku"
            class="sku-input"
            aria-label="Ozon SKU"
            :disabled="state === 'loading'"
            placeholder="输入数字 SKU，例如 4998185789"
            @keyup.enter="submitImport"
          />
        </div>
        <el-button
          class="sku-submit"
          type="primary"
          :loading="state === 'loading' && activeAction === 'import'"
          :disabled="submitDisabled"
          @click="submitImport"
        >导入</el-button>
      </div>

      <p class="store-context" :class="{ 'is-missing': !storeClientId }">
        {{ storeClientId ? `当前店铺：${storeClientId}` : '请先选择当前店铺后再导入或同步' }}
      </p>

      <div v-if="state === 'loading'" class="state-message is-loading" role="status" aria-live="polite">
        {{ activeAction === 'sync' ? '正在同步当前店铺商品…' : '正在导入 Ozon 商品…' }}
      </div>

      <div v-else-if="state === 'error'" class="state-message is-error" role="alert" aria-live="assertive">
        <div>{{ errorMessage }}</div>
        <template v-if="completedAction === 'sync'">
          <div class="sync-count">失败 {{ syncFailed }} 个</div>
          <ul v-if="syncErrors.length" class="error-list">
            <li v-for="error in syncErrors" :key="error">{{ error }}</li>
          </ul>
        </template>
      </div>

      <template v-else-if="state === 'conflicts'">
        <div class="conflicts-state" role="status" aria-live="polite">
          <div class="state-message is-warning">
            本地草稿与 Ozon 数据存在冲突。仅勾选需要用远端值覆盖的字段。
          </div>
          <ul v-if="warnings.length" class="warning-list">
            <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
          </ul>
          <div class="conflict-list">
            <div v-for="conflict in conflicts" :key="conflict.field" class="conflict-row">
              <el-checkbox v-model="selectedFields[conflict.field]" class="conflict-checkbox">
                {{ conflict.field }}
              </el-checkbox>
              <div class="conflict-value">
                <span class="value-label">本地</span>
                <pre>{{ displayValue(conflict.local) }}</pre>
              </div>
              <div class="conflict-value">
                <span class="value-label">Ozon</span>
                <pre>{{ displayValue(conflict.remote) }}</pre>
              </div>
            </div>
          </div>
          <el-button class="apply-conflicts" type="primary" @click="applyConflicts">
            应用选中字段
          </el-button>
        </div>
      </template>

      <template v-else-if="state === 'done'">
        <div class="state-message is-done" role="status" aria-live="polite">
          <template v-if="completedAction === 'sync'">
            <div>
              {{ syncFailed > 0 ? '同步部分完成' : '同步完成' }}：共拉取 {{ syncResult.pulled ?? 0 }} 个商品，新增 {{ syncResult.created ?? 0 }} 个，更新 {{ syncResult.updated ?? 0 }} 个，保留 {{ syncResult.preserved ?? 0 }} 个，失败 {{ syncFailed }} 个。
            </div>
            <ul v-if="syncErrors.length" class="error-list">
              <li v-for="error in syncErrors" :key="error">{{ error }}</li>
            </ul>
          </template>
          <template v-else>
            <div>{{ importResult.created ? '商品已导入为新草稿' : '本地草稿已更新' }}。</div>
          </template>
          <template v-if="warnings.length">
            <ul class="warning-list">
              <li v-for="warning in warnings" :key="warning">{{ warning }}</li>
            </ul>
          </template>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button
        class="sync-store"
        :loading="state === 'loading' && activeAction === 'sync'"
        :disabled="!storeClientId || state === 'loading'"
        @click="syncCurrentStore"
      >同步当前店铺</el-button>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../../api.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  storeClientId: { type: [String, Number], default: '' },
})
const emit = defineEmits(['update:modelValue', 'imported'])

const sku = ref('')
const state = ref('idle')
const activeAction = ref('')
const completedAction = ref('')
const errorMessage = ref('')
const conflicts = ref([])
const warnings = ref([])
const selectedFields = reactive({})
const importResult = ref({})
const syncResult = ref({})

const submitDisabled = computed(() => !String(props.storeClientId || '').trim() || state.value === 'loading')
const syncFailed = computed(() => Number(syncResult.value.failed || 0))
const syncErrors = computed(() => {
  const resultErrors = Array.isArray(syncResult.value.errors) ? syncResult.value.errors : []
  if (syncFailed.value > 0) return resultErrors
  const warningSet = new Set(warnings.value)
  return resultErrors.filter((error) => !warningSet.has(error))
})

function reset() {
  sku.value = ''
  state.value = 'idle'
  activeAction.value = ''
  completedAction.value = ''
  errorMessage.value = ''
  conflicts.value = []
  warnings.value = []
  importResult.value = {}
  syncResult.value = {}
  for (const field of Object.keys(selectedFields)) delete selectedFields[field]
}

watch(() => props.modelValue, (open) => {
  if (open) reset()
}, { immediate: true })

function normalizedSku() {
  const value = String(sku.value || '').trim()
  const number = Number(value)
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(number) || number <= 0) {
    state.value = 'error'
    errorMessage.value = 'SKU 必须是正整数'
    return ''
  }
  return value
}

function showConflicts(result) {
  conflicts.value = result.conflicts || []
  for (const field of Object.keys(selectedFields)) delete selectedFields[field]
  for (const conflict of conflicts.value) selectedFields[conflict.field] = false
  state.value = 'conflicts'
}

function finishImport(result) {
  importResult.value = result
  completedAction.value = 'import'
  state.value = 'done'
  emit('imported', {
    draft: result.draft,
    created: Boolean(result.created),
    warnings: result.warnings || [],
  })
  emit('update:modelValue', false)
}

async function runImport(selected_fields) {
  const value = normalizedSku()
  if (!value || !String(props.storeClientId || '').trim()) return

  activeAction.value = 'import'
  errorMessage.value = ''
  state.value = 'loading'
  try {
    const result = await api.importOzonBySku(value, String(props.storeClientId), selected_fields)
    warnings.value = result.warnings || []
    if (selected_fields === undefined && result.conflicts && result.conflicts.length) {
      showConflicts(result)
      return
    }
    finishImport(result)
  } catch (error) {
    errorMessage.value = String(error && error.message ? error.message : error)
    state.value = 'error'
  }
}

function submitImport() {
  return runImport(undefined)
}

function applyConflicts() {
  const fields = conflicts.value
    .map((conflict) => conflict.field)
    .filter((field) => selectedFields[field])
  return runImport(fields)
}

async function syncCurrentStore() {
  const storeClientId = String(props.storeClientId || '').trim()
  if (!storeClientId) return

  activeAction.value = 'sync'
  errorMessage.value = ''
  state.value = 'loading'
  try {
    syncResult.value = await api.syncOzonProducts(storeClientId)
    completedAction.value = 'sync'
    warnings.value = syncResult.value.warnings || []
    if (syncFailed.value > 0 && Number(syncResult.value.pulled || 0) === 0) {
      errorMessage.value = '同步失败：未成功同步任何商品。'
      state.value = 'error'
      return
    }
    state.value = 'done'
  } catch (error) {
    errorMessage.value = String(error && error.message ? error.message : error)
    state.value = 'error'
  }
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

defineExpose({
  sku,
  state,
  conflicts,
  warnings,
  selectedFields,
  submitImport,
  applyConflicts,
  syncCurrentStore,
})
</script>

<style scoped>
.ozon-import-dialog { display: flex; flex-direction: column; gap: 14px; }
.sku-row { display: flex; gap: 10px; align-items: flex-end; }
.sku-field { display: flex; flex: 1; flex-direction: column; gap: 5px; }
.sku-label { color: var(--c-text-2); font-size: 13px; font-weight: 600; }
.sku-input { width: 100%; }
.store-context { margin: 0; color: var(--c-text-3); font-size: 13px; }
.store-context.is-missing { color: var(--el-color-danger); }
.state-message { border-radius: 6px; padding: 10px 12px; }
.state-message.is-loading { background: var(--el-color-primary-light-9); color: var(--el-color-primary); }
.state-message.is-error { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }
.state-message.is-warning { background: var(--el-color-warning-light-9); color: var(--el-color-warning-dark-2); }
.state-message.is-done { background: var(--el-color-success-light-9); color: var(--el-color-success); }
.warning-list { margin: 0; padding-left: 20px; color: var(--el-color-warning-dark-2); }
.error-list { margin: 6px 0 0; padding-left: 20px; }
.sync-count { margin-top: 6px; font-weight: 600; }
.conflicts-state { display: flex; flex-direction: column; gap: 14px; }
.conflict-list { display: flex; flex-direction: column; gap: 10px; }
.conflict-row { display: grid; grid-template-columns: 140px 1fr 1fr; gap: 10px; align-items: start; padding: 10px; border: 1px solid var(--el-border-color); border-radius: 6px; }
.conflict-value { min-width: 0; }
.value-label { display: block; margin-bottom: 4px; color: var(--c-text-3); font-size: 12px; }
.conflict-value pre { margin: 0; padding: 8px; overflow-wrap: anywhere; white-space: pre-wrap; background: var(--el-fill-color-light); border-radius: 4px; font: inherit; font-size: 13px; }
.apply-conflicts { align-self: flex-end; }
</style>
