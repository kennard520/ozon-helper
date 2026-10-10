<script setup>
import { ref, watch, onMounted } from 'vue'
import { api } from '../api.js'
import { ElMessage } from 'element-plus'
import { publishLabel } from '../local-lite.js'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'
import { useDraftBatchOps } from '../composables/useDraftBatchOps.js'
import DraftListPane from '../components/workbench/DraftListPane.vue'
import VariantGroupBar from '../components/workbench/VariantGroupBar.vue'
import PipelinePanel from '../components/workbench/PipelinePanel.vue'
import DetailTabs from '../components/workbench/DetailTabs.vue'

const store = useAppStore()
const wb = useWorkbenchStore()
const ops = useDraftBatchOps(store)
const details = ref(null)
const publishing = ref(false)
// 顶层解构让模板可自动解包 ref（Vue 3 setup 顶层 ref 自动 unwrap）
const { publishResult, warehouses: draftWarehouses, groupPublishing } = ops

watch(() => store.selectedId, (id) => wb.loadForDraft(id), { immediate: true })
onMounted(async () => {
  await store.loadDrafts()
  if (!store.localLite) ops.loadWarehouses()
  const id = Number(new URL(window.location.href).searchParams.get('edit'))
  if (id > 0) {
    try {
      const r = await api.getDraft(id)
      const draft = r.draft || r
      if (draft.store_client_id) { store.currentStore = String(draft.store_client_id); await store.loadDrafts() }
      if (!store.drafts.some(d => d.id === id)) store.drafts.push(draft)
      store.selectedId = id
    } catch (e) { ElMessage.error('打开采集草稿失败：' + e.message) }
  }
})

async function publishGroup() {
  if (wb.loading) return null
  const group = wb.groupKey || (store.selectedDraft && store.selectedDraft.variant_group) || ''
  const result = await ops.doPublishGroup(group)
  await wb.reload()
  return result
}

function currentPublishDraft() {
  const id = wb.currentVariantId || (store.selectedDraft && store.selectedDraft.id)
  if (id == null) return null
  if (store.selectedDraft && store.selectedDraft.id === id) return store.selectedDraft
  return store.drafts.find((d) => d.id === id) || wb.currentVariant || { id }
}

async function publishLite() {
  if (publishing.value) return
  publishing.value = true
  try {
    await details.value?.savePending?.()
    await publishSelected()
  } catch (e) { ElMessage.error("保存或发布失败：" + e.message) }
  finally { publishing.value = false }
}

async function publishSelected() {
  if (wb.loading) return null
  const draft = currentPublishDraft()
  if (!draft) return null
  const result = await ops.doPublish(draft)
  await wb.reload()
  return result
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
        <div class="wb-empty__t">{{ store.localLite ? '在 WB/Ozon 商品页采集后，选择草稿编辑并发布' : '选中左侧草稿后在此进入 AI 工作台' }}</div>
      </div>
      <template v-else>
        <!-- 顶:来源商品链接 -->
        <section v-if="store.selectedDraft.source_title || sourceLink(store.selectedDraft)" class="wb-source">
          <span class="wb-source__t" :title="store.selectedDraft.source_title">{{ store.selectedDraft.source_title || '来源商品' }}</span>
          <a v-if="sourceLink(store.selectedDraft)" class="wb-source__lk"
            :href="sourceLink(store.selectedDraft)" target="_blank" rel="noopener">打开来源链接 ↗</a>
        </section>
        <!-- 顶:变体组横排条 -->
        <section class="wb-group">
          <VariantGroupBar @variant-deleted="store.loadDrafts()" />
        </section>
        <!-- 中:流程(含发布条) -->
        <section class="wb-flow">
          <div v-if="store.localLite" class="manual-workflow">
            <div class="manual-workflow__header"><h2>上架流程</h2><p>当前商品 · 手动编辑后发布</p></div>
            <div class="manual-workflow__steps">
              <div class="manual-step"><span class="manual-step__number">1</span><div><h3>采集商品</h3><p>来源数据已保存为草稿</p><span class="manual-step__saved">已采集</span></div></div>
              <div class="manual-step"><span class="manual-step__number">2</span><div><h3>编辑商品信息</h3><p>俄语标题、类目、价格与尺寸</p><button @click="wb.requestFocus({ field: 'ozon_title' })">编辑资料</button></div></div>
              <div class="manual-step"><span class="manual-step__number">3</span><div><h3>填写必填特征</h3><p>按所选 Ozon 类目补充属性</p><button @click="wb.requestFocus({ step: 'attributes' })">检查特征</button></div></div>
              <div class="manual-step"><span class="manual-step__number">4</span><div><h3>准备商品图片</h3><p>加入图集，检查图片上传结果</p><button @click="wb.requestFocus({ field: 'images' })">管理图片</button></div></div>
              <div class="manual-step"><span class="manual-step__number">5</span><div><h3>发布前检查</h3><p>点击下方发布，查看提交预览并确认</p></div></div>
            </div>
          </div>
          <div class="wb-publish-bar">
            <el-button type="primary" size="small" :loading="publishing || groupPublishing || wb.loading" :disabled="wb.loading" @click="store.localLite ? publishLite() : publishGroup()">
              {{ !store.localLite && store.selectedDraft.source === 'ozon' ? '同步回 Ozon' : '🚀 发布到 Ozon' }}
            </el-button>
            <div v-if="publishResult" class="wb-publish-result">
              <span :class="publishResult.published ? 'ok' : 'err'">{{ publishLabel(publishResult) }}</span>
              <span v-if="publishResult.task_id">任务 #{{ publishResult.task_id }}</span>
              <span v-for="(e, i) in (publishResult.errors || [])" :key="i" class="err">▲ {{ typeof e === 'string' ? e : JSON.stringify(e) }}</span>
            </div>
          </div>
          <PipelinePanel v-if="!store.localLite" @publish-one="publishSelected" />
        </section>
        <!-- 下:变体详情 -->
        <section class="wb-detail">
          <DetailTabs ref="details" />
        </section>
      </template>
    </main>
  </div>
</template>
<style scoped>
/* 高度自适应:整页随内容增高,由外层 .app__content 提供滚动条;不再固定 100vh */
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
.wb-publish-bar{display:flex;align-items:center;gap:var(--sp-3);flex-wrap:wrap}
.wb-publish-result{display:flex;flex-wrap:wrap;gap:4px;font-size:var(--fs-sm)}
.wb-publish-result .ok{color:var(--c-success)}
.wb-publish-result .err{color:var(--c-danger)}
</style>
