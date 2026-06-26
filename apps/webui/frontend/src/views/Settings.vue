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

// 回填只做一次：settings 异步到达（loadState 未完成就切到本页）时也能填上，
// 之后不再覆盖用户正在编辑的内容。避免"表单空着→保存→把真实值抹成空"。
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

// AI 平台：地址+Key 配一次，多用途复用。{name, base, key(新输入), key_saved}
const aiPlatforms = ref([])
// AI 用途：只存 平台名 + 模型（协议/引擎按用途后端自动定，用户不选；地址+Key 来自所选平台）
const aiUses = reactive({
  text: { platform: '', model: '', multimodal: false },
  multimodal: { platform: '', model: '' },
  image: { platform: '', model: '' },
  video: { platform: '', model: '' },
})

// 模型下拉：点开时按所选平台调 /v1/models 拉取(后端用平台已存地址/Key)。仍可手输自定义。
const aiModels = reactive({ text: [], image: [], video: [], multimodal: [] })
const modelsLoading = reactive({ text: false, image: false, video: false, multimodal: false })
async function loadModels(use) {
  const plat = aiUses[use].platform
  if (!plat) { ElMessage.warning('请先选平台'); return }
  if (modelsLoading[use]) return
  modelsLoading[use] = true
  try {
    const r = await api.aiModels(use, '', '', plat)   // 传平台名 → 后端用该平台地址/Key
    const ms = r.models || []
    const cur = aiUses[use].model
    aiModels[use] = (cur && !ms.includes(cur)) ? [cur, ...ms] : ms   // 保留当前已选,避免覆盖丢显示
    if (!ms.length) ElMessage.warning(r.error || '没拉到模型，可手动输入')
  } catch (e) {
    ElMessage.warning('拉取模型失败，可手动输入：' + ((e && e.message) || e))
  } finally { modelsLoading[use] = false }
}

function _loadAi() {
  const s = store.settings || {}
  aiPlatforms.value = (s.ai_platforms || []).map((p) => ({
    name: p.name || '', base: p.base || '', key: '', key_saved: !!p.key_saved }))
  for (const [use, key] of [['text', 'ai_text'], ['multimodal', 'ai_multimodal'], ['image', 'ai_image'], ['video', 'ai_video']]) {
    const b = s[key] || {}
    aiUses[use].platform = b.platform || ''
    aiUses[use].model = b.model || ''
    // 把已存模型种进下拉选项，否则 el-select(allow-create) 初始 options 空时不显示这个值(看着像没存)
    if (b.model) aiModels[use] = [b.model]
  }
  aiUses.text.multimodal = !!(s.ai_text && s.ai_text.multimodal)
}
onMounted(_loadAi)
watch(() => store.settings, _loadAi, { deep: true })   // deep:就地更新 settings 也回填

async function save() {
  // contract_currency 一直有有效值，照常发送
  const payload = {
    contract_currency: form.contract_currency,
  }
  // 汇率仅在 >0 时发送（0/空不覆盖已存汇率，且后端会补时间戳）
  const rate = Number(form.rub_cny)
  if (rate > 0) payload.rub_cny = rate
  payload.ai_auto_apply = form.ai_auto_apply
  payload.auto_publish = form.auto_publish
  // AI 平台：地址+Key 配一次。key 留空 = 不改（沿用同名平台已存 key）
  payload.ai_platforms = aiPlatforms.value
    .filter((p) => (p.name || '').trim())
    .map((p) => {
      const o = { name: p.name.trim(), base: (p.base || '').trim() }
      if ((p.key || '').trim()) o.key = p.key.trim()
      return o
    })
  // 各用途：平台名 + 模型(引擎后端按用途自动)
  const useBlock = (u) => ({ platform: u.platform || '', model: (u.model || '').trim() })
  payload.ai_text = { ...useBlock(aiUses.text), multimodal: aiUses.text.multimodal }
  payload.ai_multimodal = useBlock(aiUses.multimodal)
  payload.ai_image = useBlock(aiUses.image)
  payload.ai_video = useBlock(aiUses.video)
  payload.translate_mode = 'ai'   // 固定走 AI 翻译（无 key 时后端降级为原样返回）

  const r = await api.saveSettings(payload)
  if (r.settings) store.settings = r.settings   // 触发 _loadAi 重填(平台 key 输入框随之清空)
  if (r.status) store.status = r.status
  if (r.paths) store.paths = r.paths
  ElMessage.success('设置已保存')
}

