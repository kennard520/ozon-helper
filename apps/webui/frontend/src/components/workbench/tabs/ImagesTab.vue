<script setup>
import { ref, computed, toRef } from 'vue'
import JSZip from 'jszip'
import { ElMessage, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import { api } from '../../../api.js'
import { useWorkbenchStore } from '../../../stores/workbench.js'
import { useGallery } from '../../../composables/useGallery.js'
import ImageCard from '../ImageCard.vue'
import GenImageModal from '../GenImageModal.vue'
import { SButton } from '../../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['saved'])
const draftRef = toRef(props, 'draft')
const wb = useWorkbenchStore()
const g = useGallery(draftRef, { onChange: () => emit('saved') })

const selMaterials = ref([])
const siblings = computed(() => wb.variants.filter((v) => v.id !== props.draft.id))

function toggleMat(id) {
  const i = selMaterials.value.indexOf(id)
  if (i >= 0) selMaterials.value.splice(i, 1)
  else selMaterials.value.push(id)
}

async function addOne(id) {
  await g.addToGallery([id])
}

async function batchAdd() {
  if (!selMaterials.value.length) return
  await g.addToGallery(selMaterials.value.slice())
  selMaterials.value = []
}

async function delImg(id) {
  try {
    await ElMessageBox.confirm('彻底删除这张图（素材与图集都会删除）？', '确认', { type: 'warning' })
  } catch {
    return
  }
  await g.removeImage(id)
}

const fileInput = ref(null)
function pickFile() {
  fileInput.value && fileInput.value.click()
}

async function onFile(e) {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  await g.upload(f)
  e.target.value = ''
  ElMessage.success('已上传到图集')
}

const genOpen = ref(false)
function openGen() {
  genOpen.value = true
}
function onGenerated() {
  emit('saved')
}

const copyOpen = ref(false)
const copyTargets = ref([])
const copyUrls = ref([])
const copyLoading = ref(false)

function toggleCopyPanel() {
  copyOpen.value = !copyOpen.value
  if (copyOpen.value) {
    copyTargets.value = []
    copyUrls.value = g.galleryItems.value.map((it) => it.url)
  }
}

function toggleCopyUrl(url) {
  const i = copyUrls.value.indexOf(url)
  if (i >= 0) copyUrls.value.splice(i, 1)
  else copyUrls.value.push(url)
}

async function doCopyTo() {
  if (!copyTargets.value.length || !copyUrls.value.length) return
  copyLoading.value = true
  try {
    await api.copyImagesTo(props.draft.id, copyUrls.value.slice(), copyTargets.value.slice())
    ElMessage.success(`已复制 ${copyUrls.value.length} 张到 ${copyTargets.value.length} 个变体`)
    copyOpen.value = false
    emit('saved')
  } catch (e) {
    ElMessage.warning(`复制失败：${e && e.message ? e.message : e}`)
  } finally {
    copyLoading.value = false
  }
}

const downloadBusy = ref(false)

function sanitizeNamePart(value, fallback = 'item') {
  const s = String(value || '').trim()
    .replace(/[\\/:*?"<>|#%&{}$!'@+=`~]/g, '')
    .replace(/[\s,，;；|/]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
  return (s || fallback).slice(0, 60)
}

function sourceName() {
  const d = props.draft || {}
  const raw = d.source_raw || {}
  const url = String(d.source_url || d.purchase_url || raw.url || raw.source_url || '')
  if (d.source_platform) return sanitizeNamePart(d.source_platform, 'source')
  if (d.source) return sanitizeNamePart(d.source, 'source')
  if (/1688\.com/.test(url)) return '1688'
  if (/taobao\.com/.test(url)) return 'taobao'
  return 'source'
}

function variantParts() {
  const d = props.draft || {}
  const raw = d.source_raw || {}
  const text = [
    wb.currentVariant && wb.currentVariant.spec,
    d.spec,
    d.variant_name,
    raw.variant_label,
    raw.sku_name,
    raw.spec,
  ].find(Boolean) || `variant-${d.id || wb.currentVariantId || 'current'}`
  return String(text).split(/[\s,，;；|/]+/).map((x) => sanitizeNamePart(x, '')).filter(Boolean)
}

function galleryBaseName() {
  return [sourceName(), ...variantParts()].map((x) => sanitizeNamePart(x, '')).filter(Boolean).join('-') || 'gallery'
}

function extFromUrlOrType(url, type) {
  const m = String(url || '').toLowerCase().match(/\.([a-z0-9]+)(?:[?#]|$)/)
  if (m) return m[1] === 'jpeg' ? 'jpg' : m[1]
  if (type && String(type).includes('/')) return String(type).split('/').pop().replace('jpeg', 'jpg')
  return 'jpg'
}

async function mapLimit(items, limit, fn) {
  let next = 0
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next
      next += 1
      await fn(items[index], index)
    }
  })
  await Promise.all(workers)
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function downloadAllGallery() {
  const items = g.galleryItems.value.slice()
  if (!items.length || downloadBusy.value) return
  downloadBusy.value = true
  try {
    const zip = new JSZip()
    const base = galleryBaseName()
    const failures = []
    await mapLimit(items, 4, async (it, index) => {
      const url = g.localUrlOf(it) || it.url
      try {
        const resp = await fetch(url, { credentials: 'same-origin' })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const blob = await resp.blob()
        const ext = extFromUrlOrType(url, blob.type)
        zip.file(`${base}-${String(index + 1).padStart(2, '0')}.${ext}`, blob)
      } catch (e) {
        failures.push({ index, error: e })
      }
    })
    if (!Object.keys(zip.files).length) throw new Error('图片下载失败')
    const blob = await zip.generateAsync({ type: 'blob' })
    saveBlob(blob, `${base}-图集.zip`)
    if (failures.length) ElMessage.warning(`已下载 ${items.length - failures.length} 张，${failures.length} 张失败`)
    else ElMessage.success(`已打包 ${items.length} 张图片`)
  } catch (e) {
    ElMessage.warning(`下载失败：${e && e.message ? e.message : e}`)
  } finally {
    downloadBusy.value = false
  }
}

const lightbox = ref('')
function openLightbox(url) {
  lightbox.value = url || ''
}
function closeLightbox() {
  lightbox.value = ''
}

function extOf(url) {
  const m = String(url || '').toLowerCase().match(/\.([a-z0-9]+)(?:[?#]|$)/)
  return m ? m[1] : ''
}

const ALLOWED_EXT = ['jpg', 'jpeg', 'png']
const compliance = computed(() => {
  const items = g.galleryItems.value
  const count = items.length
  const exts = items.map((it) => extOf(it.url || it.local_url))
  const known = exts.filter(Boolean)
  const bad = known.filter((e) => !ALLOWED_EXT.includes(e))
  const formatState = count === 0 ? 'unknown'
    : bad.length ? 'bad'
      : known.length < count ? 'warn'
        : 'ok'
  return {
    count,
    rows: [
      { key: 'count', label: `张数 >= 10（当前 ${count}）`, state: count >= 10 ? 'ok' : (count ? 'warn' : 'bad') },
      { key: 'format', label: '格式 jpg / png', state: formatState },
      { key: 'ratio', label: '比例 3:4', state: 'unknown' },
      { key: 'edge', label: '长边 >= 1600px', state: 'unknown' },
      { key: 'size', label: '单张 <= 10MB', state: 'unknown' },
    ],
  }
})
const badgeText = { ok: '达标', warn: '注意', bad: '不达标', unknown: '未知' }
</script>

<template>
  <div class="images-tab">
    <div class="images-tab__actions">
      <SButton variant="primary" @click="openGen">AI 生图</SButton>
      <SButton v-if="siblings.length" :variant="copyOpen ? 'primary' : 'ghost'" @click="toggleCopyPanel">复制到别的变体</SButton>
    </div>

    <section v-if="copyOpen && siblings.length" class="copy-panel">
      <div class="copy-panel__row">
        <span class="images-tab__title">目标变体</span>
        <ElSelect v-model="copyTargets" multiple collapse-tags placeholder="选择要复制到的同组变体" style="min-width:260px">
          <ElOption v-for="v in siblings" :key="v.id" :label="v.spec || `变体 ${v.id}`" :value="v.id" />
        </ElSelect>
      </div>
      <div class="copy-panel__row">
        <span class="images-tab__title">复制这些图（默认当前图集全部，{{ copyUrls.length }} 张）</span>
      </div>
      <div v-if="g.galleryItems.value.length" class="images-tab__grid">
        <ImageCard
          v-for="it in g.galleryItems.value"
          :key="it.id"
          :url="it.url"
          :local-url="g.localUrlOf(it)"
          :type="it.type"
          :source="it.source"
          selectable
          :selected="copyUrls.includes(it.url)"
          @zoom="openLightbox"
          @toggle-select="toggleCopyUrl(it.url)"
        />
      </div>
      <div v-else class="images-tab__empty">当前图集为空，无图可复制。</div>
      <div class="copy-panel__foot">
        <SButton
          size="sm"
          variant="primary"
          :loading="copyLoading"
          :disabled="!copyTargets.length || !copyUrls.length"
          @click="doCopyTo"
        >
          复制 {{ copyUrls.length }} 张到 {{ copyTargets.length }} 个变体
        </SButton>
        <SButton size="sm" @click="copyOpen = false">取消</SButton>
      </div>
    </section>

    <section class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">图集（发布顺序，{{ g.galleryItems.value.length }}）</span>
        <SButton size="sm" :loading="downloadBusy" :disabled="!g.galleryItems.value.length" @click="downloadAllGallery">下载全部</SButton>
        <SButton size="sm" @click="pickFile">上传图片</SButton>
        <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onFile" />
      </div>

      <div class="compliance" role="list" aria-label="Ozon 图集合规自查">
        <span class="compliance__hint">Ozon 要求</span>
        <span
          v-for="r in compliance.rows"
          :key="r.key"
          role="listitem"
          class="compliance__b"
          :class="`is-${r.state}`"
          :title="r.state === 'unknown' ? '前端无法获取真实像素/文件大小，仅作建议' : ''"
        >
          {{ r.label }} · {{ badgeText[r.state] }}
        </span>
      </div>

      <div v-if="g.galleryItems.value.length" class="images-tab__grid">
        <ImageCard
          v-for="(it, i) in g.galleryItems.value"
          :key="it.id"
          :url="it.url"
          :local-url="g.localUrlOf(it)"
          :type="it.type"
          :source="it.source"
          :badge="String(i + 1)"
          @zoom="openLightbox"
        >
          <template #actions>
            <button class="ic-btn" :disabled="i === 0" title="上移" @click="g.moveUp(it.id)">↑</button>
            <button class="ic-btn" :disabled="i === g.galleryItems.value.length - 1" title="下移" @click="g.moveDown(it.id)">↓</button>
            <button class="ic-btn" title="移出图集" @click="g.removeFromGallery([it.id])">−</button>
            <button class="ic-btn ic-btn--danger" title="删除" @click="delImg(it.id)">×</button>
          </template>
        </ImageCard>
      </div>
      <div v-else class="images-tab__empty">图集为空，从下方素材库选图加入；采集图会先进入素材库。</div>
    </section>

    <section class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">素材库（{{ g.materialItems.value.length }}）</span>
        <SButton v-if="selMaterials.length" size="sm" variant="primary" @click="batchAdd">批量加入图集（{{ selMaterials.length }}）</SButton>
      </div>
      <div v-if="g.materialItems.value.length" class="images-tab__grid">
        <ImageCard
          v-for="m in g.materialItems.value"
          :key="m.id"
          :url="m.url"
          :local-url="g.localUrlOf(m)"
          :type="m.type"
          :source="m.source"
          selectable
          :selected="selMaterials.includes(m.id)"
          @zoom="openLightbox"
          @toggle-select="toggleMat(m.id)"
        >
          <template #actions>
            <button class="ic-btn" title="加入图集" @click.stop="addOne(m.id)">加入图集</button>
            <button class="ic-btn ic-btn--danger" title="删除" @click.stop="delImg(m.id)">×</button>
          </template>
        </ImageCard>
      </div>
      <div v-else class="images-tab__empty">没有未入图集的素材。</div>
    </section>

    <div v-if="lightbox" class="lightbox" @click="closeLightbox">
      <button class="lightbox__close" title="关闭" aria-label="关闭" @click.stop="closeLightbox">×</button>
      <img class="lightbox__img" :src="lightbox" alt="" @click.stop>
    </div>

    <GenImageModal v-model="genOpen" :draft="draft" @generated="onGenerated" @zoom="openLightbox" />
  </div>
</template>

<style scoped>
.images-tab{padding:var(--sp-3,12px)}
.images-tab__sec{margin-bottom:var(--sp-5,20px)}
.images-tab__actions{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-4,16px)}
.images-tab__head{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-2,8px);flex-wrap:wrap}
.images-tab__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.images-tab__grid{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px)}
.images-tab__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888)}
.ic-btn{border:none;background:transparent;cursor:pointer;font-size:11px;padding:1px 4px;color:var(--c-text-2,#555)}
.ic-btn:hover{color:var(--c-primary,#7c3aed)}
.ic-btn--danger:hover{color:var(--c-danger,#e5484d)}
.ic-btn:disabled{opacity:.35;cursor:not-allowed}
.copy-panel{margin-bottom:var(--sp-5,20px);padding:var(--sp-3,12px);border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);background:var(--c-primary-50,#faf7ff)}
.copy-panel__row{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-2,8px)}
.copy-panel__foot{display:flex;align-items:center;gap:var(--sp-2,8px);margin-top:var(--sp-3,12px)}
.compliance{display:flex;flex-wrap:wrap;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-3,12px)}
.compliance__hint{font-size:var(--fs-xs,12px);font-weight:600;color:var(--c-text-3,#888)}
.compliance__b{font-size:var(--fs-xs,12px);padding:2px 8px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.compliance__b.is-ok{background:var(--c-success-bg,#ecfdf5);color:var(--c-success,#10b981);border-color:var(--c-success,#10b981)}
.compliance__b.is-warn{background:var(--c-warn-bg,#fffbeb);color:var(--c-warn,#b45309);border-color:#f3dca0}
.compliance__b.is-bad{background:var(--c-danger-bg,#fef2f2);color:var(--c-danger,#ef4444);border-color:#f3b4b4}
.compliance__b.is-unknown{background:var(--c-bg,#f7f9fc);color:var(--c-text-3,#888);border-color:var(--c-border,#e5e8ef);cursor:help}
.lightbox{position:fixed;inset:0;z-index:3000;display:flex;align-items:center;justify-content:center;background:rgba(15,18,28,.82);padding:var(--sp-5,24px);cursor:zoom-out}
.lightbox__img{max-width:92vw;max-height:92vh;object-fit:contain;border-radius:var(--r-sm,8px);box-shadow:var(--sh-pop,0 8px 24px rgba(20,20,40,.12));cursor:default}
.lightbox__close{position:fixed;top:18px;right:22px;width:36px;height:36px;border:none;cursor:pointer;border-radius:50%;background:rgba(255,255,255,.92);color:var(--c-text,#1f2733);font-size:16px;line-height:1}
.lightbox__close:hover{background:#fff}
</style>
