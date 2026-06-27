<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import RichContentPreview from '../../RichContentPreview.vue'
import { api } from '../../../api.js'

const props = defineProps({ draft: Object })

const richLoading = ref(false)

const richJson = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  return (sr && sr.rich_content_json) || null
})

async function doRichContent() {
  if (!props.draft || !props.draft.id) return
  richLoading.value = true
  try {
    const r = await api.makeRichContent(props.draft.id, {})
    if (r && r.ok) {
      ElMessage.success(`富文本已生成（${r.blocks} 张大图）`)
    } else {
      ElMessage.warning('生成完成，请刷新查看')
    }
  } catch (e) {
    ElMessage.error('生成失败：' + (e && e.message || ''))
  } finally {
    richLoading.value = false
  }
}
</script>

<template>
  <div class="richtext-tab">
    <div class="section-head" style="margin-bottom:12px">
      <div>
        <h3 style="margin:0 0 4px">富文本</h3>
        <p style="margin:0;color:var(--c-text-2,#666);font-size:13px">
          把图集拼成 Ozon A+ 富文本（每张图一个全宽块）。
        </p>
      </div>
    </div>

    <div class="rich-actions" style="margin-bottom:12px">
      <el-button size="small" :loading="richLoading" @click="doRichContent">生成富文本</el-button>
    </div>

    <template v-if="richJson">
      <div class="rich-section-title" style="margin-bottom:6px;font-weight:600">富文本预览</div>
      <RichContentPreview :rich-json="richJson" />
    </template>
    <div v-else class="rich-empty" style="color:var(--c-text-2,#999)">
      还没有富文本，点上面「生成富文本」生成。
    </div>
  </div>
</template>