// 店铺管理（统一列表，唯一默认店）
// extraStores 是从 store.settings.ozon_stores 来的脱敏列表（{name, client_id, is_default, api_key_saved}）
const extraStores = computed(() => store.settings.ozon_stores || [])

// 新增店铺表单
const newStore = reactive({ name: '', client_id: '', api_key: '' })

async function persistStores(list) {
  const r = await api.saveSettings({ ozon_stores: list })
  if (r.settings) store.settings = r.settings
  if (r.status) store.status = r.status
  if (r.paths) store.paths = r.paths
}

async function addStore() {
  const name = newStore.name.trim(), client_id = newStore.client_id.trim(), api_key = newStore.api_key.trim()
  if (!name || !client_id || !api_key) { ElMessage.warning('请填写店铺名称、Client ID 和 API Key'); return }
  const existing = extraStores.value.map(s => ({ name: s.name, client_id: s.client_id, is_default: s.is_default }))
  await persistStores([...existing, { name, client_id, api_key, is_default: existing.length === 0 }])
  newStore.name = ''; newStore.client_id = ''; newStore.api_key = ''
  ElMessage.success('店铺已保存')
}

async function setDefaultStore(client_id) {
  const list = extraStores.value.map(s => ({ name: s.name, client_id: s.client_id, is_default: s.client_id === client_id }))
  await persistStores(list)
  ElMessage.success('已设为默认')
}

async function removeStore(client_id) {
  const list = extraStores.value.filter(s => s.client_id !== client_id)
    .map(s => ({ name: s.name, client_id: s.client_id, is_default: s.is_default }))
  await persistStores(list)
  ElMessage.success('已删除')
}

// realFBS 运费表：导出 CSV → Excel 改 → 导入覆盖（智能定价即刻生效）
const realfbsImporting = ref(false)
async function exportRealfbs() {
  try {
    const text = await api.exportRealfbsRoutes()
    const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'realfbs_routes.csv'; a.click()
    URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('导出失败：' + (e.message || e)) }
}
async function importRealfbs(file) {
  realfbsImporting.value = true
  try {
    const text = await file.text()
    const r = await api.importRealfbsRoutes(text)
    ElMessage.success(`运费表已导入 ${r.count} 条，智能定价即刻生效`)
  } catch (e) { ElMessage.error('导入失败：' + (e.message || e)) }
  finally { realfbsImporting.value = false }
  return false   // 阻止 el-upload 自动上传
}

