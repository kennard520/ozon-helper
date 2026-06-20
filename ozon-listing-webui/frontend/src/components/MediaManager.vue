<template>
  <section class="md-section">
    <div class="md-head">
      <h4>图片 <span class="ai-pill">AI</span></h4>
      <div class="md-actions">
        <slot name="image-actions" />
        <el-button>打开照片编辑器</el-button>
        <el-upload
          :show-file-list="false"
          accept="image/*"
          multiple
          :http-request="uploadImage"
        >
          <el-button type="primary">添加图片</el-button>
        </el-upload>
      </div>
    </div>
    <div v-if="images.length" class="md-grid ozon-media-grid">
      <div v-for="(u, i) in images" :key="i" class="md-cell">
        <el-image :src="disp(u)" :preview-src-list="images.map(disp)" :initial-index="i" fit="cover" loading="lazy" />
        <div class="md-badge" v-if="i === 0">主图</div>
        <div class="md-ops">
          <el-button link size="small" :disabled="i === 0" @click="moveUp(i)">上移</el-button>
          <el-button link size="small" :disabled="i === images.length - 1" @click="moveDown(i)">下移</el-button>
          <el-button link size="small" :disabled="i === 0" @click="setCover(i)">设主图</el-button>
          <el-button link size="small" type="danger" @click="removeImage(i)">删除</el-button>
        </div>
      </div>
      <div v-for="i in emptyImageSlots" :key="'empty-' + i" class="md-cell md-empty-cell"></div>
    </div>
    <div v-else class="md-empty">暂无图片</div>
    <div class="md-rule-note">要求：至少 10 张，3:4，JPEG/JPG/PNG/HEIC/WEBP，长边 200-7680 像素，单张不超过 10MB。</div>
    <slot name="image-extra" />
  </section>

  <section class="md-section">
    <div class="md-head">
      <h4>视频</h4>
      <div class="md-actions">
        <slot name="video-actions" />
        <el-upload
          :show-file-list="false"
          accept="video/*"
          :http-request="uploadVideo"
        >
          <el-button>添加视频</el-button>
        </el-upload>
      </div>
    </div>
    <div class="video-row">
      <div v-if="videoUrl" class="video-slot filled">
        <video :src="videoUrl" controls preload="metadata" />
        <div class="md-video-actions">
          <a :href="videoUrl" target="_blank" rel="noreferrer" class="md-video-link">打开 / 下载</a>
          <el-button link size="small" type="danger" @click="removeVideo">删除</el-button>
        </div>
      </div>
      <div v-for="i in (videoUrl ? 4 : 5)" :key="'video-empty-' + i" class="video-slot">空视频位</div>
    </div>
    <div class="md-rule-note">要求：MP4/MOV，长边 1080-1920 像素，8 秒至 5 分钟。</div>
  </section>

  <section class="md-section">
    <div class="md-head">
      <h4>视频封面</h4>
      <el-button>添加封面</el-button>
    </div>
    <div class="cover-row">
      <div class="cover-thumb"></div>
      <p>在商品卡片中加入短视频代替主图片，可以帮助买家从不同角度动态地查看商品。</p>
    </div>
  </section>

</template>

<script setup>
import { ElMessage } from 'element-plus'
import { computed } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  images: { type: Array, default: () => [] },
  videoUrl: { type: String, default: '' },
  draftId: { type: [Number, String], default: null },
  localMap: { type: Object, default: () => ({}) },
})

// 显示用 URL：优先本地副本(localMap 是 源url→/media 路径 的字典)。
// 1688 图(cbu01.alicdn.com)有防盗链，浏览器直接加载失败显示 FAILED；本地副本由 webui 托管无此问题。
// localMap 按 url 做 key(非下标)，删/移图不会错位。无本地副本(如 Ozon 图)则用源 url。
function disp(u) {
  return props.localMap[u] || u
}
const emit = defineEmits(['update:images', 'update:videoUrl'])
const emptyImageSlots = computed(() => Math.max(0, 12 - props.images.length))

function removeImage(i) {
  const next = props.images.slice()
  next.splice(i, 1)
  emit('update:images', next)
}

function setCover(i) {
  if (i <= 0) return
  const next = props.images.slice()
  const [pick] = next.splice(i, 1)
  next.unshift(pick)
  emit('update:images', next)
}

function moveUp(i) {
  if (i <= 0) return
  const next = props.images.slice()
  ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
  emit('update:images', next)
}

