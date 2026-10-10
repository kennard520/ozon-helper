<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'

const store = useAppStore()

const storeId = ref('')
const campaigns = ref([])
const currentCampaign = ref(null)
const products = ref([])
const promotionProducts = ref([])
const promotionSummary = ref({ total: 0, reviews_promo_enabled: 0 })
const selectedProducts = ref([])
const selectedPromotionProducts = ref([])
const keyword = ref('')
const promotionKeyword = ref('')
const promotionFilter = ref('all')
const addText = ref('')
const campaignsLoading = ref(false)
const productsLoading = ref(false)
const promotionsLoading = ref(false)
const previewLoading = ref(false)
const committing = ref(false)
const reviewsPromoClosing = ref(false)
const addDialogVisible = ref(false)
const previewVisible = ref(false)
const previewData = ref(null)
const results = ref([])

const stores = computed(() => store.settings?.ozon_stores || [])
const isSearchPromo = computed(() => !!currentCampaign.value?.is_search_promo)
const actionLabel = computed(() => isSearchPromo.value ? '取消搜索推广' : '从活动移除')
const addActionLabel = computed(() => isSearchPromo.value ? '加入搜索推广' : '添加到活动')
const campaignType = computed(() => isSearchPromo.value ? 'search' : '')

const filteredProducts = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return products.value
  return products.value.filter((p) => {
    return [p.sku, p.offer_id, p.title, p.status].some(v => String(v || '').toLowerCase().includes(q))
  })
})

const filteredPromotionProducts = computed(() => {
  const q = promotionKeyword.value.trim().toLowerCase()
  return promotionProducts.value.filter((p) => {
    if (promotionFilter.value === 'enabled' && !p.reviews_promo_enabled) return false
    if (promotionFilter.value === 'disabled' && p.reviews_promo_enabled) return false
    if (!q) return true
    return [p.sku, p.offer_id, p.product_id, p.title].some(v => String(v || '').toLowerCase().includes(q))
  })
})

const closablePromotionProducts = computed(() => {
  return selectedPromotionProducts.value.filter(p => p.reviews_promo_enabled && p.offer_id)
})

function ensureStoreId() {
  if (storeId.value) return
  if (!store.currentStore) store.ensureCurrentStore?.()
  storeId.value = store.currentStore || String(stores.value[0]?.client_id || '')
}

function itemFromProduct(row) {
  return {
    sku: String(row?.sku || '').trim(),
    offer_id: String(row?.offer_id || row?.offerId || '').trim(),
  }
}

