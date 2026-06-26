<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAppStore } from './stores/app.js'
import Collect from './views/Collect.vue'
import Settings from './views/Settings.vue'
import Users from './views/Users.vue'
import Warehouses from './views/Warehouses.vue'
import Fulfillment from './views/Fulfillment.vue'
import Wallet from './views/Wallet.vue'
import Login from './views/Login.vue'
import { isLoggedIn, getUser, getToken, setAuth, clearAuth } from './auth.js'
import { api } from './api.js'

// 插件打开网页时带了 ?token=（单点登录）→ 存进 localStorage 后从 URL 抹掉
function consumeUrlToken() {
  try {
    const sp = new URLSearchParams(location.search)
    const t = sp.get('token')
    if (t) {
      setAuth(t, null)
      sp.delete('token')
      const qs = sp.toString()
      history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash)
    }
  } catch (e) { /* ignore */ }
}
consumeUrlToken()

const store = useAppStore()
const activeView = ref('collect')
const navCollapsed = ref(false)
const loggedIn = ref(isLoggedIn())
const user = ref(getUser())
const walletBalance = ref(null)

function _online(v) {
  const s = String(v == null ? '' : v).toLowerCase()
  if (!s) return false
  return !/(^none$|^no$|未|missing|absent|未配置|未登录|disconnected)/.test(s)
}
const isOzonOnline = computed(() => _online(store.status && store.status.ozon_api))

async function loadWallet() {
  try {
    const r = await api.wallet()
    const acc = (r && (r.account || r)) || {}
    if (acc.balance != null) walletBalance.value = acc.balance
  } catch (e) { /* 钱包未就绪时忽略 */ }
}

async function bootData() {
  await store.loadState()   // 先拿到 settings → 定下 currentStore，再按当前店拉草稿
  store.loadDrafts()
  loadWallet()
}
function onLoggedIn(u) {
  loggedIn.value = true
  user.value = u
  bootData()
}
function onLogout() {
  clearAuth()
  loggedIn.value = false
  user.value = null
}
function onAccountCmd(cmd) {
  if (cmd === 'logout') onLogout()
  else activeView.value = cmd
}
// api.js 在收到 401 时派发 auth:logout
function handleAuthEvent() { onLogout() }

onMounted(async () => {
  window.addEventListener('auth:logout', handleAuthEvent)
  if (loggedIn.value) {
    bootData()
    if (!user.value) {
      // token 来自插件 URL、本地没存 user → 拉一次补上用户名（顺带验 token 有效）
      try {
        const r = await api.me()
        user.value = r.user
        setAuth(getToken(), r.user)
      } catch (e) { /* 401 会触发 auth:logout */ }
    }
  }
})
onUnmounted(() => window.removeEventListener('auth:logout', handleAuthEvent))
</script>
<template>
  <Login v-if="!loggedIn" @logged-in="onLoggedIn" />
  <el-container v-else style="height:100vh">
    <el-aside :width="navCollapsed ? '0px' : '210px'" style="transition:width .2s ease; overflow:hidden">
      <div class="brand"><span class="gp-brand-text">上品助手 Pro</span></div>
      <el-menu :default-active="activeView" @select="k => activeView = k">
        <el-menu-item index="collect">📦 商品草稿</el-menu-item>
        <el-menu-item index="warehouses">🏢 仓库</el-menu-item>
        <el-menu-item index="fulfillment">🚚 备货发货</el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <div>Version 2026.06</div>
        <div class="aside-mode">本地数据 · 凭证不出本机</div>
      </div>
    </el-aside>
    <el-container>
      <el-header style="display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;align-items:center;gap:14px">
          <el-button text style="font-size:18px;padding:4px 8px" :title="navCollapsed ? '展开导航' : '折叠导航'" @click="navCollapsed = !navCollapsed">☰</el-button>
          <div v-if="store.storeList.length" class="store-switcher">
            <span class="switcher-label">🏪 当前店铺</span>
            <el-select
              :model-value="store.currentStore"
              size="small"
              style="width:170px"
              placeholder="选择店铺"
              @change="(v) => store.setCurrentStore(v)"
            >
              <el-option
                v-for="st in store.storeList"
                :key="st.client_id"
                :label="st.is_default ? `${st.name}（默认）` : st.name"
                :value="String(st.client_id)"
              />
            </el-select>
          </div>
          <div class="status-pills">
            <span class="status-pill">
              <span class="gp-dot" :class="{ off: !isOzonOnline }"></span>
              <span>Ozon API {{ isOzonOnline ? '就绪' : '未配置' }}</span>
            </span>
          </div>
        </div>
        <div class="header-right">
          <span
            v-if="walletBalance != null"
            class="wallet-chip"
            title="点击查看钱包"
            @click="activeView = 'wallet'"
          >💰 ¥{{ walletBalance }}</span>
          <el-dropdown trigger="click" @command="onAccountCmd">
            <span class="account-trigger">{{ (user && user.username) || '账号' }} ▾</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="wallet">💰 我的钱包</el-dropdown-item>
                <el-dropdown-item command="settings">⚙️ 设置</el-dropdown-item>
                <el-dropdown-item v-if="user && user.role === 'admin'" command="users">👥 用户管理</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main>
        <Collect v-if="activeView === 'collect'" />
        <Warehouses v-else-if="activeView === 'warehouses'" />
        <Fulfillment v-else-if="activeView === 'fulfillment'" />
        <Wallet v-else-if="activeView === 'wallet'" />
        <Settings v-else-if="activeView === 'settings'" />
        <Users v-else-if="activeView === 'users'" />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.store-switcher { display: flex; align-items: center; gap: 6px; }
.switcher-label { font-size: 12px; color: var(--gp-muted); }
.status-pills {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.05);
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  font-size: 11px;
  color: var(--gp-muted);
}
.status-pill { display: flex; align-items: center; gap: 6px; }
.pill-sep { width: 1px; height: 10px; background: rgba(0, 0, 0, 0.15); }
.header-right { display: flex; align-items: center; gap: 12px; }
.wallet-chip {
  font-size: 12px;
  color: var(--gp-purple-soft);
  background: rgba(139, 92, 246, 0.12);
  border: 1px solid rgba(139, 92, 246, 0.25);
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
}
.account-trigger {
  font-size: 13px;
  color: var(--gp-muted);
  cursor: pointer;
  outline: none;
  display: inline-flex;
  align-items: center;
}
.account-trigger:hover { color: var(--gp-text); }
.aside-footer {
  margin-top: auto;
  padding: 16px 20px;
  font-size: 11px;
  color: var(--gp-dim);
}
.aside-mode { color: var(--gp-faint); font-family: monospace; margin-top: 2px; }
:deep(.el-aside) { display: flex; flex-direction: column; }
:deep(.el-menu) { border-right: none; background: transparent; }
</style>
