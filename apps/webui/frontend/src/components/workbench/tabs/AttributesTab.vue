<script setup>
import { ref, computed, toRef } from 'vue'
import { ElInput } from 'element-plus'
import { useAttributes } from '../../../composables/useAttributes.js'
import AttrField from '../AttrField.vue'
import { SButton, SAlert } from '../../../ui/index.js'

const props = defineProps({
  draft: { type: Object, default: () => ({}) },
  form: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'save-info'])

const draftRef = toRef(props, 'draft')
const a = useAttributes(draftRef)

const optionalOpen = ref(false)

const TAG_ATTR = 23171
const MODEL_NAME_ATTR = 9048

const tagDef = {
  id: TAG_ATTR,
  name: '标签',
  is_required: true,
  is_collection: true,
  dictionary_id: 0,
  max_value_count: 0,
}
const modelDef = {
  id: MODEL_NAME_ATTR,
  name: '型号名称',
  is_required: true,
  is_collection: false,
  dictionary_id: 0,
}

const systemAttrIds = new Set([TAG_ATTR, MODEL_NAME_ATTR])
const visibleGroups = computed(() => ({
  aspects: (a.groups.value.aspects || []).filter((def) => !systemAttrIds.has(Number(def.id))),
  required: (a.groups.value.required || []).filter((def) => !systemAttrIds.has(Number(def.id))),
  optional: (a.groups.value.optional || []).filter((def) => !systemAttrIds.has(Number(def.id))),
}))
const categoryMissingIds = computed(() => a.missingIds.value.filter((id) => !systemAttrIds.has(Number(id))))

function attrValues(id) {
  const draftAttr = (props.draft.attributes || []).find((x) => Number(x.id) === Number(id))
  const vals = a.values[id] || (draftAttr && draftAttr.values) || []
  return Array.isArray(vals) ? vals : []
}

function attrText(id) {
  return attrValues(id).map((v) => (v && v.value) || v).filter(Boolean)
}

const tagText = computed(() => attrText(TAG_ATTR).join(', '))
const modelValues = computed(() => attrValues(MODEL_NAME_ATTR))
const descriptionText = computed(() => String((props.form && props.form.description) ?? props.draft.description ?? '').trim())
const hasCountry = computed(() => true)

const customMissing = computed(() => {
  const out = []
  if (!descriptionText.value) out.push('简介')
  if (!attrText(TAG_ATTR).length) out.push('标签')
  if (!attrText(MODEL_NAME_ATTR).length) out.push('型号名称')
  if (!hasCountry.value) out.push('原产国 / 制造国')
  return out
})

const missingSet = computed(() => new Set([...categoryMissingIds.value, ...customMissing.value]))
const missingCount = computed(() => categoryMissingIds.value.length + customMissing.value.length)

function onUpdate(def, val) { a.setValue(def.id, val) }

function onTagsChange(v) {
  const values = String(v || '')
    .split(/[,\n，]/)
    .map((x) => x.trim())
    .filter(Boolean)
    .map((value) => ({ value }))
  a.setValue(TAG_ATTR, values)
}

function onDescriptionChange() {
  emit('save-info')
}
</script>

