<template>
  <el-dialog
    :model-value="modelValue"
    title="AI 生成视频（Agnes，约 5 秒）"
    width="560px"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <el-form label-width="90px" label-position="left">
      <el-form-item label="参考图">
        <div class="src-pick">
          <div
            v-for="(im, i) in images" :key="i"
            class="src-item" :class="{ active: imageUrl === im.url }"
            @click="imageUrl = im.url"
          >
            <img :src="im.disp" loading="lazy" />
          </div>
        </div>
        <div class="hint">图生视频：以选中图为第一帧做商品展示运镜。</div>
      </el-form-item>

      <el-form-item label="提示词">
        <el-input v-model="prompt" type="textarea" :rows="3"
                  placeholder="留空用默认：环绕运镜商品展示（产品保持一致）" />
      </el-form-item>
    </el-form>

    <div v-if="job.status !== 'idle'" class="job-box">
      <template v-if="job.status === 'running'">
        <el-progress :percentage="job.progress" :stroke-width="14" striped striped-flow />
        <div class="hint">生成中（草稿 #{{ job.draft_id }}），完成后自动写入该草稿的视频。可关闭窗口，后台继续。</div>
      </template>
      <div v-else-if="job.status === 'done'" class="ok">✓ 已完成并写入草稿 #{{ job.draft_id }}</div>
      <div v-else-if="job.status === 'error'" class="err">生成失败：{{ job.last_error }}</div>
      <div v-else-if="job.status === 'stopped'" class="hint">已停止</div>
    </div>

    <template #footer>
      <el-button v-if="job.status === 'running'" type="danger" plain @click="stop">停止任务</el-button>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button type="primary" :disabled="job.status === 'running'" :loading="starting" @click="start">
        开始生成
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  draftId: { type: Number, required: true },
  images: { type: Array, default: () => [] },   // [{url, disp}]
})
const emit = defineEmits(['update:modelValue', 'done'])

const prompt = ref('')
const imageUrl = ref('')
const starting = ref(false)
// 后端全局单任务状态机（batch_collect 同款）：idle/running/done/error/stopped
const job = reactive({ status: 'idle', progress: 0, draft_id: 0, last_error: '', url: '' })
let timer = null

function applyStatus(r) {
  job.status = r.status || 'idle'
  job.progress = Number(r.progress) || 0
  job.draft_id = Number(r.draft_id) || 0
  job.last_error = r.last_error || ''
  job.url = r.url || ''
}

function stopPolling() {
  if (timer) { clearInterval(timer); timer = null }
}

function startPolling() {
  stopPolling()
  timer = setInterval(async () => {
    try {
      const r = await api.aiVideoStatus()
      const wasRunning = job.status === 'running'
      applyStatus(r)
      if (r.status === 'running') return
      stopPolling()
      if (r.status === 'done' && wasRunning) {
        ElMessage.success('视频已生成并写入草稿')
        emit('done', r)
      } else if (r.status === 'error' && wasRunning) {
        ElMessage.error('视频生成失败：' + (r.last_error || ''))
      }
    } catch { /* 轮询网络抖动静默忽略 */ }
  }, 3000)
}

// 打开时：默认选第一张图（上次选的图已不在图集时重置）+ 拉一次状态
// （页面刷新/重开也能接上还在跑的任务）。
// 关窗时不停轮询：任务在后台继续，跑完才能回写草稿并通知父组件刷新；
// 轮询在到达终态或组件卸载（切草稿/离开页面）时停。
watch(() => props.modelValue, async (open) => {
  if (!open) return
  if (!props.images.some((im) => im.url === imageUrl.value)) {
    imageUrl.value = props.images.length ? props.images[0].url : ''
  }
  try {
    const r = await api.aiVideoStatus()
    applyStatus(r)
    if (r.status === 'running') startPolling()
  } catch { /* 状态拉不到不阻塞 UI */ }
}, { immediate: true })

onBeforeUnmount(stopPolling)

async function start() {
  if (!props.images.length) { ElMessage.warning('草稿没有图片，无法图生视频'); return }
  starting.value = true
  try {
    const r = await api.aiVideo(props.draftId, {
      prompt: String(prompt.value || '').trim() || undefined,
      image_url: imageUrl.value || undefined,
    })
    applyStatus(r)
    if (r.status === 'running' && r.draft_id !== props.draftId) {
      ElMessage.warning(`已有任务在跑（草稿 #${r.draft_id}），请等它完成`)
      return
    }
    startPolling()
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally {
    starting.value = false
  }
}

async function stop() {
  try { applyStatus(await api.aiVideoStop()) } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  }
}

defineExpose({ prompt, imageUrl, job, start, stop, startPolling, applyStatus })
</script>

<style scoped>
.src-pick { display: flex; flex-wrap: wrap; gap: 6px; }
.src-item { width: 64px; height: 64px; border: 2px solid transparent; border-radius: 4px;
  overflow: hidden; cursor: pointer; }
.src-item.active { border-color: var(--c-brand); }
.src-item img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hint { font-size: 12px; color: var(--c-text-3); margin-top: 6px; }
.job-box { margin-top: 8px; padding: 10px 12px; background: var(--c-surface-2); border: 1px solid rgba(59,130,246,0.25); border-radius: 6px; }
.ok { color: var(--c-success); }
.err { color: var(--c-danger); }
</style>
