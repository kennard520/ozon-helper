<script setup>
import { ref, computed, reactive } from 'vue'
import { ElDialog, ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { useAppStore } from '../stores/app.js'
import { api } from '../api.js'
import {
  SButton, SBadge, SCard, SStatCard, SAlert, SSectionHeader, SAvatar,
} from '../ui/index.js'

const store = useAppStore()

// ── 计算属性 ──────────────────────────────────────────────────────────────
const stores = computed(() => store.settings.ozon_stores || [])
const connectedCount = computed(() => stores.value.filter(s => s.api_key_saved).length)
const failedCount = computed(() => stores.value.filter(s => !s.api_key_saved).length)
const hasFailedStores = computed(() => failedCount.value > 0)

// ── 持久化辅助(与 Settings.vue 同模式) ──────────────────────────────────
async function persistStores(list) {
  const r = await api.saveSettings({ ozon_stores: list })
  if (r.settings) store.settings = r.settings
  if (r.status) store.status = r.status
  if (r.paths) store.paths = r.paths
}

// ── 切换当前店 ───────────────────────────────────────────────────────────
function switchStore(cid) {
  store.setCurrentStore(String(cid))
}

// ── 移除店铺 ─────────────────────────────────────────────────────────────
async function removeStore(s) {
  try {
    await ElMessageBox.confirm(`确认移除店铺「${s.name}」？`, '移除确认', {
      confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  const list = stores.value
    .filter(x => x.client_id !== s.client_id)
    .map(x => ({ name: x.name, client_id: x.client_id, is_default: x.is_default }))
  await persistStores(list)
  ElMessage.success('已移除')
}

// ── 添加/编辑对话框 ──────────────────────────────────────────────────────
const dialogVisible = ref(false)
const dialogMode = ref('add')   // 'add' | 'edit'
const dialogSaving = ref(false)
const editTarget = ref(null)    // 编辑时的原 client_id
const dialogForm = reactive({ name: '', client_id: '', api_key: '' })

function openAdd() {
  dialogMode.value = 'add'
  editTarget.value = null
  dialogForm.name = ''
  dialogForm.client_id = ''
  dialogForm.api_key = ''
  dialogVisible.value = true
}

function openEdit(s) {
  dialogMode.value = 'edit'
  editTarget.value = s.client_id
  dialogForm.name = s.name
  dialogForm.client_id = s.client_id
  dialogForm.api_key = ''
  dialogVisible.value = true
}

async function saveDialog() {
  const name = dialogForm.name.trim()
  const client_id = dialogForm.client_id.trim()
  const api_key = dialogForm.api_key.trim()

  if (!name || !client_id) {
    ElMessage.warning('店铺名称和 Client ID 不能为空')
    return
  }
  if (dialogMode.value === 'add' && !api_key) {
    ElMessage.warning('添加店铺时 API Key 不能为空')
    return
  }

  dialogSaving.value = true
  try {
    if (dialogMode.value === 'add') {
      // 新增：保留现有脱敏字段 + 加新店
      const existing = stores.value.map(s => ({ name: s.name, client_id: s.client_id, is_default: s.is_default }))
      const newEntry = { name, client_id, api_key, is_default: existing.length === 0 }
      await persistStores([...existing, newEntry])
      ElMessage.success('店铺已添加')
    } else {
      // 编辑：找到对应条目，更新字段
      const list = stores.value.map(s => {
        if (s.client_id !== editTarget.value) {
          return { name: s.name, client_id: s.client_id, is_default: s.is_default }
        }
        const updated = { name, client_id, is_default: s.is_default }
        if (api_key) updated.api_key = api_key   // 留空 = 不改
        return updated
      })
      await persistStores(list)
      ElMessage.success('凭证已更新')
    }
    dialogVisible.value = false
  } finally {
    dialogSaving.value = false
  }
}

// 重新授权：直接打开编辑对话框(取第一个失效店)
function reAuthorize() {
  const failed = stores.value.find(s => !s.api_key_saved)
  if (failed) openEdit(failed)
}
</script>

<template>
  <div class="stores-page">
    <!-- 页头 -->
    <SSectionHeader
      title="店铺管理"
      subtitle="管理您的 Ozon 店铺凭证与连接状态"
    >
      <template #actions>
        <SButton variant="primary" size="sm" @click="openAdd">+ 添加店铺</SButton>
      </template>
    </SSectionHeader>

    <!-- 统计卡行 -->
    <div class="stores-stats">
      <SStatCard
        label="已连接"
        :value="`${connectedCount} / ${stores.length}`"
        hint="API Key 有效的店铺数"
      />
      <SStatCard
        label="商品总数"
        value="—"
        hint="暂无店铺级统计端点"
      />
      <SStatCard
        label="需处理"
        :value="failedCount"
        :danger="failedCount > 0"
        hint="凭证失效，需重新授权"
      />
    </div>

    <!-- 凭证失效告警条 -->
    <SAlert
      v-if="hasFailedStores"
      variant="danger"
      title="部分店铺凭证失效"
    >
      {{ failedCount }} 个店铺的 API Key 未配置或已失效，请重新授权以恢复同步。
      <template #actions>
        <SButton variant="ghost" size="sm" @click="reAuthorize">重新授权</SButton>
      </template>
    </SAlert>

    <!-- 店铺卡网格 -->
    <div class="stores-grid">
      <!-- 店铺卡 -->
      <SCard v-for="s in stores" :key="s.client_id" padding="0">
        <!-- 卡头：头像 + 名 + Client-Id + 徽标 -->
        <template #header>
          <div class="store-card-head">
            <SAvatar :name="s.name" :size="40" />
            <div class="store-card-info">
              <div class="store-card-name">{{ s.name }}</div>
              <div class="store-card-cid">Client ID: {{ s.client_id }}</div>
            </div>
            <SBadge :variant="s.api_key_saved ? 'success' : 'danger'">
              {{ s.api_key_saved ? '已连接' : '凭证失效' }}
            </SBadge>
          </div>
        </template>

        <!-- 卡体：三栏统计 + 额外信息 -->
        <div class="store-card-body">
          <div class="store-card-metrics">
            <div class="store-metric">
              <div class="store-metric__l">余额</div>
              <div class="store-metric__v">—</div>
            </div>
            <div class="store-metric">
              <div class="store-metric__l">商品</div>
              <div class="store-metric__v">—</div>
            </div>
            <div class="store-metric">
              <div class="store-metric__l">仓库</div>
              <div class="store-metric__v">—</div>
            </div>
          </div>

          <div class="store-card-meta">
            <div class="store-meta-row">
              <span class="store-meta-label">API Key</span>
              <span class="store-meta-value store-meta-mono">
                {{ s.api_key_saved ? '••••••••' + s.client_id.slice(-4) : '未配置' }}
              </span>
            </div>
            <div class="store-meta-row">
              <span class="store-meta-label">状态</span>
              <span class="store-meta-value">
                <SBadge :variant="s.is_default ? 'primary' : 'neutral'">
                  {{ s.is_default ? '默认店铺' : '普通店铺' }}
                </SBadge>
              </span>
            </div>
          </div>
        </div>

        <!-- 卡底：操作按钮 -->
        <template #footer>
          <div class="store-card-actions">
            <!-- 当前店/切换 -->
            <SButton
              v-if="String(s.client_id) === store.currentStore"
              variant="subtle"
              size="sm"
              disabled
            >当前店铺</SButton>
            <SButton
              v-else
              variant="ghost"
              size="sm"
              @click="switchStore(s.client_id)"
            >设为当前</SButton>

            <!-- 编辑凭证 -->
            <SButton variant="ghost" size="sm" @click="openEdit(s)">编辑凭证</SButton>

            <!-- 移除 -->
            <SButton variant="danger" size="sm" @click="removeStore(s)">移除</SButton>
          </div>
        </template>
      </SCard>

      <!-- 末尾"添加 Ozon 店铺"虚线卡 -->
      <div class="store-add-card" @click="openAdd">
        <div class="store-add-card__icon">＋</div>
        <div class="store-add-card__text">添加 Ozon 店铺</div>
        <div class="store-add-card__hint">接入新店铺，输入 Client ID 和 API Key</div>
      </div>
    </div>

    <!-- 添加/编辑 对话框 -->
    <ElDialog
      v-model="dialogVisible"
      :title="dialogMode === 'add' ? '添加 Ozon 店铺' : '编辑店铺凭证'"
      width="440px"
      :close-on-click-modal="false"
    >
      <div class="dialog-form">
        <div class="dialog-field">
          <label class="dialog-label">店铺名称</label>
          <ElInput v-model="dialogForm.name" placeholder="如：俄罗斯主店" />
        </div>
        <div class="dialog-field">
          <label class="dialog-label">Client ID</label>
          <ElInput
            v-model="dialogForm.client_id"
            placeholder="如：2841057"
            :disabled="dialogMode === 'edit'"
          />
        </div>
        <div class="dialog-field">
          <label class="dialog-label">
            API Key
            <span v-if="dialogMode === 'edit'" class="dialog-label-hint">(留空不修改)</span>
          </label>
          <ElInput
            v-model="dialogForm.api_key"
            type="password"
            show-password
            :placeholder="dialogMode === 'edit' ? '留空则保留原 API Key' : '请输入 API Key'"
          />
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <SButton variant="ghost" size="sm" @click="dialogVisible = false">取消</SButton>
          <SButton
            variant="primary"
            size="sm"
            :loading="dialogSaving"
            @click="saveDialog"
          >{{ dialogMode === 'add' ? '添加' : '保存' }}</SButton>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.stores-page {
  padding: var(--sp-6);
  max-width: 1200px;
}

/* 统计卡行 */
.stores-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--sp-4);
  margin-bottom: var(--sp-5);
}

/* 店铺网格 */
.stores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: var(--sp-4);
}

/* 店铺卡头 */
.store-card-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.store-card-info {
  flex: 1;
  min-width: 0;
}
.store-card-name {
  font-weight: 700;
  color: var(--c-text);
  font-size: var(--fs-md);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.store-card-cid {
  font-size: var(--fs-xs);
  color: var(--c-text-3);
  margin-top: 2px;
}

/* 卡体 */
.store-card-body {
  padding: var(--sp-4) var(--sp-5);
}

/* 三栏统计 */
.store-card-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--sp-3);
  padding-bottom: var(--sp-4);
  border-bottom: 1px solid var(--c-border);
  margin-bottom: var(--sp-4);
}
.store-metric__l {
  font-size: var(--fs-xs);
  color: var(--c-text-3);
}
.store-metric__v {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--c-text);
  margin-top: 2px;
}