<template>
  <div class="attrs-tab">
    <SAlert v-if="missingCount" variant="warn"
      :title="`还缺 ${missingCount} 项必填信息（改动会自动保存）`" style="margin-bottom:14px" />

    <div class="at-sec">
      <div class="at-sec__k"><span class="at-req">*</span>简介</div>
      <ElInput
        v-if="form"
        v-model="form.description"
        type="textarea"
        :rows="4"
        placeholder="商品简介，发布前必填"
        :class="{ 'is-missing': missingSet.has('简介') }"
        @change="onDescriptionChange"
      />
      <div v-else class="at-anno" :class="{ 'at-anno--missing': missingSet.has('简介') }">
        {{ draft.description || '暂无简介' }}
      </div>
    </div>

    <div class="at-grid at-grid--system">
      <div class="at-fld">
        <label class="at-label"><span class="at-req">*</span>标签</label>
        <ElInput
          :model-value="tagText"
          placeholder="多个标签用逗号分隔"
          :class="{ 'is-missing': missingSet.has('标签') }"
          @change="onTagsChange"
        />
      </div>
      <AttrField
        class="at-fld"
        :def="modelDef"
        :model-value="modelValues"
        :options="[]"
        :missing="missingSet.has('型号名称')"
        @update:model-value="(v) => onUpdate(modelDef, v)"
      />
      <div class="at-ro">
        <label class="at-ro__k"><span class="at-req">*</span>原产国 / 制造国</label>
        <div class="at-ro__box">中国（Китай）</div>
      </div>
    </div>

    <template v-if="visibleGroups.aspects.length">
      <div class="at-head">
        <span class="at-head__t">区别特征（变体维度）<span class="at-head__s"> · 各变体不同，合并卡靠它区分</span></span>
      </div>
      <div class="at-aspects">
        <div v-for="def in visibleGroups.aspects" :key="def.id" class="at-aspect">
          <AttrField
            :def="def" :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
            :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="missingSet.has(def.id)"
            @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
          />
        </div>
      </div>
    </template>

    <template v-if="visibleGroups.required.length">
      <div class="at-sec__k">类目必填属性</div>
      <div class="at-grid">
        <AttrField
          v-for="def in visibleGroups.required" :key="def.id" class="at-fld"
          :def="def" :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
          :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="missingSet.has(def.id)"
          @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
        />
      </div>
      <div class="at-hint">品牌在“商品信息”tab 填。</div>
    </template>

    <div v-if="visibleGroups.optional.length" class="at-sec at-sec--optional">
      <SButton size="sm" @click="optionalOpen = !optionalOpen">
        {{ optionalOpen ? '收起可选项' : `展开可选项（${visibleGroups.optional.length}）` }}
      </SButton>
      <div v-if="optionalOpen" class="at-grid" style="margin-top:10px">
        <AttrField
          v-for="def in visibleGroups.optional" :key="def.id" class="at-fld"
          :def="def" :model-value="a.values[def.id] || []" :options="a.optionsOf(def.id)"
          :loading="a.loadingOf(def.id)" :oversized="a.oversizedOf(def.id)" :missing="false"
          @update:model-value="(v) => onUpdate(def, v)" @ensure="a.ensureOptions(def)" @search="(q) => a.search(def, q)"
        />
      </div>
    </div>

    <div v-if="!visibleGroups.aspects.length && !visibleGroups.required.length && !visibleGroups.optional.length"
         class="at-empty">先在“商品信息”tab 选好类目，再填特征。</div>
  </div>
</template>

<style scoped>
.attrs-tab { padding: var(--sp-3, 12px); }

.at-head { display: flex; align-items: center; justify-content: space-between; margin: 18px 0 10px; }
.at-head__t { font-size: 12px; font-weight: 700; color: var(--c-primary, #7c3aed); }
.at-head__s { font-weight: 400; color: #b8c0cc; }

.at-aspects { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 18px; }
.at-aspect { padding: 10px 12px; background: #faf8ff; border: 1px solid #ece6ff; border-radius: 9px; min-width: 0; }
.at-aspect :deep(.attr-field) { margin-bottom: 0; }

.at-sec { margin-bottom: 18px; }
.at-sec--optional { margin-bottom: 4px; }
.at-sec__k { font-size: 12px; font-weight: 700; color: #5b6675; margin-bottom: 8px; }
.at-label { display: block; font-size: var(--fs-sm, 13px); color: var(--c-text-2, #555); margin-bottom: 4px; }
.at-req { color: var(--c-danger, #e5484d); margin-right: 2px; }
.at-anno { font-size: 12.5px; color: #5b6675; line-height: 1.65; background: #fff; border: 1px solid rgba(0,0,0,.07); border-radius: 9px; padding: 10px 12px; }
.at-anno--missing { color: var(--c-danger, #e5484d); border-color: var(--c-danger, #e5484d); }

.at-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 16px; margin-bottom: 18px; }
.at-grid--system { grid-template-columns: 1fr 1fr; align-items: end; }
.at-fld { min-width: 0; }
.at-grid :deep(.attr-field) { margin-bottom: 0; }
.at-grid :deep(.attr-field__label) { margin-bottom: 4px; }

.at-ro { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.at-ro__k { font-size: var(--fs-sm, 13px); color: var(--c-text-2, #555); }
.at-ro__box {
  display: flex; align-items: center; height: 32px; padding: 0 11px; box-sizing: border-box;
  background: var(--c-bg, #f7f9fc); border: 1px solid var(--c-border, #e5e8ef);
  border-radius: 6px; font-size: 13px; color: var(--c-text-2, #555);
}

.is-missing :deep(.el-input__wrapper), .is-missing :deep(.el-textarea__inner) {
  box-shadow: 0 0 0 1px var(--c-danger, #e5484d) inset;
}
.at-hint { font-size: var(--fs-sm, 13px); color: var(--c-text-3, #888); margin: 10px 0 18px; }
.at-empty { font-size: var(--fs-sm, 13px); color: var(--c-text-3, #888); margin-top: var(--sp-2, 8px); }
@media (max-width: 860px) {
  .at-aspects, .at-grid, .at-grid--system { grid-template-columns: 1fr; }
}
</style>
