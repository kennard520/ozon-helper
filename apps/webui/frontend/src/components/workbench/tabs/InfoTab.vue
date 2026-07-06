<script setup>
import { computed } from 'vue'
import { ElInput, ElInputNumber } from 'element-plus'
import CategorySelect from '../../../components/CategorySelect.vue'
import BrandSelect from '../../../components/BrandSelect.vue'

const props = defineProps({
  form: { type: Object, required: true },
  draft: { type: Object, default: () => ({}) },
})

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
    <div class="info-grid">
      <div class="ifield">
        <label>Ozon 标题 (RU)</label>
        <ElInput v-model="form.ozon_title" placeholder="上架用俄语标题" />
      </div>

      <div class="ifield">
        <label>类目</label>
        <CategorySelect v-model="categoryModel" />
      </div>

      <div class="ifield ifield--double">
        <label>货号 (Offer ID)</label>
        <div class="ifield__ro">{{ draft.offer_id || '-' }}</div>
      </div>

      <div class="ifield">
        <label>品牌</label>
        <BrandSelect v-model="brandModel" :cat="form.category_id" :type="form.type_id" />
      </div>

      <div class="ifield">
        <label>售价 (₽)</label>
        <ElInputNumber v-model="form.price" :min="0" :precision="2" controls-position="right" style="width:100%" />
      </div>

      <div class="ifield">
        <label>划线价 (₽)</label>
        <ElInputNumber v-model="form.old_price" :min="0" :precision="2" controls-position="right" style="width:100%" />
      </div>

      <div class="ifield">
        <label>尺寸 长 x 宽 x 高 (mm)</label>
        <div class="dims">
          <ElInputNumber v-model="form.length_mm" :min="0" :precision="0" :controls="false" placeholder="长" style="width:100%" />
          <span class="dims__x">x</span>
          <ElInputNumber v-model="form.width_mm" :min="0" :precision="0" :controls="false" placeholder="宽" style="width:100%" />
          <span class="dims__x">x</span>
          <ElInputNumber v-model="form.height_mm" :min="0" :precision="0" :controls="false" placeholder="高" style="width:100%" />
        </div>
      </div>

      <div class="ifield">
        <label>重量 (g)</label>
        <ElInputNumber v-model="form.weight_g" :min="0" :precision="0" controls-position="right" style="width:100%" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-tab {
  padding: var(--sp-3, 12px);
}

.info-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px 16px;
}

.ifield:nth-child(1),
.ifield:nth-child(5),
.ifield:nth-child(7) {
  grid-column: span 2;
}

.ifield--double {
  grid-column: span 2;
}

.ifield {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.ifield > label {
  font-size: var(--fs-xs, 11.5px);
  color: var(--c-text-3, #8a94a3);
}

.ifield__ro {
  min-height: 36px;
  display: flex;
  align-items: center;
  padding: 8px 11px;
  border: 1px solid var(--c-border, #e5e8ef);
  border-radius: 9px;
  background: var(--c-bg, #f7f9fc);
  color: var(--c-text, #1f2733);
  font-size: var(--fs-sm, 13px);
  font-weight: 500;
}

.dims {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.dims__x {
  color: var(--c-text-3, #8a94a3);
}

@media (max-width: 760px) {
  .info-grid {
    grid-template-columns: 1fr;
  }

  .ifield:nth-child(1),
  .ifield:nth-child(5),
  .ifield:nth-child(7),
  .ifield--double {
    grid-column: auto;
  }

  .dims {
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
  }
}
</style>
