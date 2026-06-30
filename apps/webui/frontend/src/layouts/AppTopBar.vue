<script setup>
import { ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus'
import { useRouter } from 'vue-router'
import { clearAuth } from '../auth.js'
defineProps({ balance: [Number, String], username: String, isAdmin: Boolean })
const emit = defineEmits(['toggle'])
const router = useRouter()
function onCmd(c) {
  if (c === 'logout') { clearAuth(); location.reload() }
  else router.push('/' + c)
}
</script>
<template>
  <header class="tb">
    <button class="tb__burger" @click="emit('toggle')">☰</button>
    <div class="tb__right">
      <span v-if="balance != null" class="tb__wallet" @click="router.push('/wallet')">💰 ₽ {{ balance }}</span>
      <ElDropdown trigger="click" @command="onCmd">
        <span class="tb__acct">{{ username || '账号' }} ▾</span>
        <template #dropdown><ElDropdownMenu>
          <ElDropdownItem command="wallet">💰 我的钱包</ElDropdownItem>
          <ElDropdownItem command="settings">⚙️ 设置</ElDropdownItem>
          <ElDropdownItem v-if="isAdmin" command="users">👥 用户管理</ElDropdownItem>
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