function moveDown(i) {
  if (i >= props.images.length - 1) return
  const next = props.images.slice()
  ;[next[i + 1], next[i]] = [next[i], next[i + 1]]
  emit('update:images', next)
}

function addImage(url) {
  if (!url) return
  emit('update:images', [...props.images, url])
}

function removeVideo() {
  emit('update:videoUrl', '')
}

function addVideo(url) {
  emit('update:videoUrl', url || '')
}

// 多选上传时 el-upload 会并发调多次 http-request；各自基于 props.images(旧值)addImage
// 会互相覆盖丢图。用 buffer 累积：本轮第一个上传时以 props.images 为基线，后续都往 buffer 追加；
// 一轮(所有并发)上传结束后清空 buffer，下轮重新以最新 props.images 为基线。
let _uploadBuffer = null
let _uploadInFlight = 0
async function uploadImage(opt) {
  if (_uploadBuffer === null) _uploadBuffer = props.images.slice()
  _uploadInFlight += 1
  try {
    const r = await api.uploadMedia(props.draftId, opt.file, 'image')
    _uploadBuffer = [..._uploadBuffer, r.url]
    emit('update:images', _uploadBuffer.slice())
    ElMessage.success('图片已上传')
  } catch (err) {
    ElMessage.error('上传失败：' + ((err && err.message) || err))
  } finally {
    _uploadInFlight -= 1
    if (_uploadInFlight === 0) _uploadBuffer = null   // 本轮结束，下轮重新取基线
  }
}

async function uploadVideo(opt) {
  try {
    const r = await api.uploadMedia(props.draftId, opt.file, 'video')
    addVideo(r.url)
    ElMessage.success('视频已上传')
  } catch (err) {
    ElMessage.error('上传失败：' + ((err && err.message) || err))
  }
}

defineExpose({ removeImage, setCover, removeVideo, addImage, addVideo, moveUp, moveDown, uploadImage, disp })
</script>

<style scoped>
.md-section { margin-bottom: 28px; }
.md-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.md-section h4 { margin: 0; font-size: 20px; }
.ai-pill {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(139,92,246,0.15);
  color: var(--gp-purple-soft);
  font-size: 13px;
}
.md-actions { display: flex; gap: 8px; align-items: center; }
.ozon-media-grid {
  display: grid;
  grid-template-columns: 2fr repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}
.md-cell {
  position: relative;
  min-height: 100px;
  aspect-ratio: 3 / 4;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 10px;
  background: rgba(0,0,0,0.03);
  overflow: hidden;
}
.md-cell:first-child {
  grid-row: span 2;
}
.md-cell .el-image {
  width: 100%;
  height: 100%;
  display: block;
}
.md-empty-cell {
  border-style: dashed;
  background: rgba(0,0,0,0.03);
}
.md-badge {
  position: absolute;
  left: 8px;
  bottom: 8px;
  z-index: 2;
  background: rgba(17, 24, 39, 0.78);
  color: var(--c-surface);
  font-size: 11px;
  font-weight: 700;
  padding: 3px 7px;
  border-radius: 999px;
}
.md-ops {
  position: absolute;
  inset: auto 6px 6px 6px;
  z-index: 3;
  display: none;
  flex-wrap: wrap;
  gap: 2px;
  padding: 4px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.95);
}
.md-cell:hover .md-ops { display: flex; }
.md-empty { color: var(--c-text-3); font-size: 13px; margin-bottom: 8px; }
.md-rule-note {
  padding: 10px 12px;
  border: 1px solid rgba(59,130,246,0.25);
  border-radius: 10px;
  background: rgba(59,130,246,0.1);
  color: var(--c-info);
  font-size: 12px;
  line-height: 1.5;
}
.video-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.video-slot {
  min-height: 82px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 10px;
  background: rgba(0,0,0,0.03);
  color: var(--gp-faint);
  font-size: 12px;
}
.video-slot.filled {
  display: block;
  padding: 6px;
}
.video-slot video {
  width: 100%;
  max-height: 120px;
  border-radius: 6px;
  display: block;
  margin-bottom: 6px;
}
.md-video-actions { display: flex; align-items: center; gap: 8px; }
.md-video-link { font-size: 12px; }
.cover-row {
  display: grid;
  grid-template-columns: 86px 1fr;
  gap: 14px;
  align-items: center;
}
.cover-thumb {
  width: 86px;
  aspect-ratio: 3 / 4;
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,0.08);
  background: rgba(0,0,0,0.04);
}
.cover-row p,
.rich-hint {
  color: var(--gp-muted);
  line-height: 1.6;
  margin: 0 0 12px;
}
</style>
