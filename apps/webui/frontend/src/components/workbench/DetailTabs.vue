<script setup>
import { ref, computed } from 'vue'
import { useWorkbenchStore } from '../../stores/workbench.js'
import { useDraftForm } from '../../composables/useDraftForm.js'
import { STabs } from '../../ui/index.js'
import InfoTab from './tabs/InfoTab.vue'
import PurchaseTab from './tabs/PurchaseTab.vue'
import VideoTab from './tabs/VideoTab.vue'
import RichTextTab from './tabs/RichTextTab.vue'
import AttributesTab from './tabs/AttributesTab.vue'
import ImagesTab from './tabs/ImagesTab.vue'
import ProposalPanel from './ProposalPanel.vue'

const wb = useWorkbenchStore()
const fm = useDraftForm(computed(() => wb.currentVariantId))
const active = ref('info')
function onProposalApplied() { fm.load(); wb.reload() }
const TABS = [
  { key: 'info', label: '商品信息' }, { key: 'attrs', label: '特征' },
  { key: 'images', label: '图片' }, { key: 'video', label: '视频' },
  { key: 'richtext', label: '富文本' }, { key: 'purchase', label: '采购信息' },
]
</script>
<template>
  <div v-if="wb.currentVariantId != null" class="dt">
    <ProposalPanel :draft="fm.draft.value" @applied="onProposalApplied" />
    <STabs :items="TABS" :active-key="active" @change="(k) => active = k" />
    <div class="dt__body">
      <InfoTab v-if="active === 'info'" :form="fm.form" :draft="fm.draft.value" @save="fm.save" />
      <PurchaseTab v-else-if="active === 'purchase'" :form="fm.form" @save="fm.save" />
      <VideoTab v-else-if="active === 'video'" :draft="fm.draft.value" @save="fm.save" />
      <RichTextTab v-else-if="active === 'richtext'" :draft="fm.draft.value" />
      <AttributesTab v-else-if="active === 'attrs'" :draft="fm.draft.value" @saved="fm.load" />
      <ImagesTab v-else-if="active === 'images'" :draft="fm.draft.value" @saved="fm.load" />
    </div>
  </div>
</template>
<style scoped>
.dt{margin-top:var(--sp-5);border-top:1px solid var(--c-border);padding-top:var(--sp-4)}
.dt__body{margin-top:var(--sp-4)}
.dt__ph{color:var(--c-text-3);font-size:var(--fs-sm);padding:var(--sp-5)}
</style>