/* 元信息行 */
.store-card-meta {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.store-meta-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.store-meta-label {
  font-size: var(--fs-xs);
  color: var(--c-text-3);
  min-width: 56px;
}
.store-meta-value {
  font-size: var(--fs-sm);
  color: var(--c-text-2);
}
.store-meta-mono {
  font-family: monospace;
  letter-spacing: 0.05em;
}

/* 卡底操作 */
.store-card-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

/* 添加虚线卡 */
.store-add-card {
  border: 2px dashed var(--c-border);
  border-radius: var(--r-lg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8) var(--sp-5);
  cursor: pointer;
  transition: 0.15s;
  min-height: 200px;
  gap: var(--sp-2);
}
.store-add-card:hover {
  border-color: var(--c-primary);
  background: var(--c-primary-50);
}
.store-add-card__icon {
  font-size: 32px;
  color: var(--c-text-4);
  line-height: 1;
}
.store-add-card:hover .store-add-card__icon {
  color: var(--c-primary);
}
.store-add-card__text {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-text-3);
}
.store-add-card:hover .store-add-card__text {
  color: var(--c-primary);
}
.store-add-card__hint {
  font-size: var(--fs-xs);
  color: var(--c-text-4);
  text-align: center;
}

/* 对话框表单 */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.dialog-field {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.dialog-label {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-2);
}
.dialog-label-hint {
  font-weight: 400;
  color: var(--c-text-4);
  font-size: var(--fs-xs);
}
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-3);
}
</style>
