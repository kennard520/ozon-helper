<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const account = ref({ balance: 0, total_recharge: 0, total_consume: 0 })
const txns = ref([])
const loading = ref(false)
const rechargeOpen = ref(false)
const rechargeForm = ref({ amount: 100, remark: '' })

const fmt = (v) => (v == null ? 0 : Number(v)).toFixed(2)
const typeText = (t) => ({ recharge: '充值', consume: '消费', refund: '退款' }[t] || t)
const tagType = (t) => ({ recharge: 'success', consume: 'danger', refund: 'warning' }[t] || 'info')

async function load() {
  loading.value = true
  try {
    const r = await api.wallet()
    account.value = r.account || {}
    txns.value = r.txns || []
  } catch (e) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function submitRecharge() {
  if (!(rechargeForm.value.amount > 0)) { ElMessage.warning('金额必须大于 0'); return }
  try {
    await api.walletRecharge(rechargeForm.value.amount, rechargeForm.value.remark)
    ElMessage.success('充值成功')
    rechargeOpen.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message || '充值失败')
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-row :gutter="20" style="margin-bottom:16px">
      <el-col :span="8"><el-card shadow="hover"><div class="lbl">当前余额</div><div class="val">¥ {{ fmt(account.balance) }}</div></el-card></el-col>
      <el-col :span="8"><el-card shadow="hover"><div class="lbl">累计充值</div><div class="val">¥ {{ fmt(account.total_recharge) }}</div></el-card></el-col>
      <el-col :span="8"><el-card shadow="hover"><div class="lbl">累计消费</div><div class="val">¥ {{ fmt(account.total_consume) }}</div></el-card></el-col>
    </el-row>
    <el-button type="primary" style="margin-bottom:12px" @click="rechargeOpen = true">充值</el-button>
    <el-table :data="txns" border>
      <el-table-column label="时间" prop="created_at" width="180" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }"><el-tag :type="tagType(row.txn_type)">{{ typeText(row.txn_type) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="金额">
        <template #default="{ row }">
          <span :style="{ color: row.txn_type === 'consume' ? 'var(--c-danger)' : 'var(--c-success)' }">
            {{ row.txn_type === 'consume' ? '-' : '+' }}{{ fmt(row.amount) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="变动后余额"><template #default="{ row }">{{ fmt(row.balance_after) }}</template></el-table-column>
      <el-table-column label="业务单号" prop="biz_no" show-overflow-tooltip />
      <el-table-column label="备注" prop="remark" show-overflow-tooltip />
    </el-table>

    <el-dialog v-model="rechargeOpen" title="充值" width="360px">
      <el-form label-width="60px">
        <el-form-item label="金额"><el-input-number v-model="rechargeForm.amount" :min="0.01" :precision="2" :step="100" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="rechargeForm.remark" placeholder="选填" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rechargeOpen = false">取消</el-button>
        <el-button type="primary" @click="submitRecharge">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.lbl { color: var(--c-text-3); font-size: 14px; }
.val { font-size: 26px; font-weight: bold; margin-top: 8px; }
</style>
