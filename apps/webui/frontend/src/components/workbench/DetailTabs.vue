<script setup>
import { ref, computed } from 'vue'
import { useWorkbenchStore } from '../../stores/workbench.js'
import { useDraftForm } from '../../composables/useDraftForm.js'
import { STabs } from '../../ui/index.js'
import InfoTab from './tabs/InfoTab.vue'
import PurchaseTab from './tabs/PurchaseTab.vue'
import VideoTab from './tabs/VideoTab.vue'
import RichTextTab from './tabs/RichTextTab.vue'

const wb = useWorkbenchStore()
const fm = useDraftForm(computed(() => wb.currentVariantId))
const active = ref('info')
const TABS = [
  { key: 'info', label: '商品信息' }, { key: 'attrs', label: '特征' },
  { key: 'images', label: '图片' }, { key: 'video', label: '视频' },
  { key: 'richtext', label: '富文本' }, { key: 'purchase', label: '采购信息' },
]
</script>
<template>
  <div v-if="wb.currentVariantId != null" class="dt">
    <STabs :items="TABS" :active-key="active" @change="(k) => active = k" />
    <div class="dt__body">
      <InfoTab v-if="active === 'info'" :form="fm.form" :draft="fm.draft.value" @save="fm.save" />
      <PurchaseTab v-else-if="active === 'purchase'" :form="fm.form" @save="fm.save" />
      <VideoTab v-else-if="active === 'video'" :draft="fm.draft.value" @save="fm.save" />
      <RichTextTab v-else-if="active === 'richtext'" :draft="fm.draft.value" />
      <div v-else-if="active === 'attrs'" class="dt__ph">特征 tab 将在 F1d-2 实现</div>
      <div v-else-if="active === 'images'" class="dt__ph">图片 tab 将在 F1d-3 实现(接素材/图集)</div>
    </div>
  </div>
</template>
<style scoped>
.dt{margin-top:var(--sp-5);border-top:1px solid var(--c-border);padding-top:var(--sp-4)}
.dt__body{margin-top:var(--sp-4)}
.dt__ph{color:var(--c-text-3);font-size:var(--fs-sm);padding:var(--sp-5)}
</style>