// realFBS 佣金表（只 FBS=RFBS，按类目×价格档）：导出 xlsx → Excel 改 → 导入覆盖；
// 也可直接丢 Ozon 官方 Tarifs xlsx 导入（自动认 'MP Tree Tarifs CN' 的 RFBS 三档）
const commissionImporting = ref(false)
async function exportCommission() {
  try {
    const blob = await api.exportCommissionCategories()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'commission_categories.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('导出失败：' + (e.message || e)) }
}
async function importCommission(file) {
  commissionImporting.value = true
  try {
    const r = await api.importCommissionCategories(file)
    ElMessage.success(`佣金表已导入 ${r.count} 个类目，智能定价即刻生效`)
  } catch (e) { ElMessage.error('导入失败：' + (e.message || e)) }
  finally { commissionImporting.value = false }
  return false   // 阻止 el-upload 自动上传
}

defineExpose({ form, save, newStore, addStore, removeStore, setDefaultStore, aiPlatforms, aiUses, exportRealfbs, importRealfbs, exportCommission, importCommission })
</script>

<template>
  <div class="settings-page" style="max-width:600px;margin:0 auto;padding:24px">
    <h2>设置</h2>

    <el-form label-width="140px" label-position="left">
      <el-form-item label="RUB/CNY 汇率">
        <el-input-number v-model="form.rub_cny" :precision="4" :step="0.01" :min="0" />
      </el-form-item>

      <el-form-item label="合同货币">
        <el-select v-model="form.contract_currency">
          <el-option label="CNY" value="CNY" />
          <el-option label="RUB" value="RUB" />
        </el-select>
      </el-form-item>

      <el-form-item label="AI 平台">
        <div style="display:flex;flex-direction:column;gap:6px">
          <div v-for="(p, i) in aiPlatforms" :key="i" style="display:flex;gap:6px;align-items:center">
            <el-input v-model="p.name" placeholder="平台名 如 GPTPlus5" size="small" style="width:150px" />
            <el-input v-model="p.base" placeholder="接口地址 如 https://az.gptplus5.com/v1" size="small" style="width:290px" />
            <el-input v-model="p.key" type="password" show-password
                      :placeholder="p.key_saved ? '已配(留空不改)' : 'API Key'" size="small" style="width:170px" />
            <el-button link type="danger" size="small" @click="aiPlatforms.splice(i, 1)">删除</el-button>
          </div>
          <el-button size="small" style="width:120px" @click="aiPlatforms.push({ name: '', base: '', key: '', key_saved: false })">+ 添加平台</el-button>
          <span style="color:#999;font-size:12px">平台只配「地址+Key」一次；下面各用途选平台+模型即可，不用重复配 Key。</span>
        </div>
      </el-form-item>

      <el-form-item label="文本 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiUses.text.platform" placeholder="平台" size="small" style="width:140px" clearable>
            <el-option v-for="p in aiPlatforms" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
          <el-select v-model="aiUses.text.model" filterable allow-create default-first-option clearable
                     :loading="modelsLoading.text" size="small" style="width:180px" placeholder="模型(点开拉取)"
                     @visible-change="(o) => o && loadModels('text')">
            <el-option v-for="m in aiModels.text" :key="m" :label="m" :value="m" />
          </el-select>
          <el-select v-model="aiUses.text.multimodal" size="small" style="width:100px">
            <el-option :value="false" label="纯文本" /><el-option :value="true" label="多模态" />
          </el-select>
        </div>
      </el-form-item>

      <el-form-item label="多模态 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiUses.multimodal.platform" placeholder="平台(留空用文本AI)" size="small" style="width:150px" clearable>
            <el-option v-for="p in aiPlatforms" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
          <el-select v-model="aiUses.multimodal.model" filterable allow-create default-first-option clearable
                     :loading="modelsLoading.multimodal" size="small" style="width:180px" placeholder="视觉模型(留空用文本AI)"
                     @visible-change="(o) => o && loadModels('multimodal')">
            <el-option v-for="m in aiModels.multimodal" :key="m" :label="m" :value="m" />
          </el-select>
          <span style="color:#999;font-size:12px">看图理解(留空复用文本AI)</span>
        </div>
      </el-form-item>

      <el-form-item label="图片 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiUses.image.platform" placeholder="平台" size="small" style="width:140px" clearable>
            <el-option v-for="p in aiPlatforms" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
          <el-select v-model="aiUses.image.model" filterable allow-create default-first-option clearable
                     :loading="modelsLoading.image" size="small" style="width:180px" placeholder="模型(点开拉取)"
                     @visible-change="(o) => o && loadModels('image')">
            <el-option v-for="m in aiModels.image" :key="m" :label="m" :value="m" />
          </el-select>
        </div>
      </el-form-item>

      <el-form-item label="视频 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiUses.video.platform" placeholder="平台" size="small" style="width:140px" clearable>
            <el-option v-for="p in aiPlatforms" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
          <el-select v-model="aiUses.video.model" filterable allow-create default-first-option clearable
                     :loading="modelsLoading.video" size="small" style="width:180px" placeholder="模型(点开拉取)"
                     @visible-change="(o) => o && loadModels('video')">
            <el-option v-for="m in aiModels.video" :key="m" :label="m" :value="m" />
          </el-select>
        </div>
      </el-form-item>

      <el-form-item label="AI 卡片应用">
        <el-radio-group v-model="form.ai_auto_apply">
          <el-radio :value="false">人工确认</el-radio>
          <el-radio :value="true">自动应用</el-radio>
        </el-radio-group>
        <div style="font-size:12px;color:var(--c-text-3);margin-top:4px">
          人工确认：AI 生成后存为待确认草案，逐项可改/删，点应用才生效。自动应用：生成即合并。
        </div>
      </el-form-item>

      <el-form-item label="采集后自动发布">
        <el-radio-group v-model="form.auto_publish">
          <el-radio :value="false">只建草稿</el-radio>
          <el-radio :value="true">自动发布到 Ozon</el-radio>
        </el-radio-group>
        <div style="font-size:12px;color:var(--c-text-3);margin-top:4px">
          开启后采集会直接发到 Ozon（原样直发，到 Ozon 后台再改）；发不出去的留草稿等你手动补。
        </div>
      </el-form-item>

      <!-- Ozon 店铺（统一列表，可设默认/删除） -->
      <el-form-item label="Ozon 店铺">
        <div style="width:100%">
          <template v-if="extraStores.length">
            <div v-for="st in extraStores" :key="st.client_id" style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <span style="min-width:80px">{{ st.name }}</span>
              <span style="font-family:monospace;color:var(--c-text-2)">…{{ st.client_id.slice(-4) }}</span>
              <span :style="st.api_key_saved ? 'color:var(--c-success)' : 'color:var(--c-danger)'">{{ st.api_key_saved ? '已配' : '未配' }}</span>
              <el-tag v-if="st.is_default" type="success" size="small">默认</el-tag>
              <el-button v-else size="small" text @click="setDefaultStore(st.client_id)">设为默认</el-button>
              <el-button size="small" type="danger" text @click="removeStore(st.client_id)">删除</el-button>
            </div>
          </template>
          <div v-else style="color:var(--c-text-3);font-size:13px;margin-bottom:8px">暂无店铺</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px">
            <el-input v-model="newStore.name" placeholder="店铺名称" style="width:120px" size="small" />
            <el-input v-model="newStore.client_id" placeholder="Client ID" style="width:120px" size="small" />
            <el-input v-model="newStore.api_key" type="password" show-password placeholder="API Key" style="width:140px" size="small" />
            <el-button size="small" type="primary" @click="addStore">添加店铺</el-button>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="运费表(realFBS)">
        <div style="width:100%">
          <div style="font-size:12px;color:var(--c-text-3);margin-bottom:6px">
            智能定价用的快递运费路线。导出 CSV → 在 Excel 改费率/加减快递 → 导入覆盖即生效（拉不到表时定价自动回退内置数据）。
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <el-button size="small" @click="exportRealfbs">导出 CSV</el-button>
            <el-upload :show-file-list="false" accept=".csv" :before-upload="importRealfbs">
              <el-button size="small" type="primary" :loading="realfbsImporting">导入 CSV 覆盖</el-button>
            </el-upload>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="佣金表(FBS)">
        <div style="width:100%">
          <div style="font-size:12px;color:var(--c-text-3);margin-bottom:6px">
            智能定价用的 realFBS 佣金，按「类目 × 价格档(0–1500 / 1500–5000 / 5000+ ₽)」，只取 FBS(RFBS)。可直接丢 Ozon 官方 Tarifs xlsx 导入；或导出模板在 Excel 改完再导入覆盖即生效（拉不到表时定价自动回退内置数据）。
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <el-button size="small" @click="exportCommission">导出 xlsx</el-button>
            <el-upload :show-file-list="false" accept=".xlsx" :before-upload="importCommission">
              <el-button size="small" type="primary" :loading="commissionImporting">导入 Excel 覆盖</el-button>
            </el-upload>
          </div>
        </div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="save">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>
