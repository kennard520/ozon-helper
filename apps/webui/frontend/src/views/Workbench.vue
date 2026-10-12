<script setup>
import { watch, onMounted, computed, ref } from 'vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import { useDraftBatchOps } from '../composables/useDraftBatchOps.js'
import DraftListPane from '../components/workbench/DraftListPane.vue'
import VariantGroupBar from '../components/workbench/VariantGroupBar.vue'
import PipelinePanel from '../components/workbench/PipelinePanel.vue'
import DetailTabs from '../components/workbench/DetailTabs.vue'
import OzonImportDialog from '../components/workbench/OzonImportDialog.vue'

const store = useAppStore()
const wb = useWorkbenchStore()
const ops = useDraftBatchOps(store)
const ozonImportOpen = ref(false)
// 顶层解构让模板可自动解包 ref（Vue 3 setup 顶层 ref 自动 unwrap）
const { publishResult, warehouses: draftWarehouses } = ops

watch(() => store.selectedId, (id) => wb.loadForDraft(id), { immediate: true })
onMounted(() => { store.loadDrafts(); ops.loadWarehouses() })

const publishTarget = computed(() => wb.currentVariant || store.selectedDraft)
const variantWarning = computed(() => String(
  store.selectedDraft?.source_raw?.ozon_sync?.variant_warning || '',
).trim())

async function handleOzonImported(result) {
  const draft = result?.draft
  if (draft?.id == null) return
  const originStore = String(store.currentStore || '')
  store.filter = 'all'
  store.page = 1
  const refreshed = await store.loadDrafts()
  if (!refreshed || String(store.currentStore || '') !== originStore) return
  if (store.adoptDraft(draft)) store.selectedId = draft.id
}

// 来源链接：优先采购链接，1688 回退 source_url
function sourceLink(d) {
  if (!d) return ''
  const u = (d.purchase_url || '').trim()
  if (u) return u
  if (d.source_platform === '1688') return (d.source_url || '').trim()
  return (d.source_url || '').trim()
}
</script>
<template>
  <div class="wb-page">
    <div class="wb-toolbar">
      <el-button type="primary" size="small" @click="ozonImportOpen = true">从 Ozon 导入</el-button>
    </div>
    <OzonImportDialog
      v-model="ozonImportOpen"
      :store-client-id="store.currentStore"
      @imported="handleOzonImported"
    />
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
    <main class="wb-main">
      <div v-if="!store.selectedDraft" class="wb-empty">
        <div class="wb-empty__i">📦</div>
        <div class="wb-empty__t">选中左侧草稿后在此进入 AI 工作台</div>
      </div>
      <template v-else>
        <!-- 顶:来源商品链接 -->
        <section v-if="store.selectedDraft.source_title || sourceLink(store.selectedDraft)" class="wb-source">
          <span class="wb-source__t" :title="store.selectedDraft.source_title">{{ store.selectedDraft.source_title || '来源商品' }}</span>
          <a v-if="sourceLink(store.selectedDraft)" class="wb-source__lk"
            :href="sourceLink(store.selectedDraft)" target="_blank" rel="noopener">打开来源链接 ↗</a>
        </section>
        <section
          v-if="variantWarning"
          class="wb-variant-warning"
          role="alert"
          aria-live="polite"
        >
          <strong>Ozon 变体提醒：</strong>
          <span>{{ variantWarning }}</span>
        </section>
        <!-- 顶:变体组横排条 -->
        <section class="wb-group">
          <VariantGroupBar @variant-deleted="store.loadDrafts()" />
        </section>
        <!-- 中:流程(含发布条) -->
        <section class="wb-flow">
          <div class="wb-publish-bar">
            <el-button type="primary" size="small" @click="ops.doPublish(publishTarget)">
              {{ store.selectedDraft.source === 'ozon' ? '同步回 Ozon' : '🚀 发布到 Ozon' }}
            </el-button>
            <div v-if="publishResult" class="wb-publish-result">
              <span v-if="publishResult.published" class="ok">● 已发布</span>
              <span v-for="(e, i) in (publishResult.errors || [])" :key="i" class="err">▲ {{ typeof e === 'string' ? e : JSON.stringify(e) }}</span>
            </div>
          </div>
          <PipelinePanel @publish-one="ops.doPublish(publishTarget)" />
        </section>
        <!-- 下:变体详情 -->
        <section class="wb-detail">
          <DetailTabs />
        </section>
      </template>
    </main>
    </div>
  </div>
</template>
<style scoped>
/* 高度自适应:整页随内容增高,由外层 .app__content 提供滚动条;不再固定 100vh */
.wb-page{display:flex;flex-direction:column;gap:var(--sp-3)}
.wb-toolbar{display:flex;align-items:center;justify-content:flex-end}
.wb-grid{display:grid;grid-template-columns:340px minmax(0,1fr);gap:var(--sp-4);align-items:start}
/* 左栏 sticky:页面滚动时驻留视口顶部、自身内部滚动,不随详情滚走 */
.wb-left{position:sticky;top:0;max-height:calc(100vh - 56px - var(--sp-5)*2);min-width:0;background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden;display:flex;flex-direction:column}
/* 右侧主区:纵向三段(变体组条 / 流程 / 详情)堆叠,自适应高度 */
.wb-main{display:flex;flex-direction:column;gap:var(--sp-4);min-width:0}
/* 变体组横排条:白底卡片 */
.wb-group{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:hidden;padding:var(--sp-5)}
/* 流程:完全展示,不滚动 */
.wb-flow{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:visible;padding:var(--sp-5);display:flex;flex-direction:column;gap:var(--sp-3)}
/* 详情:自适应高度,随内容增高,页面滚动条滚动(不再内部固定高滚动) */
.wb-detail{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);overflow:visible;padding:var(--sp-5)}
.wb-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);color:var(--c-text-3)}
.wb-empty__i{font-size:40px;margin-bottom:12px;opacity:.7}
.wb-source{display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap;background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);padding:var(--sp-3) var(--sp-5);font-size:var(--fs-sm)}
.wb-source__t{font-weight:600;color:var(--c-text-2);max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wb-source__lk{color:var(--c-primary);text-decoration:none}
.wb-source__lk:hover{text-decoration:underline}
.wb-variant-warning{display:flex;align-items:flex-start;gap:var(--sp-2);padding:var(--sp-3) var(--sp-4);border:1px solid var(--c-warning);border-radius:var(--r-lg);background:rgba(245,158,11,.12);color:var(--c-warning);font-size:var(--fs-sm);line-height:1.5}
.wb-variant-warning strong{flex:0 0 auto}
.wb-publish-bar{display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap}
.wb-publish-result{display:flex;flex-wrap:wrap;gap:4px;font-size:var(--fs-sm)}
.wb-publish-result .ok{color:var(--c-success)}
.wb-publish-result .err{color:var(--c-danger)}
</style>
