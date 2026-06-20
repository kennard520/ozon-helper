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

// 三套 AI 配置（文本/图片/视频）。翻译固定走文本 AI（无 key 时后端自动降级为不翻译）
const aiText = reactive({ engine: 'openai', api_base: '', api_key: '', model: '', multimodal: false })
const aiImage = reactive({ engine: 'agnes', api_base: '', api_key: '', model: '' })
const aiVideo = reactive({ engine: 'agnes', api_base: '', api_key: '', model: '' })

function _loadAi() {
  const s = store.settings || {}
  for (const [local, key] of [[aiText, 'ai_text'], [aiImage, 'ai_image'], [aiVideo, 'ai_video']]) {
    const b = s[key] || {}
    local.engine = b.engine || (key === 'ai_text' ? 'openai' : 'agnes')
    local.api_base = b.api_base || ''
    local.model = b.model || ''
    local.api_key = ''
  }
  aiText.multimodal = !!(store.settings.ai_text && store.settings.ai_text.multimodal)
}
onMounted(_loadAi)
watch(() => store.settings, _loadAi)

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
  // 三套 AI 配置：engine/base/model 照常发；api_key 仅非空才发（空=不改，保留旧 key）
  const aiBlock = (b) => {
    const o = { engine: b.engine, api_base: b.api_base.trim(), model: b.model.trim() }
    if (b.api_key.trim()) o.api_key = b.api_key.trim()
    return o
  }
  payload.ai_text = { ...aiBlock(aiText), multimodal: aiText.multimodal }
  payload.ai_image = aiBlock(aiImage)
  payload.ai_video = aiBlock(aiVideo)
  payload.translate_mode = 'ai'   // 固定走 AI 翻译（无 key 时后端降级为原样返回）

  const r = await api.saveSettings(payload)
  if (r.settings) store.settings = r.settings
  if (r.status) store.status = r.status
  if (r.paths) store.paths = r.paths
  // 密钥惯例：保存后清空输入框
  aiText.api_key = ''
  aiImage.api_key = ''
  aiVideo.api_key = ''
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

defineExpose({ form, save, newStore, addStore, removeStore, setDefaultStore, aiText, aiImage, aiVideo })
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

      <el-form-item label="文本 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiText.engine" size="small" style="width:130px">
            <el-option label="OpenAI兼容(DeepSeek)" value="openai" />
            <el-option label="Agnes" value="agnes" />
          </el-select>
          <el-input v-model="aiText.api_base" placeholder="接口地址" size="small" style="width:200px" />
          <el-input v-model="aiText.api_key" type="password" show-password
                    :placeholder="store.settings.ai_text?.api_key_saved ? '已配(留空不改)' : 'API Key'" size="small" style="width:160px" />
          <el-input v-model="aiText.model" placeholder="模型" size="small" style="width:140px" />
          <el-select v-model="aiText.multimodal" size="small" style="width:110px">
            <el-option :value="false" label="纯文本" />
            <el-option :value="true" label="多模态" />
          </el-select>
        </div>
      </el-form-item>
      <el-form-item label="图片 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiImage.engine" size="small" style="width:130px"><el-option label="Agnes" value="agnes" /></el-select>
          <el-input v-model="aiImage.api_base" placeholder="接口地址" size="small" style="width:200px" />
          <el-input v-model="aiImage.api_key" type="password" show-password
                    :placeholder="store.settings.ai_image?.api_key_saved ? '已配(留空不改)' : 'API Key'" size="small" style="width:160px" />
          <el-input v-model="aiImage.model" placeholder="模型" size="small" style="width:140px" />
        </div>
      </el-form-item>
      <el-form-item label="视频 AI">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
          <el-select v-model="aiVideo.engine" size="small" style="width:130px"><el-option label="Agnes" value="agnes" /></el-select>
          <el-input v-model="aiVideo.api_base" placeholder="接口地址" size="small" style="width:200px" />
          <el-input v-model="aiVideo.api_key" type="password" show-password
                    :placeholder="store.settings.ai_video?.api_key_saved ? '已配(留空不改)' : 'API Key'" size="small" style="width:160px" />
          <el-input v-model="aiVideo.model" placeholder="模型" size="small" style="width:140px" />
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

      <el-form-item>
        <el-button type="primary" @click="save">保存</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>
