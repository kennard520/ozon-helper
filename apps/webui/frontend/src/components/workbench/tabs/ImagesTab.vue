<script setup>
import { ref, computed, toRef } from 'vue'
import { ElMessage, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import { useWorkbenchStore } from '../../../stores/workbench.js'
import { useGallery } from '../../../composables/useGallery.js'
import ImageCard from '../ImageCard.vue'
import { SButton } from '../../../ui/index.js'

const props = defineProps({ draft: { type: Object, default: () => ({}) } })
const emit = defineEmits(['saved'])
const draftRef = toRef(props, 'draft')
const wb = useWorkbenchStore()
const g = useGallery(draftRef, { onChange: () => emit('saved') })

const selMaterials = ref([])           // 素材多选 id
const toggleMat = (id) => { const i = selMaterials.value.indexOf(id); i >= 0 ? selMaterials.value.splice(i, 1) : selMaterials.value.push(id) }

const siblings = computed(() => wb.variants.filter((v) => v.id !== props.draft.id))
const borrowId = ref(null)
const borrowMats = ref([])
const borrowSel = ref([])
async function onBorrowPick(id) {
  borrowId.value = id; borrowSel.value = []
  borrowMats.value = id != null ? await g.fetchSiblingMaterials(id) : []
}
const toggleBorrow = (url) => { const i = borrowSel.value.indexOf(url); i >= 0 ? borrowSel.value.splice(i, 1) : borrowSel.value.push(url) }

async function addOne(id) { await g.addToGallery([id]) }
async function batchAdd() { if (selMaterials.value.length) { await g.addToGallery(selMaterials.value.slice()); selMaterials.value = [] } }
async function delImg(id) {
  try { await ElMessageBox.confirm('彻底删除这张图（素材与图集都删）？', '确认', { type: 'warning' }) } catch { return }
  await g.removeImage(id)
}
async function doBorrow() {
  if (!borrowId.value || !borrowSel.value.length) return
  await g.copyFrom(borrowId.value, borrowSel.value.slice())
  ElMessage.success(`已借 ${borrowSel.value.length} 张到图集`); borrowSel.value = []
}
const fileInput = ref(null)
function pickFile() { fileInput.value && fileInput.value.click() }
async function onFile(e) {
  const f = e.target.files && e.target.files[0]; if (!f) return
  await g.upload(f); e.target.value = ''; ElMessage.success('已上传到图集')
}
</script>

<template>
  <div class="images-tab">
    <!-- 图集段 -->
    <section class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">图集（发布顺序，{{ g.galleryItems.value.length }}）</span>
        <SButton size="sm" @click="pickFile">上传图片</SButton>
        <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onFile" />
      </div>
      <div v-if="g.galleryItems.value.length" class="images-tab__grid">
        <ImageCard v-for="(it, i) in g.galleryItems.value" :key="it.id"
          :url="it.url" :local-url="g.localUrl(it.url)" :type="it.type" :source="it.source" :badge="String(i + 1)">
          <template #actions>
            <button class="ic-btn" :disabled="i === 0" title="上移" @click="g.moveUp(it.id)">↑</button>
            <button class="ic-btn" :disabled="i === g.galleryItems.value.length - 1" title="下移" @click="g.moveDown(it.id)">↓</button>
            <button class="ic-btn" title="移出图集" @click="g.removeFromGallery([it.id])">−</button>
            <button class="ic-btn ic-btn--danger" title="删除" @click="delImg(it.id)">✕</button>
          </template>
        </ImageCard>
      </div>
      <div v-else class="images-tab__empty">图集为空，从下方素材库选图加入。</div>
    </section>

    <!-- 素材库段 -->
    <section class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">素材库（{{ g.materialItems.value.length }}）</span>
        <SButton v-if="selMaterials.length" size="sm" variant="primary" @click="batchAdd">批量加入图集（{{ selMaterials.length }}）</SButton>
      </div>
      <div v-if="g.materialItems.value.length" class="images-tab__grid">
        <ImageCard v-for="m in g.materialItems.value" :key="m.id"
          :url="m.url" :local-url="g.localUrl(m.url)" :type="m.type" :source="m.source"
          :selected="selMaterials.includes(m.id)" @click="toggleMat(m.id)">
          <template #actions>
            <button class="ic-btn" title="加入图集" @click.stop="addOne(m.id)">加入图集</button>
            <button class="ic-btn ic-btn--danger" title="删除" @click.stop="delImg(m.id)">✕</button>
          </template>
        </ImageCard>
      </div>
      <div v-else class="images-tab__empty">没有未入图集的素材。</div>
    </section>

    <!-- 来自变体借图 -->
    <section v-if="siblings.length" class="images-tab__sec">
      <div class="images-tab__head">
        <span class="images-tab__title">来自变体</span>
        <ElSelect :model-value="borrowId" placeholder="选一个同组变体借图" clearable style="width:200px" @change="onBorrowPick">
          <ElOption v-for="v in siblings" :key="v.id" :label="v.spec || `变体${v.id}`" :value="v.id" />
        </ElSelect>
        <SButton v-if="borrowSel.length" size="sm" variant="primary" @click="doBorrow">借 {{ borrowSel.length }} 张到图集</SButton>
      </div>
      <div v-if="borrowMats.length" class="images-tab__grid">
        <ImageCard v-for="m in borrowMats" :key="m.id"
          :url="m.url" :local-url="m.url" :type="m.type" :source="m.source"
          :selected="borrowSel.includes(m.url)" @click="toggleBorrow(m.url)" />
      </div>
      <div v-else-if="borrowId != null" class="images-tab__empty">该变体没有素材。</div>
    </section>
  </div>
</template>

<style scoped>
.images-tab{padding:var(--sp-3,12px)}
.images-tab__sec{margin-bottom:var(--sp-5,20px)}
.images-tab__head{display:flex;align-items:center;gap:var(--sp-2,8px);margin-bottom:var(--sp-2,8px)}
.images-tab__title{font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555)}
.images-tab__grid{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px)}
.images-tab__empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888)}
.ic-btn{border:none;background:transparent;cursor:pointer;font-size:11px;padding:1px 4px;color:var(--c-text-2,#555)}
.ic-btn:hover{color:var(--c-primary,#7c3aed)}
.ic-btn--danger:hover{color:var(--c-danger,#e5484d)}
.ic-btn:disabled{opacity:.35;cursor:not-allowed}
</style>
