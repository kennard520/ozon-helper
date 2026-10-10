<script setup>
import { ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus'
import { useRouter } from 'vue-router'
import { useRoute } from 'vue-router'
import { computed } from 'vue'
import { useAppStore } from '../stores/app.js'
import { clearAuth } from '../auth.js'
defineProps({ balance: [Number, String], username: String, isAdmin: Boolean })
const emit = defineEmits(['toggle'])
const router = useRouter()
const store = useAppStore()
const route = useRoute()
const pageTitle = computed(() => ({ '/': '商品工作台', '/stores': '店铺管理', '/settings': '系统设置', '/analytics': '数据分析', '/campaigns': '广告活动', '/warehouses': '仓库管理', '/fulfillment': '备货发货' }[route.path] || 'Ozon Helper'))
function onCmd(c) {
  if (c === 'logout') { clearAuth(); location.reload() }
  else router.push('/' + c)
}
</script>
<template>
  <header class="tb">
    <button class="tb__burger" aria-label="收起或展开侧栏" @click="emit('toggle')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 3v18"/></svg></button>
    <div class="tb__breadcrumb">{{ pageTitle }}<template v-if="route.path === '/' && store.selectedDraft"> / <b>{{ store.selectedDraft.ozon_title || store.selectedDraft.source_title }}</b></template></div>
    <div class="tb__right">
      <span v-if="!store.localLite && balance != null" class="tb__wallet" @click="router.push('/wallet')">💰 ₽ {{ balance }}</span>
      <ElDropdown trigger="click" @command="onCmd">
        <span class="tb__acct" :title="username || '账号'">{{ (username || '卖家').slice(0, 2) }}</span>
        <template #dropdown><ElDropdownMenu>
          <ElDropdownItem v-if="!store.localLite" command="wallet">💰 我的钱包</ElDropdownItem>
          <ElDropdownItem command="settings">⚙️ 设置</ElDropdownItem>
          <ElDropdownItem v-if="isAdmin && !store.localLite" command="users">👥 用户管理</ElDropdownItem>
          <ElDropdownItem divided command="logout">退出登录</ElDropdownItem>
        </ElDropdownMenu></template>
      </ElDropdown>
    </div>
  </header>
</template>
<style scoped>
.tb{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 var(--sp-5);
  background:#fff;border-bottom:1px solid var(--c-border)}
.tb__burger{background:none;border:none;font-size:18px;cursor:pointer;color:var(--c-text-2)}
.tb__right{display:flex;align-items:center;gap:var(--sp-4)}
.tb__wallet{font-size:var(--fs-sm);color:var(--c-primary);background:var(--c-primary-50);
  border:1px solid var(--c-primary-200);padding:4px 10px;border-radius:999px;cursor:pointer}
.tb__acct{font-size:var(--fs-sm);color:var(--c-text-2);cursor:pointer}
</style>