function parseInputItems(text) {
  const seen = new Set()
  return String(text || '')
    .split(/[\s,;，；]+/)
    .map(t => t.trim())
    .filter(Boolean)
    .map((token) => (/^\d+$/.test(token) ? { sku: token, offer_id: '' } : { sku: '', offer_id: token }))
    .filter((item) => {
      const key = `${item.sku}|${item.offer_id}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

async function loadCampaigns() {
  ensureStoreId()
  campaignsLoading.value = true
  try {
    const r = await api.performanceCampaigns(storeId.value)
    campaigns.value = r.campaigns || []
    if (!currentCampaign.value && campaigns.value.length) await selectCampaign(campaigns.value[0])
  } catch (e) {
    ElMessage.error(e.message || String(e))
  } finally {
    campaignsLoading.value = false
  }
}

async function loadProductPromotions() {
  ensureStoreId()
  promotionsLoading.value = true
  try {
    const r = await api.performanceProductPromotions(storeId.value, 1000)
    promotionProducts.value = r.products || []
    promotionSummary.value = r.summary || { total: promotionProducts.value.length, reviews_promo_enabled: 0 }
  } catch (e) {
    promotionProducts.value = []
    promotionSummary.value = { total: 0, reviews_promo_enabled: 0 }
    ElMessage.error(e.message || String(e))
  } finally {
    promotionsLoading.value = false
  }
}

async function selectCampaign(row) {
  currentCampaign.value = row
  selectedProducts.value = []
  results.value = []
  await loadProducts()
}

async function loadProducts() {
  if (!currentCampaign.value) {
    products.value = []
    return
  }
  productsLoading.value = true
  try {
    const r = await api.performanceCampaignProducts(currentCampaign.value.id, storeId.value, campaignType.value)
    products.value = r.products || []
  } catch (e) {
    products.value = []
    ElMessage.error(e.message || String(e))
  } finally {
    productsLoading.value = false
  }
}

function handleSelectionChange(rows) {
  selectedProducts.value = rows || []
}

function handlePromotionSelectionChange(rows) {
  selectedPromotionProducts.value = rows || []
}

function promotionItem(row) {
  return {
    sku: String(row?.sku || '').trim(),
    offer_id: String(row?.offer_id || '').trim(),
  }
}

function productPreviewUrl(row) {
  const sku = String(row?.sku || '').trim()
  if (!sku) return ''
  return `https://seller.ozon.ru/app/products/${encodeURIComponent(sku)}/edit/preview`
}

function isPreviewColumn(column) {
  return column?.property === 'sku' || column?.property === 'title'
}

function openProductPreview(row, column) {
  if (!isPreviewColumn(column)) return
  const url = productPreviewUrl(row)
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

function productPreviewCellClass({ row, column }) {
  if (!isPreviewColumn(column) || !productPreviewUrl(row)) return ''
  return 'product-preview-cell'
}

async function previewOperation(operation, items) {
  if (!currentCampaign.value) {
    ElMessage.warning('请先选择广告活动')
    return
  }
  if (!items.length) {
    ElMessage.warning('请先选择或输入商品')
    return
  }
  const payload = {
    operation,
    campaign_id: String(currentCampaign.value.id || ''),
    campaign_title: currentCampaign.value.title || '',
    items,
  }
  previewLoading.value = true
  try {
    previewData.value = await api.performanceOperationPreview(payload, storeId.value)
    results.value = []
    previewVisible.value = true
  } catch (e) {
    ElMessage.error(e.message || String(e))
  } finally {
    previewLoading.value = false
  }
}

async function previewRemoveSelected() {
  const operation = isSearchPromo.value ? 'disable_search_promo' : 'remove_products'
  await previewOperation(operation, selectedProducts.value.map(itemFromProduct))
}

async function previewAddInput() {
  const operation = isSearchPromo.value ? 'enable_search_promo' : 'add_products'
  await previewOperation(operation, parseInputItems(addText.value))
}

async function commitPreview() {
  if (!previewData.value) return
  committing.value = true
  try {
    const payload = {
      operation: previewData.value.operation,
      campaign_id: previewData.value.campaign_id,
      campaign_title: previewData.value.campaign_title || currentCampaign.value?.title || '',
      items: previewData.value.items || [],
    }
    const r = await api.performanceOperationCommit(payload, storeId.value)
    results.value = r.results || []
    previewVisible.value = false
    addDialogVisible.value = false
    addText.value = ''
    await loadProducts()
    ElMessage.success('操作已提交')
  } catch (e) {
    ElMessage.error(e.message || String(e))
  } finally {
    committing.value = false
  }
}

async function closeSelectedReviewsPromo() {
  const items = closablePromotionProducts.value.map(promotionItem)
  if (!items.length) {
    ElMessage.warning('请选择已开启快速收集评论的商品')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认关闭 ${items.length} 个商品的快速收集评论？`,
      '批量关闭快速收集评论',
      { type: 'warning', confirmButtonText: '关闭', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  reviewsPromoClosing.value = true
  try {
    const r = await api.performanceDisableReviewsPromo(items, storeId.value)
    results.value = r.results || []
    const ok = results.value.filter(x => x.ok).length
    ElMessage.success(`已提交 ${ok} 个关闭任务`)
    await loadProductPromotions()
  } catch (e) {
    ElMessage.error(e.message || String(e))
  } finally {
    reviewsPromoClosing.value = false
  }
}

function onStoreChange() {
  currentCampaign.value = null
  products.value = []
  selectedProducts.value = []
  loadCampaigns()
  loadProductPromotions()
}

onMounted(() => {
  loadCampaigns()
  loadProductPromotions()
})
watch(() => store.currentStore, (cid) => {
  if (!cid || cid === storeId.value) return
  storeId.value = cid
  onStoreChange()
})

defineExpose({
  campaigns,
  products,
  selectedProducts,
  currentCampaign,
  previewData,
  promotionProducts,
  selectedPromotionProducts,
  selectCampaign,
  closeSelectedReviewsPromo,
  openProductPreview,
  previewRemoveSelected,
  previewAddInput,
  parseInputItems,
})
</script>

<template>
  <div class="campaign-page">
    <header class="page-head">
      <div>
        <p class="page-head__eyebrow">Ozon Performance</p>
        <h1>广告活动</h1>
      </div>
      <div class="page-head__actions">
        <el-select v-model="storeId" class="store-select" placeholder="店铺" @change="onStoreChange">
          <el-option v-for="s in stores" :key="s.client_id" :label="s.name || s.client_id" :value="String(s.client_id)" />
        </el-select>
        <el-button :loading="campaignsLoading" @click="loadCampaigns">刷新</el-button>
      </div>
    </header>

    <section class="promotion-panel" aria-label="商品推广状态">
      <div class="panel-head">
        <div>
          <h2>商品推广状态</h2>
          <p>
            快速收集评论已开启
            {{ promotionSummary.reviews_promo_enabled || 0 }} / {{ promotionSummary.total || 0 }}
          </p>
        </div>
        <div class="promotion-actions">
          <el-radio-group v-model="promotionFilter">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="enabled">已开启</el-radio-button>
            <el-radio-button value="disabled">未开启</el-radio-button>
          </el-radio-group>
          <el-input v-model="promotionKeyword" clearable placeholder="搜索 SKU / offer_id / 标题" />
          <el-button
            type="danger"
            plain
            :disabled="!closablePromotionProducts.length"
            :loading="reviewsPromoClosing"
            @click="closeSelectedReviewsPromo"
          >
            批量关闭
          </el-button>
          <el-button :loading="promotionsLoading" @click="loadProductPromotions">刷新商品状态</el-button>
        </div>
      </div>
      <el-table
        v-loading="promotionsLoading"
        :data="filteredPromotionProducts"
        height="280"
        row-key="product_id"
        :cell-class-name="productPreviewCellClass"
        @cell-click="openProductPreview"
        @selection-change="handlePromotionSelectionChange"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column prop="sku" label="SKU" width="140">
          <template #default="{ row }">
            <a
              v-if="productPreviewUrl(row)"
              class="product-preview-link"
              :href="productPreviewUrl(row)"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop
            >
              {{ row.sku }}
            </a>
            <span v-else>{{ row.sku }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="offer_id" label="Offer ID" width="180" />
        <el-table-column prop="title" label="商品标题" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <a
              v-if="productPreviewUrl(row)"
              class="product-preview-link"
              :href="productPreviewUrl(row)"
              target="_blank"
              rel="noopener noreferrer"
              @click.stop
            >
              {{ row.title || row.sku }}
            </a>
            <span v-else>{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="快速收集评论" width="140">
          <template #default="{ row }">
            <el-tag :type="row.reviews_promo_enabled ? 'success' : 'info'" effect="plain">
              {{ row.reviews_promo_enabled ? '已开启' : '未开启' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <div class="campaign-shell">
      <section class="campaign-list" aria-label="广告活动列表">
        <div class="panel-head">
          <h2>活动</h2>
          <span>{{ campaigns.length }} 个</span>
        </div>
        <el-table
          v-loading="campaignsLoading"
          :data="campaigns"
          height="calc(100vh - 252px)"
          highlight-current-row
          @row-click="selectCampaign"
        >
          <el-table-column prop="title" label="名称" min-width="160">
            <template #default="{ row }">
              <div class="campaign-name">
                <strong>{{ row.title || row.id }}</strong>
                <span>ID {{ row.id }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_search_promo ? 'warning' : 'info'" effect="plain">
                {{ row.is_search_promo ? '搜索推广' : '普通活动' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="product-panel" aria-label="活动商品">
        <div class="panel-head">
          <div>
            <h2>{{ currentCampaign?.title || '选择活动' }}</h2>
            <p v-if="currentCampaign">ID {{ currentCampaign.id }} · {{ isSearchPromo ? '搜索推广' : '普通活动' }}</p>
          </div>
          <div class="product-actions">
            <el-input v-model="keyword" clearable placeholder="搜索 SKU / offer_id / 标题" />
            <el-button type="primary" :disabled="!currentCampaign" @click="addDialogVisible = true">
              {{ addActionLabel }}
            </el-button>
            <el-button
              type="danger"
              plain
              :disabled="!selectedProducts.length"
              :loading="previewLoading"
              @click="previewRemoveSelected"
            >
              {{ actionLabel }}
            </el-button>
          </div>
        </div>

        <el-table
          v-loading="productsLoading"
          :data="filteredProducts"
          height="calc(100vh - 300px)"
          row-key="sku"
          :cell-class-name="productPreviewCellClass"
          @cell-click="openProductPreview"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="44" />
          <el-table-column prop="sku" label="SKU" width="140">
            <template #default="{ row }">
              <a
                v-if="productPreviewUrl(row)"
                class="product-preview-link"
                :href="productPreviewUrl(row)"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
              >
                {{ row.sku }}
              </a>
              <span v-else>{{ row.sku }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="offer_id" label="Offer ID" width="160" />
          <el-table-column prop="title" label="商品标题" min-width="240" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column prop="bid" label="出价" width="100" />
        </el-table>

        <div v-if="results.length" class="result-panel">
          <div class="result-panel__head">
            <strong>执行结果</strong>
            <span>{{ results.filter(r => r.ok).length }} / {{ results.length }} 成功</span>
          </div>
          <el-table :data="results" size="small" max-height="220">
            <el-table-column prop="sku" label="SKU" width="140" />
            <el-table-column prop="offer_id" label="Offer ID" width="160" />
            <el-table-column label="结果" width="96">
              <template #default="{ row }">
                <el-tag :type="row.ok ? 'success' : 'danger'" effect="plain">{{ row.ok ? '成功' : '失败' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="消息" min-width="220" show-overflow-tooltip />
          </el-table>
        </div>
      </section>
    </div>

    <el-dialog v-model="addDialogVisible" :title="addActionLabel" width="560px">
      <div class="dialog-body">
        <el-input
          v-model="addText"
          type="textarea"
          :rows="8"
          placeholder="每行一个 SKU 或 offer_id，也可以用空格、逗号分隔"
        />
      </div>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="previewLoading" @click="previewAddInput">预览</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="确认执行" width="640px">
      <div v-if="previewData" class="preview-box">
        <div class="preview-meta">
          <span>活动：{{ previewData.campaign_title || previewData.campaign_id }}</span>
          <span>商品数：{{ previewData.count }}</span>
        </div>
        <el-alert
          v-if="previewData.warnings && previewData.warnings.length"
          type="warning"
          :closable="false"
          show-icon
          :title="previewData.warnings.join('；')"
        />
        <el-table :data="previewData.items || []" size="small" max-height="280">
          <el-table-column prop="sku" label="SKU" width="180" />
          <el-table-column prop="offer_id" label="Offer ID" min-width="200" />
        </el-table>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">再检查一下</el-button>
        <el-button type="primary" :loading="committing" @click="commitPreview">提交执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.campaign-page{max-width:1380px;margin:0 auto;padding:var(--sp-5);color:var(--c-text)}
.page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--sp-4);margin-bottom:var(--sp-4)}
.page-head__eyebrow{margin:0 0 4px;color:var(--c-primary);font-size:var(--fs-xs);font-weight:700;text-transform:uppercase;letter-spacing:.08em}
.page-head h1{margin:0;font-size:28px;line-height:1.2}
.page-head__actions{display:flex;align-items:center;gap:var(--sp-2)}
.store-select{width:220px}
.campaign-shell{display:grid;grid-template-columns:minmax(320px,.8fr) minmax(0,1.7fr);gap:var(--sp-4);align-items:start}
.promotion-panel,.campaign-list,.product-panel{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-sm);box-shadow:var(--sh-card);padding:var(--sp-4);min-width:0}
.promotion-panel{margin-bottom:var(--sp-4)}
.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp-3);margin-bottom:var(--sp-3)}
.panel-head h2{margin:0;font-size:var(--fs-xl);color:var(--c-text)}
.panel-head p,.panel-head span{margin:5px 0 0;color:var(--c-text-3);font-size:var(--fs-xs)}
.campaign-name{display:flex;flex-direction:column;gap:3px;min-width:0}
.campaign-name strong{font-size:var(--fs-sm);color:var(--c-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.campaign-name span{font-size:var(--fs-xs);color:var(--c-text-4)}
.product-preview-link{color:var(--c-primary);font-weight:600;text-decoration:none}
.product-preview-link:hover{text-decoration:underline}
:deep(.product-preview-cell){cursor:pointer;color:var(--c-primary)}
.product-actions{display:grid;grid-template-columns:minmax(220px,1fr) auto auto;gap:var(--sp-2);align-items:center;min-width:min(100%,640px)}
.promotion-actions{display:grid;grid-template-columns:auto minmax(220px,1fr) auto auto;gap:var(--sp-2);align-items:center;min-width:min(100%,820px)}
.promotion-actions :deep(.el-radio-group){display:flex;flex-wrap:nowrap}
.promotion-actions :deep(.el-radio-button){white-space:nowrap}
.result-panel{margin-top:var(--sp-4);border:1px solid var(--c-border);border-radius:var(--r-sm);padding:var(--sp-3);background:var(--c-bg-2)}
.result-panel__head{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-2);font-size:var(--fs-sm)}
.result-panel__head span{color:var(--c-text-3)}
.dialog-body{display:flex;flex-direction:column;gap:var(--sp-3)}
.preview-box{display:flex;flex-direction:column;gap:var(--sp-3)}
.preview-meta{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3);font-size:var(--fs-sm);color:var(--c-text-2)}
:deep(.el-table){--el-table-header-bg-color:var(--c-bg-2)}
@media (max-width:1100px){
  .campaign-page{padding:var(--sp-4)}
  .campaign-shell{grid-template-columns:1fr}
  .product-actions,.promotion-actions{grid-template-columns:1fr}
}
@media (max-width:720px){
  .page-head{align-items:flex-start;flex-direction:column}
  .page-head__actions{width:100%;align-items:stretch;flex-direction:column}
  .store-select{width:100%}
}
</style>
