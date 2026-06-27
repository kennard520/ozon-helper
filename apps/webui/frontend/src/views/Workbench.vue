<script setup>
import { ref, watch, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import DraftListPane from '../components/workbench/DraftListPane.vue'

const store = useAppStore()
const wb = useWorkbenchStore()
watch(() => store.selectedId, (id) => wb.loadForDraft(id), { immediate: true })
onMounted(() => store.loadDrafts())

const warehouses = ref([])
async function onDelete() {}
async function onBatchUpdate() {}
async function onBatchPublish() {}
</script>
<template>
  <div class="wb-grid">
    <aside class="wb-left">
      <DraftListPane
        :drafts="store.filteredDrafts"
        :counts="store.counts"
        :filter="store.filter"
        :selected-id="store.selectedId"
        :warehouses="warehouses"
        :total="store.total"
        :page="store.page"
        :page-size="store.pageSize"
        @refresh="store.loadDrafts()"
        @update:filter="store.setFilter"
        @select="(id) => store.selectedId = id"
        @page-change="store.setPage"
        @size-change="store.setPageSize"
        @delete="onDelete"
        @batch-update="onBatchUpdate"
        @batch-publish="onBatchPublish"
      />
    </aside>
    <main class="wb-center">
      <div v-if="!store.selectedDraft" class="wb-empty">
        <div class="wb-empty__i">📦</div>
        <div class="wb-empty__t">选中左侧草稿后在此进入 AI 工作台</div>
      </div>
      <div v-else class="wb-center-placeholder">中栏(AI 工作台 + 详情)将在 F1c/F1d 实现</div>
    </main>
    <aside class="wb-right"><!-- Task4: VariantCardsPane --></aside>
  </div>
</template>
<style scoped>
.wb-grid{display:grid;grid-template-columns:360px 1fr 360px;gap:var(--sp-4);height:calc(100vh - 56px - var(--sp-5)*2)}
.wb-left,.wb-right{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden;display:flex;flex-direction:column}
.wb-center{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:auto;padding:var(--sp-5)}
.wb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--c-text-3)}
.wb-empty__i{font-size:40px;margin-bottom:12px;opacity:.7}
.wb-center-placeholder{color:var(--c-text-3);font-size:var(--fs-sm)}
</style>
