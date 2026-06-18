<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'

const store = useAppStore()
const warehouses = ref([])
const loading = ref(false)
const syncing = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await api.listWarehouses(store.currentStore)
    warehouses.value = r.warehouses
  } catch (e) {
    ElMessage.error(e.message || '加载仓库失败')
  } finally {
    loading.value = false
  }
}
// 切店 → 重新拉当前店仓库
watch(() => store.currentStore, load, { immediate: true })

async function doSync() {
  syncing.value = true
  try {
    const r = await api.syncWarehouses(store.currentStore)
    warehouses.value = r.warehouses
    ElMessage.success(`同步成功，共 ${r.synced} 个仓库`)
  } catch (e) {
    ElMessage.error(e.message || '同步失败')
  } finally {
    syncing.value = false
  }
}

async function makeDefault(wid) {
  try {
    const r = await api.setDefaultWarehouse(wid, store.currentStore)
    warehouses.value = r.warehouses
  } catch (e) {
    ElMessage.error(e.message || '设置默认仓库失败')
  }
}

function fmtFetchedAt(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

defineExpose({ warehouses, doSync, makeDefault, fmtFetchedAt })
</script>

<template>
  <div>
    <div style="margin-bottom: 16px">
      <el-button type="primary" :loading="syncing" @click="doSync">从 Ozon 同步仓库</el-button>
    </div>
    <el-table :data="warehouses" v-loading="loading" style="width: 100%">
      <el-table-column prop="warehouse_id" label="仓库 ID" width="120" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_rfbs ? 'warning' : 'info'">
            {{ row.is_rfbs ? 'rFBS' : 'FBS' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column label="默认" width="80">
        <template #default="{ row }">
          <el-radio
            :model-value="row.is_default ? row.warehouse_id : null"
            :label="row.warehouse_id"
            @click="makeDefault(row.warehouse_id)"
          />
        </template>
      </el-table-column>
      <el-table-column label="上次同步" width="160">
        <template #default="{ row }">
          <span v-if="row.fetched_at" style="color:var(--c-text-3);font-size:12px">{{ fmtFetchedAt(row.fetched_at) }}</span>
          <span v-else style="color:var(--c-text-disabled)">—</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
