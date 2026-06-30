<script setup>
import { reactive, ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'
import { getUser } from '../auth.js'

// 仅 admin 可用；后端对 /api/admin/* 强制鉴权，前端隐藏只是 UX。
const isAdmin = computed(() => (getUser() || {}).role === 'admin')
const users = ref([])
const newUser = reactive({ username: '', password: '', max_stores: 1 })

async function loadUsers() {
  if (!isAdmin.value) return
  try { users.value = (await api.adminListUsers()).users } catch (e) { /* 非 admin 被后端 403，忽略 */ }
}
onMounted(loadUsers)

async function createUser() {
  if (!newUser.username || !newUser.password) { ElMessage.warning('填用户名和密码'); return }
  try {
    await api.adminCreateUser(newUser.username.trim(), newUser.password, Number(newUser.max_stores) || 1)
    ElMessage.success('已创建用户')
    newUser.username = ''; newUser.password = ''; newUser.max_stores = 1
    await loadUsers()
  } catch (e) { ElMessage.error(e.message || '创建失败') }
}

async function updateMaxStores(u) {
  try { await api.adminUpdateUser(u.id, { max_stores: Number(u.max_stores) || 1 }); ElMessage.success('已更新上限') }
  catch (e) { ElMessage.error(e.message || '更新失败') }
}

async function resetPassword(u) {
  try {
    const { value } = await ElMessageBox.prompt(`给 ${u.username} 设新密码（≥6 位）`, '重置密码', { inputType: 'password' })
    if (!value) return
    await api.adminUpdateUser(u.id, { password: value })
    ElMessage.success('密码已重置')
  } catch (e) { if (e !== 'cancel') ElMessage.error((e && e.message) || '重置失败') }
}

async function toggleStatus(u) {
  const next = u.status === 'active' ? 'disabled' : 'active'
  try {
    await api.adminUpdateUser(u.id, { status: next })
    ElMessage.success(next === 'active' ? '已启用' : '已禁用')
    await loadUsers()
  } catch (e) { ElMessage.error(e.message || '操作失败') }
}

async function removeUser(u) {
  try {
    await ElMessageBox.confirm(
      `确定彻底删除用户「${u.username}」？将连同其全部草稿/钱包/订单/快照一起删除，不可恢复！`,
      '危险操作', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await api.adminDeleteUser(u.id)
    ElMessage.success('已删除')
    await loadUsers()
  } catch (e) { if (e !== 'cancel') ElMessage.error((e && e.message) || '删除失败') }
}
</script>

<template>
  <div style="max-width:780px;margin:0 auto;padding:24px">
    <h2>用户管理</h2>
    <el-card style="margin-top:12px">
      <template #header>新建用户</template>
      <el-form :inline="true">
        <el-form-item label="用户名"><el-input v-model="newUser.username" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="newUser.password" type="password" /></el-form-item>
        <el-form-item label="最大店铺数"><el-input-number v-model="newUser.max_stores" :min="1" /></el-form-item>
        <el-form-item><el-button type="primary" @click="createUser">创建</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-table :data="users" size="small" border style="margin-top:16px">
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="role" label="角色" width="80" />
      <el-table-column prop="status" label="状态" width="80" />
      <el-table-column label="当前店数" width="80">
        <template #default="{ row }">{{ row.store_count }}</template>
      </el-table-column>
      <el-table-column label="最大店铺数" width="150">
        <template #default="{ row }">
          <el-input-number v-model="row.max_stores" :min="1" size="small" @change="() => updateMaxStores(row)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="290">
        <template #default="{ row }">
          <el-button size="small" @click="resetPassword(row)">重置密码</el-button>
          <el-button size="small" :type="row.status === 'active' ? 'warning' : 'success'" @click="toggleStatus(row)">
            {{ row.status === 'active' ? '禁用' : '启用' }}
          </el-button>
          <el-button v-if="row.role !== 'admin'" size="small" type="danger" @click="removeUser(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
