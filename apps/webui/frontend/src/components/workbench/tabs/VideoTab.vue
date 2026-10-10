<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import MediaManager from '../../MediaManager.vue'
import AiVideoDialog from '../../AiVideoDialog.vue'
import { api } from '../../../api.js'

const props = defineProps({ draft: Object })
const emit = defineEmits(['save'])

const aiVidDlg = ref(false)

// 给 AiVideoDialog 用的图列表（url + disp）
const aiDialogImages = computed(() => {
  const imgs = (props.draft && props.draft.images) || []
  return imgs.map(u => ({ url: u, disp: u }))
})

async function onVideoChange(url) {
  const r = await api.patchDraft(props.draft.id, { video_url: url })
  if (r && r.draft) emit('save', r.draft)
}

async function openAiVideo() {
  aiVidDlg.value = true
}

async function onAiVideoDone() {
  // 视频在后台写库，通知父级刷新
  emit('save')
}
</script>

<template>
  <div class="video-tab">
    <div class="section-head" style="margin-bottom:12px">
      <div>
        <h3 style="margin:0 0 4px">视频</h3>
        <p style="margin:0;color:var(--c-text-2,#666);font-size:13px">上传视频，或用主图 AI 生成短视频。</p>
      </div>
    </div>

    <MediaManager
      only="video"
      :images="(draft && draft.images) || []"
      :video-url="(draft && draft.video_url) || ''"
      :draft-id="draft && draft.id"
      :local-map="{}"
      @update:images="() => {}"
      @update:videoUrl="onVideoChange"
    >
      <template #video-actions>
        <el-button size="small" @click="openAiVideo">AI 生成视频</el-button>
      </template>
    </MediaManager>

    <AiVideoDialog
      v-model="aiVidDlg"
      :draft-id="draft && draft.id"
      :images="aiDialogImages"
      @done="onAiVideoDone"
    />
  </div>
</template>
