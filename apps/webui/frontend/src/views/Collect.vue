<template>
  <div class="collect-view">
    <div class="content-grid">
      <!-- 草稿卡片列表 -->
      <section class="draft-pane glass-panel">
        <DraftTable
          :drafts="store.filteredDrafts"
          :counts="store.counts"
          :filter="store.filter"
          :selected-id="store.selectedId"
          :warehouses="warehouses"
          :total="store.total"
          :page="store.page"
          :page-size="store.pageSize"
          @refresh="refresh"
          @update:filter="(k) => store.setFilter(k)"
          @select="(id) => (store.selectedId = id)"
          @delete="doDelete"
          @batch-update="doBatchUpdate"
          @batch-publish="doBatchPublish"
          @page-change="(p) => store.setPage(p)"
          @size-change="(s) => store.setPageSize(s)"
        />
      </section>

      <!-- 详情编辑 -->
      <section class="detail-pane glass-panel">
        <div class="detail-pane-head">
          <strong>商品详情</strong>
          <span class="detail-pane-actions">
            <el-select
              v-if="storeOptions.length > 1"
              v-model="selectedStore"
              size="small"
              style="width:130px;margin-right:6px"
              placeholder="选目标店"
            >
              <el-option
                v-for="opt in storeOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <el-button
              type="primary"
              size="small"
              :disabled="!store.selectedDraft"
              @click="doPublish(store.selectedDraft)"
            >{{ store.selectedDraft && store.selectedDraft.source === 'ozon' ? '同步回 Ozon' : '🚀 发布到 Ozon' }}</el-button>
          </span>
        </div>

        <DraftDetail
          v-if="store.selectedDraft"
          :key="store.selectedId"
          :draft="store.selectedDraft"
          @open-pricing="pricingOpen = true"
        />
        <div v-else class="empty-state">
          <div class="empty-icon">📦</div>
          <div class="empty-title">选中左侧草稿后在这里编辑</div>
          <div class="empty-sub">商品采集请用浏览器插件「上品助手」就地抓取，自动建草稿。</div>
        </div>

        <div v-if="publishResult" class="publish-result">
          <div v-if="publishResult.published" class="ok">● 已发布</div>
          <ul v-if="(publishResult.errors || []).length" class="errs">
            <li v-for="(e, i) in publishResult.errors" :key="i">▲ {{ typeof e === 'string' ? e : JSON.stringify(e) }}</li>
          </ul>
          <pre v-if="publishResult.poll || publishResult.response">{{ JSON.stringify(publishResult.poll || publishResult.response, null, 2) }}</pre>
        </div>
      </section>
    </div>

    <PricingDialog
      v-if="store.selectedDraft"
      v-model="pricingOpen"
      :draft="store.selectedDraft"
      @apply="onPricingApply"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'
import DraftTable from '../components/DraftTable.vue'
import DraftDetail from '../components/DraftDetail.vue'
import PricingDialog from '../components/PricingDialog.vue'

const store = useAppStore()

const pricingOpen = ref(false)
const publishResult = ref(null)
const warehouses = ref([])

// 目标店选择：默认 last_publish_store（在选项里），否则默认店
const selectedStore = ref('')
// storeOptions 来自统一店铺列表（已含默认店，勿再拼主店免重复）
const storeOptions = computed(() =>
  (store.settings.ozon_stores || []).map(st => ({
    value: st.client_id,
    label: st.is_default ? `${st.name}（默认）` : st.name,
  }))
)
function _defaultStoreId(s) {
  const def = (s.ozon_stores || []).find(st => st.is_default)
  return def ? String(def.client_id) : String((s.ozon_stores && s.ozon_stores[0] && s.ozon_stores[0].client_id) || '')
}
// 当 settings 加载后初始化 selectedStore
watch(
  () => store.settings,
  (s) => {
    if (!s || !(s.ozon_stores || []).length) return
    const last = String(s.last_publish_store || '')
    const opts = storeOptions.value.map(o => o.value)
    selectedStore.value = (last && opts.includes(last)) ? last : _defaultStoreId(s)
  },
  { immediate: true, deep: true },
)
// 顶栏「当前店铺」切换 → 发布目标跟着切（current 为空时不覆盖，沿用上面的默认逻辑）
watch(
  () => store.currentStore,
  (cid) => {
    if (cid && storeOptions.value.some(o => String(o.value) === String(cid))) {
      selectedStore.value = String(cid)
    }
  },
  { immediate: true },
)

