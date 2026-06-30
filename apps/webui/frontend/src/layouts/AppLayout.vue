<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { getUser, getToken, setAuth } from '../auth.js'
import { api } from '../api.js'
import AppSidebar from './AppSidebar.vue'
import AppTopBar from './AppTopBar.vue'

const store = useAppStore()
const collapsed = ref(false)
const user = ref(getUser())
const balance = ref(null)
const ready = ref(false)   // loadState 完成(当前店已解析)后才渲染子路由
const isAdmin = computed(() => user.value && user.value.role === 'admin')

async function loadWallet() {
  try { const r = await api.wallet(); const acc = (r && (r.account || r)) || {}
    if (acc.balance != null) balance.value = acc.balance } catch (e) { /* ignore */ }
}
onMounted(async () => {
  // 先解析当前店,再放行子路由——否则子页面(Vue 子 mounted 早于父)会先发一条不带店的请求
  await store.loadState()
  ready.value = true
  loadWallet()
  if (!user.value) { try { const r = await api.me(); user.value = r.user; setAuth(getToken(), r.user) } catch (e) { /* 401→logout */ } }
})
</script>
<template>
  <div class="app" :class="{ collapsed }">
    <AppSidebar class="app__sb" />
    <div class="app__main">
      <AppTopBar :balance="balance" :username="user && user.username" :is-admin="isAdmin" @toggle="collapsed = !collapsed" />
      <main class="app__content"><router-view v-if="ready" /></main>
    </div>
  </div>
</template>
<style scoped>
.app{display:grid;grid-template-columns:220px 1fr;height:100vh}
.app.collapsed{grid-template-columns:0 1fr}
.app__sb{overflow:hidden;transition:.2s}
.app__main{display:flex;flex-direction:column;min-width:0;background:var(--c-bg)}
.app__content{flex:1;overflow:auto;padding:var(--sp-5)}
</style>
