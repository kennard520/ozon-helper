<script setup>
import { reactive, ref, watch, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '../stores/app.js'
import { api } from '../api.js'

const store = useAppStore()

const form = reactive({
  rub_cny: 0,
  contract_currency: 'CNY',
  ai_auto_apply: false,
  auto_publish: false,
})

let backfilled = false
function backfill(s) {
  if (backfilled || !s || Object.keys(s).length === 0) return
  if (s.rub_cny != null && s.rub_cny !== '') form.rub_cny = Number(s.rub_cny) || 0
  if (s.contract_currency != null) form.contract_currency = s.contract_currency
  if (s.ai_auto_apply != null) form.ai_auto_apply = s.ai_auto_apply
  if (s.auto_publish != null) form.auto_publish = s.auto_publish
  backfilled = true
}
watch(() => store.settings, backfill, { immediate: true, deep: true })

const aiPlatforms = ref([])
const aiUses = reactive({
  text: { platform: '', model: '', multimodal: false },
  multimodal: { platform: '', model: '' },
  image: { platform: '', model: '' },
  video: { platform: '', model: '' },
})
const aiModels = reactive({ text: [], image: [], video: [], multimodal: [] })
const modelsLoading = reactive({ text: false, image: false, video: false, multimodal: false })

async function loadModels(use) {
  const plat = aiUses[use].platform
  if (!plat) { ElMessage.warning('请先选择平台'); return }
  if (modelsLoading[use]) return
  modelsLoading[use] = true
  try {
    const r = await api.aiModels(use, '', '', plat)
    const ms = r.models || []
    const cur = aiUses[use].model
    aiModels[use] = (cur && !ms.includes(cur)) ? [cur, ...ms] : ms
    if (!ms.length) ElMessage.warning(r.error || '没有拉到模型，可手动输入')
  } catch (e) {
    ElMessage.warning('拉取模型失败，可手动输入：' + ((e && e.message) || e))
  } finally {
    modelsLoading[use] = false
  }
}

function _loadAi() {
  const s = store.settings || {}
  aiPlatforms.value = (s.ai_platforms || []).map((p) => ({
    name: p.name || '',
    base: p.base || '',
    key: '',
    key_saved: !!p.key_saved,
  }))
  for (const [use, key] of [['text', 'ai_text'], ['multimodal', 'ai_multimodal'], ['image', 'ai_image'], ['video', 'ai_video']]) {
    const b = s[key] || {}
    aiUses[use].platform = b.platform || ''
    aiUses[use].model = b.model || ''
    if (b.model) aiModels[use] = [b.model]
  }
  aiUses.text.multimodal = !!(s.ai_text && s.ai_text.multimodal)
}
onMounted(_loadAi)
watch(() => store.settings, _loadAi, { deep: true })

function addPlatform() {
  aiPlatforms.value.push({ name: '', base: '', key: '', key_saved: false })
}

async function save() {
  const payload = { contract_currency: form.contract_currency }
  const rate = Number(form.rub_cny)
  if (rate > 0) payload.rub_cny = rate
  payload.ai_auto_apply = form.ai_auto_apply
  payload.auto_publish = form.auto_publish
  payload.ai_platforms = aiPlatforms.value
    .filter((p) => (p.name || '').trim())
    .map((p) => {
      const o = { name: p.name.trim(), base: (p.base || '').trim() }
      if ((p.key || '').trim()) o.key = p.key.trim()
      return o
    })
  const useBlock = (u) => ({ platform: u.platform || '', model: (u.model || '').trim() })
  payload.ai_text = { ...useBlock(aiUses.text), multimodal: aiUses.text.multimodal }
  payload.ai_multimodal = useBlock(aiUses.multimodal)
  payload.ai_image = useBlock(aiUses.image)
  payload.ai_video = useBlock(aiUses.video)
  payload.translate_mode = 'ai'
  const r = await api.saveSettings(payload)
  if (r.settings) store.settings = r.settings
  if (r.status) store.status = r.status
  if (r.paths) store.paths = r.paths
  ElMessage.success('设置已保存')
}

const realfbsImporting = ref(false)
async function exportRealfbs() {
  try {
    const text = await api.exportRealfbsRoutes()
    const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'realfbs_routes.csv'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || e))
  }
}
async function importRealfbs(file) {
  realfbsImporting.value = true
  try {
    const text = await file.text()
    const r = await api.importRealfbsRoutes(text)
    ElMessage.success(`运费表已导入 ${r.count} 条，智能定价即刻生效`)
  } catch (e) {
    ElMessage.error('导入失败：' + (e.message || e))
  } finally {
    realfbsImporting.value = false
  }
  return false
}

