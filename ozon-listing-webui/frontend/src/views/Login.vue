<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import { setAuth } from '../auth.js'

const emit = defineEmits(['logged-in'])
const mode = ref('login')        // login | register
const form = ref({ username: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const fn = mode.value === 'login' ? api.login : api.register
    const r = await fn(form.value.username, form.value.password)
    setAuth(r.token, r.user)
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
    emit('logged-in', r.user)
  } catch (e) {
    ElMessage.error(e.message || '失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <div class="title">Ozon 上品助手</div>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" @keyup.enter="submit" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width:100%" @click="submit">
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </el-form>
      <div class="switch">
        <el-link type="primary" @click="mode = mode === 'login' ? 'register' : 'login'">
          {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
        </el-link>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--c-bg);
  background-image:
    radial-gradient(circle at 10% 20%, rgba(139, 92, 246, 0.2) 0%, transparent 40%),
    radial-gradient(circle at 90% 80%, rgba(59, 130, 246, 0.2) 0%, transparent 40%);
}
.login-card { width: 360px; }
.title {
  font-size: 20px;
  font-weight: bold;
  text-align: center;
  margin-bottom: 20px;
  background: linear-gradient(to right, #a78bfa, #818cf8);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.switch { text-align: center; margin-top: 12px; }
</style>