async function loadWarehouses() {
  try {
    const r = await api.listWarehouses(store.currentStore)
    warehouses.value = r.warehouses || []
  } catch { /* 未配置 key / 未同步仓库时忽略 */ }
}
// 切店 → 重新拉当前店仓库（批量设置仓库下拉用）
watch(() => store.currentStore, () => loadWarehouses())

// 默认确认实现：包一层 ElMessageBox.confirm（取消会 reject）。测试里会替换成 resolve(true) 的 spy。
const confirmFn = ref((message, title) =>
  ElMessageBox.confirm(message, title || '确认', { type: 'warning', dangerouslyUseHTMLString: true }),
)

async function doBatchUpdate({ ids, patch }) {
  if (!ids || !ids.length) return
  try {
    const r = await api.batchUpdateDrafts(ids, patch)
    await store.loadDrafts()
    const label = 'stock' in patch ? '库存' : '仓库'
    const failN = (r.errors || []).length
    ElMessage.success(`已批量设置${label}：成功 ${(r.updated || []).length} 项${failN ? `，失败 ${failN} 项` : ''}`)
  } catch (e) {
    ElMessage.error('批量设置失败：' + ((e && e.message) || e))
  }
}

async function doBatchPublish(ids) {
  if (!ids || !ids.length) return
  try {
    await confirmFn.value(`确认批量发布选中的 ${ids.length} 个商品到 Ozon？将逐个校验并扣发布费，不可逆。`, '批量发布确认')
  } catch (e) {
    return // 用户取消
  }
  try {
    const r = await api.batchPublish(ids, selectedStore.value)
    await store.loadDrafts()
    ElMessage.success(`批量发布完成：成功 ${r.published} 个，失败 ${r.failed} 个`)
    const fails = (r.results || []).filter((x) => !x.published)
    if (fails.length) {
      const detail = fails.slice(0, 5).map((f) => `#${f.id}：${(f.errors || []).join('；') || '失败'}`).join('\n')
      ElMessage.warning('部分未成功：\n' + detail + (fails.length > 5 ? `\n…共 ${fails.length} 个` : ''))
    }
  } catch (e) {
    ElMessage.error('批量发布失败：' + ((e && e.message) || e))
  }
}

async function doDelete(rows) {
  const list = (rows || []).filter(Boolean)
  if (!list.length) return
  const message = `确定删除选中的 ${list.length} 个草稿？此操作只清除本地草稿，不会删除 Ozon 线上商品。`
  try {
    await confirmFn.value(message, '删除草稿')
  } catch {
    return // 用户取消
  }
  const fail = []
  for (const row of list) {
    try {
      await api.deleteDraft(row.id)
      store.removeDraft(row.id)
    } catch (err) {
      fail.push(`#${row.id}: ${(err && err.message) || err}`)
    }
  }
  if (fail.length) ElMessage.error(`删除失败：\n${fail.join('\n')}`)
}

function _buildPreviewHtml(summary, errors, warnings) {
  if (errors && errors.length) {
    const items = errors.map((e) => `<li style="color:var(--c-danger)">▲ ${e}</li>`).join('')
    return `<div style="text-align:left"><b>发布前检查发现问题，无法继续：</b><ul style="padding-left:18px;margin:8px 0">${items}</ul></div>`
  }
  const warnHtml = (warnings && warnings.length)
    ? `<div style="text-align:left;margin-bottom:8px;padding:8px;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.3);border-radius:4px">` +
      `<b style="color:var(--c-warning)">⚠️ 以下必填属性未填（可在 Ozon 后台补），仍可发布：</b>` +
      `<ul style="padding-left:18px;margin:6px 0 0">${warnings.map((wn) => `<li>${wn}</li>`).join('')}</ul></div>`
    : ''
  const s = summary
  const dims = s.dims_mm ? `${s.dims_mm.depth}×${s.dims_mm.width}×${s.dims_mm.height} mm` : '—'
  const rows = [
    ['商品编号', s.offer_id || '—'],
    ['标题', s.name || '—'],
    ['类目 ID / 类型 ID', `${s.category_id || '—'} / ${s.type_id || '—'}`],
    ['价格 / 划线价', `${s.price || '—'} / ${s.old_price || '—'} ${s.currency_code || ''}`],
    ['尺寸 (深×宽×高)', dims],
    ['重量', s.weight_g != null ? `${s.weight_g} g` : '—'],
    ['图片数', s.images_count ?? '—'],
    ['属性数', s.attributes_count ?? '—'],
    ['描述长度', s.description_len ?? '—'],
    ['含视频', s.has_video ? '是' : '否'],
  ]
  const trs = rows.map(([k, v]) =>
    `<tr><td style="color:var(--c-text-3);padding:2px 8px 2px 0;white-space:nowrap">${k}</td><td style="font-weight:500">${v}</td></tr>`
  ).join('')
  return `<div style="text-align:left">${warnHtml}<b>将提交以下内容到 Ozon（不可逆）：</b><table style="margin-top:8px;border-collapse:collapse">${trs}</table></div>`
}