const commissionImporting = ref(false)
async function exportCommission() {
  try {
    const blob = await api.exportCommissionCategories()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'commission_categories.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || e))
  }
}
async function importCommission(file) {
  commissionImporting.value = true
  try {
    const r = await api.importCommissionCategories(file)
    ElMessage.success(`佣金表已导入 ${r.count} 个类目，智能定价即刻生效`)
  } catch (e) {
    ElMessage.error('导入失败：' + (e.message || e))
  } finally {
    commissionImporting.value = false
  }
  return false
}

const aiUseRows = [
  { key: 'text', title: '文本 AI', platformPlaceholder: '平台', modelPlaceholder: '模型' },
  { key: 'multimodal', title: '多模态 AI', platformPlaceholder: '留空复用文本 AI', modelPlaceholder: '视觉模型' },
  { key: 'image', title: '图片 AI', platformPlaceholder: '平台', modelPlaceholder: '模型' },
  { key: 'video', title: '视频 AI', platformPlaceholder: '平台', modelPlaceholder: '模型' },
]

defineExpose({
  form, save, aiPlatforms, aiUses,
  exportRealfbs, importRealfbs, exportCommission, importCommission,
})
</script>

<template>
  <div class="settings-page">
    <header class="settings-hero">
      <div>
        <p class="settings-hero__eyebrow">System Settings</p>
        <h1>系统设置</h1>
        <p class="settings-hero__desc">统一管理汇率、AI 平台、店铺凭证和智能定价数据。</p>
      </div>
      <el-button type="primary" size="large" @click="save">保存设置</el-button>
    </header>

    <div class="settings-layout">
      <section class="setting-section">
        <div class="section-head">
          <div>
            <h2>基础偏好</h2>
            <p>影响报价、草稿生成和发布行为。</p>
          </div>
        </div>
        <div class="section-grid section-grid--two">
          <div class="money-row">
            <div class="money-row__copy">
              <strong>汇率与合同货币</strong>
              <span>用于成本换算、报价和利润测算。</span>
            </div>
            <div class="money-row__controls">
              <div class="money-input">
                <span>RUB/CNY</span>
                <el-input-number v-model="form.rub_cny" :precision="4" :step="0.01" :min="0" controls-position="right" />
              </div>
              <div class="money-currency">
                <span>合同币</span>
                <el-radio-group v-model="form.contract_currency">
                  <el-radio-button value="CNY">CNY</el-radio-button>
                  <el-radio-button value="RUB">RUB</el-radio-button>
                </el-radio-group>
              </div>
            </div>
          </div>
          <div class="choice-box">
            <div>
              <strong>AI 卡片应用</strong>
              <span>人工确认会先保存为待确认草稿，自动应用会直接合并生成结果。</span>
            </div>
            <el-radio-group v-model="form.ai_auto_apply">
              <el-radio-button :value="false">人工确认</el-radio-button>
              <el-radio-button :value="true">自动应用</el-radio-button>
            </el-radio-group>
          </div>
          <div class="choice-box">
            <div>
              <strong>采集后自动发布</strong>
              <span>开启后采集流程会尝试直接发布到 Ozon。</span>
            </div>
            <el-radio-group v-model="form.auto_publish">
              <el-radio-button :value="false">只建草稿</el-radio-button>
              <el-radio-button :value="true">自动发布</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </section>

      <section class="setting-section">
        <div class="section-head">
          <div>
            <h2>AI 平台</h2>
            <p>平台只配置一次地址和 Key，各用途选择平台与模型即可。</p>
          </div>
          <el-button @click="addPlatform">添加平台</el-button>
        </div>

        <div class="platform-list">
          <div v-for="(p, i) in aiPlatforms" :key="i" class="platform-row">
            <el-input v-model="p.name" placeholder="平台名，如 GPTPlus5" />
            <el-input v-model="p.base" placeholder="接口地址，如 https://example.com/v1" />
            <el-input
              v-model="p.key"
              type="password"
              show-password
              :placeholder="p.key_saved ? '已配置，留空不改' : 'API Key'"
            />
            <el-button text type="danger" @click="aiPlatforms.splice(i, 1)">删除</el-button>
          </div>
          <div v-if="!aiPlatforms.length" class="empty-box">还没有 AI 平台，点击右上角添加一个。</div>
        </div>

        <div class="ai-use-grid">
          <div v-for="row in aiUseRows" :key="row.key" class="ai-use-card">
            <div class="ai-use-card__title">{{ row.title }}</div>
            <div class="ai-use-card__controls">
              <el-select v-model="aiUses[row.key].platform" :placeholder="row.platformPlaceholder" clearable>
                <el-option v-for="p in aiPlatforms" :key="p.name" :label="p.name" :value="p.name" />
              </el-select>
              <el-select
                v-model="aiUses[row.key].model"
                filterable
                allow-create
                default-first-option
                clearable
                :loading="modelsLoading[row.key]"
                :placeholder="row.modelPlaceholder"
                @visible-change="(o) => o && loadModels(row.key)"
              >
                <el-option v-for="m in aiModels[row.key]" :key="m" :label="m" :value="m" />
              </el-select>
              <el-select v-if="row.key === 'text'" v-model="aiUses.text.multimodal" class="mode-select">
                <el-option :value="false" label="纯文本" />
                <el-option :value="true" label="多模态" />
              </el-select>
            </div>
          </div>
        </div>
      </section>

      <section class="setting-section">
        <div class="section-head">
          <div>
            <h2>智能定价数据</h2>
            <p>维护 realFBS 运费和佣金表，导入后立即参与定价计算。</p>
          </div>
        </div>

        <div class="data-tools">
          <div class="data-card">
            <div>
              <h3>运费表 realFBS</h3>
              <p>导出 CSV 后在 Excel 调整，再导入覆盖。</p>
            </div>
            <div class="data-card__actions">
              <el-button @click="exportRealfbs">导出 CSV</el-button>
              <el-upload :show-file-list="false" accept=".csv" :before-upload="importRealfbs">
                <el-button type="primary" :loading="realfbsImporting">导入 CSV</el-button>
              </el-upload>
            </div>
          </div>

          <div class="data-card">
            <div>
              <h3>佣金表 FBS</h3>
              <p>支持导出模板或导入 Ozon 官方 Tarifs xlsx。</p>
            </div>
            <div class="data-card__actions">
              <el-button @click="exportCommission">导出 xlsx</el-button>
              <el-upload :show-file-list="false" accept=".xlsx" :before-upload="importCommission">
                <el-button type="primary" :loading="commissionImporting">导入 Excel</el-button>
              </el-upload>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page{max-width:1180px;margin:0 auto;padding:var(--sp-6);color:var(--c-text)}
