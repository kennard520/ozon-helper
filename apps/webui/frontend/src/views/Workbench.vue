<script setup>
import { watch, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import { useDraftBatchOps } from '../composables/useDraftBatchOps.js'
import DraftListPane from '../components/workbench/DraftListPane.vue'
import VariantCardsPane from '../components/workbench/VariantCardsPane.vue'

const store = useAppStore()
const wb = useWorkbenchStore()
const ops = useDraftBatchOps(store)
// 顶层解构让模板可自动解包 ref（Vue 3 setup 顶层 ref 自动 unwrap）
const { publishResult, warehouses: draftWarehouses } = ops

watch(() => store.selectedId, (id) => wb.loadForDraft(id), { immediate: true })
onMounted(() => { store.loadDrafts(); ops.loadWarehouses() })
</script>
<template>
  <div class="wb-grid">
    <aside class="wb-left">
      <DraftListPane
        :drafts="store.filteredDrafts"
        :counts="store.counts"
        :filter="store.filter"
        :selected-id="store.selectedId"
        :warehouses="draftWarehouses"
        :total="store.total"
        :page="store.page"
        :page-size="store.pageSize"
        @refresh="store.loadDrafts()"
        @update:filter="store.setFilter"
        @select="(id) => store.selectedId = id"
        @page-change="store.setPage"
        @size-change="store.setPageSize"
        @delete="ops.doDelete"
        @batch-update="ops.doBatchUpdate"
        @batch-publish="ops.doBatchPublish"
      />
    </aside>
    <main class="wb-center">
      <div v-if="!store.selectedDraft" class="wb-empty">
        <div class="wb-empty__i">📦</div>
        <div class="wb-empty__t">选中左侧草稿后在此进入 AI 工作台</div>
      </div>
      <div v-else class="wb-center-content">
        <div class="wb-publish-bar">
          <el-button type="primary" size="small" @click="ops.doPublish(store.selectedDraft)">
            {{ store.selectedDraft.source === 'ozon' ? '同步回 Ozon' : '🚀 发布到 Ozon' }}
          </el-button>
          <div v-if="publishResult" class="wb-publish-result">
            <span v-if="publishResult.published" class="ok">● 已发布</span>
            <span v-for="(e, i) in (publishResult.errors || [])" :key="i" class="err">▲ {{ typeof e === 'string' ? e : JSON.stringify(e) }}</span>
          </div>
        </div>
        <div class="wb-center-placeholder">中栏(AI 工作台 + 详情)将在 F1c/F1d 实现</div>
      </div>
    </main>
    <aside class="wb-right">
      <VariantCardsPane @variant-deleted="store.loadDrafts()" />
    </aside>
  </div>
</template>
<style scoped>
.wb-grid{display:grid;grid-template-columns:360px 1fr 360px;gap:var(--sp-4);height:calc(100vh - 56px - var(--sp-5)*2)}
.wb-left,.wb-right{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden;display:flex;flex-direction:column}
.wb-center{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:auto;padding:var(--sp-5)}
.wb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--c-text-3)}
.wb-empty__i{font-size:40px;margin-bottom:12px;opacity:.7}
.wb-center-placeholder{color:var(--c-text-3);font-size:var(--fs-sm)}
.wb-center-content{display:flex;flex-direction:column;gap:var(--sp-3)}
.wb-publish-bar{display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap}
.wb-publish-result{display:flex;flex-wrap:wrap;gap:4px;font-size:var(--fs-sm)}
.wb-publish-result .ok{color:var(--c-success)}
.wb-publish-result .err{color:var(--c-danger)}
</style>
