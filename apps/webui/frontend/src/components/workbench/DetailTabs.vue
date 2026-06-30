<script setup>
import { ref, computed } from 'vue'
import { useWorkbenchStore, variantColorName } from '../../stores/workbench.js'
import { useDraftForm } from '../../composables/useDraftForm.js'
import { SButton, STabs } from '../../ui/index.js'
import InfoTab from './tabs/InfoTab.vue'
import PurchaseTab from './tabs/PurchaseTab.vue'
import VideoTab from './tabs/VideoTab.vue'
import RichTextTab from './tabs/RichTextTab.vue'
import AttributesTab from './tabs/AttributesTab.vue'
import ImagesTab from './tabs/ImagesTab.vue'

const wb = useWorkbenchStore()
const fm = useDraftForm(computed(() => wb.currentVariantId))
const draftSafe = computed(() => fm.draft.value || {})
const active = ref('info')
const saving = ref(false)

const SYS_ATTR_IDS = new Set([9048, 23171, 85])
const ready = computed(() => {
  const d = fm.draft.value || {}
  const attrs = Array.isArray(d.attributes) ? d.attributes : []
  const hasAttr = attrs.some((a) => a && !SYS_ATTR_IDS.has(Number(a.id))
    && Array.isArray(a.values) && a.values.length > 0)
  const mats = Array.isArray(d.materials) ? d.materials : []
  const hasGallery = mats.some((m) => m && m.in_gallery)
  const hasVideo = !!d.video_url
  const sr = d.source_raw || {}
  const hasRich = !!(sr && sr.rich_content_json)
  return { attrs: hasAttr, images: hasGallery, video: hasVideo, richtext: hasRich }
})

const TABS = computed(() => [
  { key: 'info', label: '商品信息' },
  { key: 'attrs', label: '特征', ready: ready.value.attrs },
  { key: 'images', label: '图片', ready: ready.value.images },
  { key: 'video', label: '视频', ready: ready.value.video },
  { key: 'richtext', label: '富文本', ready: ready.value.richtext },
  { key: 'purchase', label: '采购信息' },
])

const cur = computed(() => wb.currentVariant)
const curSpec = computed(() => (cur.value && cur.value.spec) || variantColorName(cur.value) || '当前变体')
const curPos = computed(() => (wb.currentVariantIndex >= 0 ? wb.currentVariantIndex + 1 : 1))
const total = computed(() => wb.variantCount)
const scopeText = computed(() => `正在编辑 ${curSpec.value}（${curPos.value}/${total.value}）`)
const detailLoading = computed(() => !!fm.loading.value)

async function refreshDetail() {
  await fm.load()
  await wb.reload()
}

async function saveDetail() {
  if (saving.value) return
  saving.value = true
  try {
    await fm.save()
    await fm.load()
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="wb.currentVariantId != null" class="dt">
    <div class="dt-head">
      <div class="dt-head__title">
        <strong>变体详情</strong>
        <span class="dt-head__scope">{{ scopeText }}</span>
      </div>
      <div class="dt-actions">
        <SButton size="sm" variant="primary" :loading="saving" :disabled="detailLoading" @click="saveDetail">
          保存
        </SButton>
        <button class="dt-refresh" :disabled="detailLoading" @click="refreshDetail">
          {{ detailLoading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <STabs :items="TABS" :active-key="active" @change="(k) => active = k" />
    <div class="dt__body">
      <InfoTab v-if="active === 'info'" :form="fm.form" :draft="draftSafe" />
      <PurchaseTab v-else-if="active === 'purchase'" :form="fm.form" />
      <VideoTab v-else-if="active === 'video'" :draft="draftSafe" @save="fm.save" />
      <RichTextTab v-else-if="active === 'richtext'" :draft="draftSafe" @saved="fm.load" />
      <AttributesTab v-else-if="active === 'attrs'" :draft="draftSafe" :form="fm.form" @saved="fm.load" @save-info="fm.save" />
      <ImagesTab v-else-if="active === 'images'" :draft="draftSafe" @saved="fm.load" />
    </div>
  </div>
  <div v-else class="dt dt--empty">
    <div class="dt-empty__i">🎯</div>
    <div class="dt-empty__t">选择至少一个变体查看详情</div>
    <div class="dt-empty__s">在上方选择一个变体，即可在此查看并编辑商品信息、特征、图片等明细。</div>
  </div>
</template>

<style scoped>
.dt{margin-top:var(--sp-5);border-top:1px solid var(--c-border);padding-top:var(--sp-4)}
.dt__body{margin-top:var(--sp-4)}
.dt-head{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-3);flex-wrap:wrap;margin-bottom:var(--sp-4)}
.dt-head__title{display:flex;align-items:center;gap:var(--sp-2);min-width:0}
.dt-head__title strong{font-size:var(--fs-md);color:var(--c-text-1)}
.dt-head__scope{font-size:var(--fs-xs);color:var(--c-text-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dt-actions{display:flex;align-items:center;gap:var(--sp-2)}
.dt-refresh{height:30px;padding:0 var(--sp-3);border:1px solid var(--c-border);background:#fff;border-radius:var(--r-sm);cursor:pointer;color:var(--c-text-2);font-size:var(--fs-sm)}
.dt-refresh:hover{background:var(--c-primary-50)}
.dt-refresh:disabled{opacity:.55;cursor:wait}
.dt__ph{color:var(--c-text-3);font-size:var(--fs-sm);padding:var(--sp-5)}
.dt--empty{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:var(--sp-6) var(--sp-5);color:var(--c-text-3)}
.dt-empty__i{font-size:36px;margin-bottom:var(--sp-3);opacity:.85}
.dt-empty__t{font-size:var(--fs-md);font-weight:600;color:var(--c-text-2);margin-bottom:var(--sp-1)}
.dt-empty__s{font-size:var(--fs-sm);color:var(--c-text-3);max-width:340px;line-height:1.6}
</style>