.settings-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:var(--sp-4);margin-bottom:var(--sp-5)}
.settings-hero__eyebrow{margin:0 0 4px;color:var(--c-primary);font-size:var(--fs-xs);font-weight:700;text-transform:uppercase;letter-spacing:.08em}
.settings-hero h1{margin:0;font-size:28px;line-height:1.2;color:var(--c-text)}
.settings-hero__desc{margin:8px 0 0;color:var(--c-text-3);font-size:var(--fs-md)}
.settings-layout{display:flex;flex-direction:column;gap:var(--sp-4)}
.setting-section{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-sm);box-shadow:var(--sh-card);padding:var(--sp-5)}
.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp-4);margin-bottom:var(--sp-4)}
.section-head h2{margin:0;font-size:var(--fs-xl);color:var(--c-text)}
.section-head p{margin:6px 0 0;color:var(--c-text-3);font-size:var(--fs-sm)}
.section-grid{display:grid;gap:var(--sp-3)}
.section-grid--two{grid-template-columns:repeat(2,minmax(0,1fr))}
.field-box,.choice-box,.ai-use-card,.data-card{border:1px solid var(--c-border);border-radius:var(--r-sm);background:var(--c-bg-2);padding:var(--sp-4)}
.money-row{grid-column:1 / -1;display:flex;align-items:center;justify-content:space-between;gap:var(--sp-5);border:1px solid var(--c-border);border-radius:var(--r-sm);background:linear-gradient(180deg,#fff,var(--c-bg-2));padding:var(--sp-4)}
.money-row__copy{display:flex;flex-direction:column;gap:4px;min-width:180px}
.money-row__copy strong{font-size:var(--fs-md);color:var(--c-text)}
.money-row__copy span{font-size:var(--fs-xs);color:var(--c-text-3)}
.money-row__controls{display:flex;align-items:flex-end;gap:var(--sp-3);flex:1;justify-content:flex-end}
.money-input,.money-currency{display:flex;flex-direction:column;gap:6px}
.money-input{width:260px}
.money-currency{width:178px}
.money-input span,.money-currency span{font-size:var(--fs-xs);font-weight:700;color:var(--c-text-3)}
.field-box{display:flex;flex-direction:column;gap:var(--sp-2)}
.field-box label{font-size:var(--fs-xs);font-weight:700;color:var(--c-text-3)}
.choice-box{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3)}
.choice-box > div{min-width:0}
.choice-box strong{display:block;font-size:var(--fs-md);color:var(--c-text)}
.choice-box span{display:block;margin-top:4px;color:var(--c-text-3);font-size:var(--fs-xs);line-height:1.5}
.choice-box :deep(.el-radio-group){flex:0 0 auto;display:flex;flex-wrap:nowrap}
.choice-box :deep(.el-radio-button){white-space:nowrap}
.platform-list{display:flex;flex-direction:column;gap:var(--sp-2);margin-bottom:var(--sp-4)}
.platform-row{display:grid;grid-template-columns:minmax(130px,.8fr) minmax(260px,1.6fr) minmax(180px,1fr) auto;gap:var(--sp-2);align-items:center}
.empty-box{border:1px dashed var(--c-border);border-radius:var(--r-sm);padding:var(--sp-4);color:var(--c-text-3);font-size:var(--fs-sm);background:var(--c-bg-2)}
.ai-use-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--sp-3)}
.ai-use-card__title{font-weight:700;color:var(--c-text);margin-bottom:var(--sp-3)}
.ai-use-card__controls{display:grid;grid-template-columns:minmax(130px,1fr) minmax(160px,1.2fr);gap:var(--sp-2)}
.mode-select{grid-column:1 / -1}
.data-tools{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--sp-3)}
.data-card{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp-4)}
.data-card h3{margin:0;color:var(--c-text);font-size:var(--fs-md)}
.data-card p{margin:6px 0 0;color:var(--c-text-3);font-size:var(--fs-sm);line-height:1.6}
.data-card__actions{display:flex;align-items:center;gap:var(--sp-2);flex-shrink:0}
:deep(.el-input-number),:deep(.el-select){width:100%}
@media (max-width:900px){
  .settings-page{padding:var(--sp-4)}
  .settings-hero{align-items:flex-start;flex-direction:column}
  .section-grid--two,.ai-use-grid,.data-tools{grid-template-columns:1fr}
  .money-row{align-items:flex-start;flex-direction:column}
  .money-row__controls{width:100%;justify-content:flex-start;flex-wrap:wrap}
  .money-input,.money-currency{width:100%}
  .platform-row{grid-template-columns:1fr}
  .choice-box,.data-card{align-items:flex-start;flex-direction:column}
}
</style>
