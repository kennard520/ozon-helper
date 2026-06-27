<script setup>
import { ElInput, ElInputNumber, ElFormItem, ElForm } from 'element-plus'
import { SButton } from '../../../ui/index.js'

const props = defineProps({
  form: { type: Object, required: true },
})
const emit = defineEmits(['save'])
</script>

<template>
  <div class="purchase-tab">
    <ElForm label-width="80px" label-position="left" class="purchase-form">
      <ElFormItem label="采购链接">
        <ElInput
          v-model="form.purchase_url"
          placeholder="1688/淘宝等采购链接"
          clearable
        />
      </ElFormItem>

      <ElFormItem label="供应商">
        <ElInput
          v-model="form.supplier"
          placeholder="供应商名称"
          clearable
        />
      </ElFormItem>

      <ElFormItem label="成本价(¥)">
        <ElInputNumber
          v-model="form.cost_cny"
          :min="0"
          :precision="2"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="采购备注">
        <ElInput
          v-model="form.purchase_note"
          type="textarea"
          :rows="3"
          placeholder="备注（可选）"
        />
      </ElFormItem>
    </ElForm>

    <div class="tab-actions">
      <SButton variant="primary" @click="emit('save')">保存</SButton>
    </div>
  </div>
</template>

<style scoped>
.purchase-tab {
  padding: var(--space-4, 16px);
}
.purchase-form {
  margin-bottom: var(--space-4, 16px);
}
.tab-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
