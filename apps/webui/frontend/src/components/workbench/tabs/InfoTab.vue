<script setup>
import { computed } from 'vue'
import { ElInput, ElInputNumber, ElFormItem, ElForm } from 'element-plus'
import CategorySelect from '../../../components/CategorySelect.vue'
import BrandSelect from '../../../components/BrandSelect.vue'
import { SButton } from '../../../ui/index.js'

const props = defineProps({
  form: { type: Object, required: true },
  draft: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['save'])

// CategorySelect v-model 契约: { cat, type }
// BrandSelect v-model 契约: { brand_id, brand_name }; props: cat, type
const categoryModel = computed({
  get: () => ({ cat: props.form.category_id, type: props.form.type_id }),
  set: (v) => {
    props.form.category_id = v.cat ?? ''
    props.form.type_id = v.type ?? ''
  },
})

const brandModel = computed({
  get: () => ({ brand_id: props.form.brand_id, brand_name: props.form.brand_name }),
  set: (v) => {
    props.form.brand_id = v.brand_id ?? null
    props.form.brand_name = v.brand_name ?? ''
  },
})
</script>

<template>
  <div class="info-tab">
    <ElForm label-width="80px" label-position="left" class="info-form">
      <ElFormItem label="Ozon 标题">
        <ElInput
          v-model="form.ozon_title"
          placeholder="上架用俄语标题"
        />
      </ElFormItem>

      <ElFormItem label="类目">
        <CategorySelect v-model="categoryModel" />
      </ElFormItem>

      <ElFormItem label="品牌">
        <BrandSelect
          v-model="brandModel"
          :cat="form.category_id"
          :type="form.type_id"
        />
      </ElFormItem>

      <ElFormItem label="库存">
        <ElInputNumber
          v-model="form.stock"
          :min="0"
          :precision="0"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="售价(¥)">
        <ElInputNumber
          v-model="form.price"
          :min="0"
          :precision="2"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="划线价(¥)">
        <ElInputNumber
          v-model="form.old_price"
          :min="0"
          :precision="2"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="克重(g)">
        <ElInputNumber
          v-model="form.weight_g"
          :min="0"
          :precision="0"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="长(mm)">
        <ElInputNumber
          v-model="form.length_mm"
          :min="0"
          :precision="0"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="宽(mm)">
        <ElInputNumber
          v-model="form.width_mm"
          :min="0"
          :precision="0"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="高(mm)">
        <ElInputNumber
          v-model="form.height_mm"
          :min="0"
          :precision="0"
          style="width: 100%"
        />
      </ElFormItem>

      <ElFormItem label="简介">
        <ElInput
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="商品简介（可选）"
        />
      </ElFormItem>
    </ElForm>

    <div class="tab-actions">
      <SButton variant="primary" @click="emit('save')">保存</SButton>
    </div>
  </div>
</template>

<style scoped>
.info-tab {
  padding: var(--space-4, 16px);
}
.info-form {
  margin-bottom: var(--space-4, 16px);
}
.tab-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