async function doPublish(draft) {
  if (!draft) return
  publishResult.value = null

  const targetStore = selectedStore.value || String(store.settings.ozon_client_id || '')

  // 先拉预览，展示将要提交的内容摘要
  let preview = null
  try {
    preview = await api.publishPreview(draft.id, targetStore)
  } catch (err) {
    publishResult.value = { published: false, errors: [`预览失败: ${(err && err.message) || String(err)}`] }
    return
  }

  // 有阻断性错误 → 只展示错误，不提供"确认"按钮
  if (!preview.ok) {
    try {
      await ElMessageBox.alert(
        _buildPreviewHtml(null, preview.errors),
        '发布前检查',
        { type: 'error', dangerouslyUseHTMLString: true, confirmButtonText: '关闭' },
      )
    } catch { /* 用户关闭弹窗 */ }
    return
  }

  // 无错误 → 展示摘要并请求确认
  try {
    await confirmFn.value(
      _buildPreviewHtml(preview.summary, null, preview.warnings),
      '发布预览 — 确认后不可逆',
    )
  } catch {
    return // 用户取消
  }

  try {
    const r = await api.publish(draft.id, targetStore)
    if (r && r.draft) store.upsertDraft(r.draft)
    publishResult.value = {
      published: r.published,
      errors: r.errors || [],
      poll: r.poll,
      response: r.response,
      task_id: r.task_id,
    }
  } catch (err) {
    publishResult.value = { published: false, errors: [(err && err.message) || String(err)] }
  }
}

async function onPricingApply(ev) {
  if (!store.selectedId) return
  const r = await api.patchDraft(store.selectedId, {
    price: ev.price,
    old_price: ev.old_price,
    pricing: ev.pricing,
  })
  if (r && r.draft) store.upsertDraft(r.draft)
}

async function refresh() {
  await store.loadDrafts()
}

onMounted(() => { store.loadDrafts(); loadWarehouses() })

defineExpose({ confirmFn, pricingOpen, publishResult, selectedStore, storeOptions, doDelete, doPublish, onPricingApply, warehouses, loadWarehouses, doBatchUpdate, doBatchPublish, refresh })
</script>

<style scoped>
.collect-view { display: flex; flex-direction: column; gap: 16px; }
.content-grid {
  display: grid;
  grid-template-columns: auto minmax(560px, 1fr);
  gap: 16px;
  align-items: start;
}
.draft-pane,
.detail-pane {
  border-radius: 16px;
  overflow: hidden;
}
.draft-pane { padding: 0; }
.detail-pane { padding: 16px 18px; }
.detail-pane-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--gp-line-soft);
}
.detail-pane-head strong { font-size: 15px; }
.detail-pane-actions { display: flex; align-items: center; }
.empty-state { padding: 64px 24px; text-align: center; color: var(--gp-muted); }
.empty-icon { font-size: 40px; margin-bottom: 12px; opacity: 0.7; }
.empty-title { font-size: 15px; color: var(--gp-text); margin-bottom: 6px; }
.empty-sub { font-size: 12px; color: var(--gp-faint); line-height: 1.6; }
.publish-result { margin-top: 12px; }
.publish-result .ok { color: var(--gp-success); }
.publish-result .errs { color: var(--gp-danger); padding-left: 18px; }
.publish-result pre {
  background: rgba(0, 0, 0, 0.03);
  padding: 8px;
  border-radius: 6px;
  max-height: 200px;
  overflow: auto;
  color: var(--gp-muted);
}

@media (max-width: 1080px) {
  .content-grid { grid-template-columns: 1fr; }
}
</style>
