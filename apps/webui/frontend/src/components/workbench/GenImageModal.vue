<script setup>
import { computed, ref, toRef, watch } from 'vue'
import { ElDialog, ElMessage } from 'element-plus'
import { api } from '../../api.js'
import { useWorkbenchStore } from '../../stores/workbench.js'
import { useGallery } from '../../composables/useGallery.js'
import { variantColor } from '../../stores/workbench.js'
import ImageCard from './ImageCard.vue'
import { SButton } from '../../ui/index.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  draft: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'generated', 'zoom'])

const draftRef = toRef(props, 'draft')
const wb = useWorkbenchStore()
const g = useGallery(draftRef)

const open = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const mode = ref('img2img')
const currentId = computed(() => props.draft.id)
const currentMaterials = computed(() => g.materialItems.value.concat(g.galleryItems.value))
const variantChips = computed(() =>
  wb.variants.map((v) => ({ id: v.id, label: v.spec || `变体${v.id}`, hex: variantColor(v) })),
)

const sourceVariantId = ref(null)
const refVariantId = ref(null)
const borrowedSourceMaterials = ref([])
const borrowedRefMaterials = ref([])
const selSources = ref([])
const refUrls = ref([])

const sourceMaterials = computed(() => {
  if (sourceVariantId.value == null || sourceVariantId.value === currentId.value) return currentMaterials.value
  return borrowedSourceMaterials.value
})
const referenceMaterials = computed(() => {
  if (refVariantId.value == null || refVariantId.value === currentId.value) return currentMaterials.value
  return borrowedRefMaterials.value
})

async function loadVariantMaterials(id) {
  if (id == null || id === currentId.value) return []
  const r = await g.fetchSiblingMaterials(id)
  return Array.isArray(r) ? r : []
}

async function pickSourceVariant(id) {
  sourceVariantId.value = id
  selSources.value = []
  if (id == null || id === currentId.value) {
    borrowedSourceMaterials.value = []
    return
  }
  try {
    borrowedSourceMaterials.value = await loadVariantMaterials(id)
  } catch (e) {
    borrowedSourceMaterials.value = []
    ElMessage.warning(`取源图变体失败：${e && e.message ? e.message : e}`)
  }
}

async function pickRefVariant(id) {
  refVariantId.value = id
  refUrls.value = []
  if (id == null || id === currentId.value) {
    borrowedRefMaterials.value = []
    return
  }
  try {
    borrowedRefMaterials.value = await loadVariantMaterials(id)
  } catch (e) {
    borrowedRefMaterials.value = []
    ElMessage.warning(`取参考图变体失败：${e && e.message ? e.message : e}`)
  }
}

function toggleList(listRef, url) {
  const i = listRef.value.indexOf(url)
  if (i >= 0) listRef.value.splice(i, 1)
  else listRef.value.push(url)
}
function toggleSource(url) { toggleList(selSources, url) }
function toggleRef(url) { toggleList(refUrls, url) }
function orderOf(list, url) {
  const i = list.indexOf(url)
  return i >= 0 ? String(i + 1) : ''
}

const QUICK_OPS = {
  img2img: [
    { key: 'whiten', label: '白底图' },
    { key: 'detail', label: '细节图' },
    { key: 'dimension', label: '尺寸图' },
    { key: 'localize', label: '俄化' },
    { key: 'scene', label: '场景图' },
    { key: 'regen', label: '重做' },
  ],
  text2img: [
    { key: 'poster', label: '营销海报' },
  ],
}
const quickOps = computed(() => QUICK_OPS[mode.value] || [])
const quickOp = ref('')
function pickQuick(key) {
  quickOp.value = quickOp.value === key ? '' : key
}

const prompt = ref('')
const promptLoading = ref(false)
const SIZES = ['900x1200', '1200x1600', '1500x2000']
const size = ref('1200x1600')
const asMain = ref(false)
const generating = ref(false)
const unsupportedNote = ref('')

const DETAIL_PROMPT = 'Generate a tight close-up detail shot emphasizing material, texture and craftsmanship of the same product. Keep the product identical, clean background, no added text, no logo, no watermark.'
const DIMENSION_PROMPT_PREFIX = 'Create a clean Ozon product size infographic from this product photo. Add precise measurement arrows and a simple dimension callout panel. Use ONLY these verified dimensions, do not invent or change numbers: '
const POSTER_PROMPT = 'Design an eye-catching Ozon marketing poster for this product: bold composition, vibrant but tasteful colors, leave clear space, no real text guaranteed (avoid garbled letters), 3:4 vertical.'
const REF_PROMPT = 'Input image 1 is the source image to edit. The following input image(s) are reference only: match their product color/style/material cues where relevant, but keep the source image composition and product identity. Do not copy unrelated backgrounds, text, logos, watermarks, or extra objects from the reference images.'

const promptText = computed(() => prompt.value.trim())
const hasGenerationIntent = computed(() => Boolean(quickOp.value || promptText.value))
const canGenerate = computed(() => {
  if (generating.value) return false
  if (mode.value === 'text2img') return hasGenerationIntent.value
  return selSources.value.length > 0 && hasGenerationIntent.value
})

function dimensionText() {
  const d = props.draft || {}
  const parts = []
  const sr = d.source_raw && typeof d.source_raw === 'object' ? d.source_raw : {}
  const und = sr.understanding && typeof sr.understanding === 'object' ? sr.understanding : {}
  const specs = und.specs && typeof und.specs === 'object' ? und.specs : {}
  for (const [k, v] of Object.entries(specs)) {
    const key = String(k || '')
    const val = String(v || '').trim()
    if (!val || !/\d/.test(val)) continue
    if (/尺寸|规格|大小|长宽高|外形|dimension|size/i.test(key)) parts.push(`${key}: ${val}`)
  }
  const L = Number(d.length_mm || 0)
  const W = Number(d.width_mm || 0)
  const H = Number(d.height_mm || 0)
  if (!parts.length && L > 0 && W > 0 && H > 0) parts.push(`dimensions: ${L} x ${W} x ${H} mm`)
  return Array.from(new Set(parts)).join('; ')
}

function withReferencePrompt(text) {
  return refUrls.value.length ? `${text}\n\n${REF_PROMPT}` : text
}

async function genPrompt() {
  const id = props.draft.id
  if (id == null) return
  promptLoading.value = true
  try {
    const r = await api.aiImagePrompts(id, 3)
    const main = r && (r.main && (r.main.prompt || r.main.text || r.main))
    const sp = r && Array.isArray(r.selling_points) && r.selling_points[0]
    const txt = main || (sp && (sp.prompt || sp.text || sp)) || ''
    prompt.value = typeof txt === 'string' ? txt : JSON.stringify(txt)
    if (!prompt.value) ElMessage.info('没有生成到提示词')
  } catch (e) {
    ElMessage.warning(`生成提示词失败：${e && e.message ? e.message : e}`)
  } finally {
    promptLoading.value = false
  }
}

async function generate() {
  const id = props.draft.id
  if (id == null) return
  if (mode.value === 'img2img' && !selSources.value.length) {
    ElMessage.info('请先选择至少一张源图')
    return
  }
  if (!hasGenerationIntent.value) {
    ElMessage.info('请选择快捷操作，或输入提示词')
    return
  }
  generating.value = true
  unsupportedNote.value = ''
  open.value = false
  ElMessage.info('已提交生成，可继续操作其它变体')
  try {
    const res = mode.value === 'img2img' ? await runImg2Img(id) : await runText2Img(id)
    if (res === 'aborted') return
    const count = Number(res && res.count) || 1
    ElMessage.success(count > 1 ? `已生成 ${count} 张并加入图集` : '已生成并加入图集')
    emit('generated')
  } catch (e) {
    ElMessage.warning(`生成失败：${e && e.message ? e.message : e}`)
  } finally {
    generating.value = false
  }
}

async function runImg2Img(id) {
  if (quickOp.value === 'dimension' && !dimensionText()) {
    ElMessage.info('图文理解里没有识别到尺寸，先不做尺寸图')
    return 'aborted'
  }
  const op = quickOp.value
  let p = promptText.value
  if (!p) {
    if (op === 'whiten') p = '电商白底主图，纯白背景，产品比例与细节不变，无文字无水印。'
    else if (op === 'localize') p = [
      'Localize this image for Ozon Russia.',
      'Keep the product, composition, background, colors, graphics and icons visually unchanged.',
      'Translate ONLY text that directly describes the product itself into natural Russian.',
      'Product-related text includes product name, model, chipset, speed, interface, dimensions, material, package contents, usage, compatibility, and real product features/specifications.',
      'Do NOT translate supplier/manufacturer/service/compliance/shipping banner text. Remove it cleanly instead.',
      'Forbidden non-product content includes factory audit/support, years of production/R&D, cross-border/export supply, complete certifications, CE/FCC/RoHS claims, free labeling, OEM/ODM/customization, large stock, same-day/fast/lightning shipping, direct manufacturer, price, QR codes, phone, links, shop names, watermarks, promotions, gifts, invoices, warranty/service promises.',
      'Final image must contain zero Chinese characters and no unrelated seller or factory claims.',
    ].join(' ')
    else if (op === 'scene') p = '把产品放进自然真实的使用场景，柔和真实光线，产品外观保持一致。'
    else if (op === 'detail') p = DETAIL_PROMPT
    else if (op === 'dimension') p = DIMENSION_PROMPT_PREFIX + dimensionText() + '. Keep the product appearance identical, use a white or light neutral background, no extra marketing text, no watermark.'
    else if (op === 'regen') p = '按 Ozon 商品图规范重做这张图，产品外观保持一致，构图清晰，背景干净，无乱码文字。'
  }
  p = withReferencePrompt(p)

  let last = null
  let count = 0
  for (let i = 0; i < selSources.value.length; i += 1) {
    last = await api.aiImage(id, {
      mode: 'img2img',
      prompt: p,
      source_url: selSources.value[i],
      reference_urls: refUrls.value,
      size: size.value,
      as_main: asMain.value && i === 0,
    })
    count += 1
  }
  return { last, count }
}

async function runText2Img(id) {
  let p = promptText.value
  if (!p) p = quickOp.value === 'poster' ? POSTER_PROMPT : ''
  const last = await api.aiImage(id, {
    mode: 'text2img',
    prompt: p,
    size: size.value,
    as_main: asMain.value,
  })
  return { last, count: 1 }
}

watch(open, (v) => {
  if (v) {
    sourceVariantId.value = currentId.value
    refVariantId.value = currentId.value
    borrowedSourceMaterials.value = []
    borrowedRefMaterials.value = []
    selSources.value = []
    refUrls.value = []
    quickOp.value = ''
    prompt.value = ''
    unsupportedNote.value = ''
  }
})

function onZoom(url) {
  emit('zoom', url)
}
</script>

<template>
  <ElDialog v-model="open" title="AI 生成图片" width="720px" append-to-body class="gen-modal">
    <div class="gm-modes">
      <button class="gm-tab" :class="{ 'is-on': mode === 'img2img' }" @click="mode = 'img2img'">图生图</button>
      <button class="gm-tab" :class="{ 'is-on': mode === 'text2img' }" @click="mode = 'text2img'">文生图</button>
    </div>

    <section v-if="mode === 'img2img'" class="gm-sec">
      <div class="gm-row gm-row--between">
        <span class="gm-hint">源图 · 要被处理的图片，可多选逐张生成</span>
        <div class="gm-chips">
          <span class="gm-hint gm-hint--mini">取自变体</span>
          <button
            v-for="c in variantChips"
            :key="c.id"
            class="gm-chip"
            :class="{ 'is-on': (sourceVariantId == null ? currentId : sourceVariantId) === c.id }"
            @click="pickSourceVariant(c.id)"
          >
            <span class="gm-dot" :style="{ background: c.hex }"></span>{{ c.label }}
          </button>
        </div>
      </div>
      <div v-if="sourceMaterials.length" class="gm-grid">
        <div v-for="m in sourceMaterials" :key="m.id || m.url" class="gm-pick-card">
          <ImageCard
            :url="m.url"
            :local-url="m.local_url || ''"
            :type="m.type"
            :source="m.source"
            selectable
            :show-select-control="false"
            :selected="selSources.includes(m.url)"
            :badge="orderOf(selSources, m.url)"
            @zoom="onZoom"
          />
          <button
            class="gm-select"
            :class="{ 'is-on': selSources.includes(m.url) }"
            :title="selSources.includes(m.url) ? '取消选择' : '选择这张源图'"
            :aria-label="selSources.includes(m.url) ? '取消选择' : '选择这张源图'"
            @click.stop="toggleSource(m.url)"
          >
            <span v-if="selSources.includes(m.url)">{{ orderOf(selSources, m.url) }}</span>
          </button>
        </div>
      </div>
      <div v-else class="gm-empty">该变体暂无可用图片。</div>
    </section>

    <section v-if="mode === 'img2img'" class="gm-sec">
      <div class="gm-row gm-row--between">
        <span class="gm-hint">参考图 · 可选，用来提供目标颜色 / 款式 / 材质</span>
        <div class="gm-chips">
          <span class="gm-hint gm-hint--mini">取自变体</span>
          <button
            v-for="c in variantChips"
            :key="c.id"
            class="gm-chip"
            :class="{ 'is-on': (refVariantId == null ? currentId : refVariantId) === c.id }"
            @click="pickRefVariant(c.id)"
          >
            <span class="gm-dot" :style="{ background: c.hex }"></span>{{ c.label }}
          </button>
        </div>
      </div>
      <div v-if="referenceMaterials.length" class="gm-grid">
        <div v-for="r in referenceMaterials" :key="`ref-${r.id || r.url}`" class="gm-pick-card">
          <ImageCard
            :url="r.url"
            :local-url="r.local_url || ''"
            :type="r.type"
            :source="r.source"
            selectable
            :show-select-control="false"
            :selected="refUrls.includes(r.url)"
            :badge="orderOf(refUrls, r.url)"
            @zoom="onZoom"
          />
          <button
            class="gm-select"
            :class="{ 'is-on': refUrls.includes(r.url) }"
            :title="refUrls.includes(r.url) ? '取消参考' : '选择为参考图'"
            :aria-label="refUrls.includes(r.url) ? '取消参考' : '选择为参考图'"
            @click.stop="toggleRef(r.url)"
          >
            <span v-if="refUrls.includes(r.url)">{{ orderOf(refUrls, r.url) }}</span>
          </button>
        </div>
      </div>
      <div v-else class="gm-empty">该变体暂无可用参考图。</div>
      <div class="gm-tipbox">
        生成结果直接加入当前图集。选了参考图时，模型会把第一张输入当源图，后面的输入只当颜色/款式参考。
      </div>
    </section>

    <section class="gm-sec">
      <div class="gm-hint">快捷操作 · 选一个可直接生成，或只填写提示词自定义生成</div>
      <div class="gm-ops">
        <button
          v-for="q in quickOps"
          :key="q.key"
          class="gm-op"
          :class="{ 'is-on': quickOp === q.key }"
          @click="pickQuick(q.key)"
        >
          {{ q.label }}
        </button>
      </div>
    </section>

    <section class="gm-sec">
      <div class="gm-row gm-row--between">
        <span class="gm-hint">提示词 · 选择快捷操作时可留空</span>
        <SButton size="sm" variant="ghost" :loading="promptLoading" @click="genPrompt">AI 生成提示词</SButton>
      </div>
      <textarea
        v-model="prompt"
        class="gm-ta"
        placeholder="也可以自定义提示词；如果不选快捷操作，这里必须填写。"
      ></textarea>
    </section>

    <section class="gm-sec gm-foot">
      <span class="gm-hint">尺寸 3:4</span>
      <button
        v-for="z in SIZES"
        :key="z"
        class="gm-size"
        :class="{ 'is-on': size === z }"
        @click="size = z"
      >
        {{ z.replace('x', '×') }}
      </button>
      <label class="gm-main"><input v-model="asMain" type="checkbox" />设为主图</label>
      <SButton
        variant="primary"
        :loading="generating"
        :disabled="!canGenerate"
        class="gm-gen"
        @click="generate"
      >
        生成
      </SButton>
    </section>

    <div v-if="unsupportedNote" class="gm-note">{{ unsupportedNote }}</div>
  </ElDialog>
</template>

<style scoped>
.gm-modes{display:flex;gap:var(--sp-2,8px);margin-bottom:var(--sp-3,12px)}
.gm-tab{flex:1;font-size:var(--fs-sm,13px);font-weight:600;color:var(--c-text-2,#555);
  background:var(--c-bg,#f7f9fc);border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);
  padding:var(--sp-2,8px) 0;cursor:pointer}
.gm-tab.is-on{color:#fff;background:var(--c-primary,#7c3aed);border-color:var(--c-primary,#7c3aed)}
.gm-sec{margin-bottom:var(--sp-4,16px)}
.gm-row{display:flex;align-items:center;gap:var(--sp-2,8px)}
.gm-row--between{justify-content:space-between;flex-wrap:wrap}
.gm-hint{font-size:var(--fs-xs,12px);color:var(--c-text-3,#888)}
.gm-hint--mini{color:var(--c-text-3,#aaa)}
.gm-chips{display:flex;align-items:center;gap:var(--sp-1,4px);flex-wrap:wrap}
.gm-chip{display:inline-flex;align-items:center;gap:4px;font-size:var(--fs-xs,12px);color:var(--c-text-2,#555);
  background:#fff;border:1px solid var(--c-border,#e5e7eb);border-radius:999px;padding:2px 9px;cursor:pointer}
.gm-chip.is-on{color:var(--c-primary,#7c3aed);border-color:var(--c-primary,#7c3aed);background:var(--c-primary-50,#faf7ff)}
.gm-dot{width:10px;height:10px;border-radius:3px;display:inline-block}
.gm-grid{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);margin-top:var(--sp-2,8px)}
.gm-pick-card{position:relative;width:88px;height:88px}
.gm-select{
  position:absolute;left:5px;top:5px;z-index:3;width:22px;height:22px;
  border:1px solid rgba(255,255,255,.92);border-radius:6px;cursor:pointer;
  background:rgba(15,23,42,.46);color:#fff;font-size:12px;font-weight:800;
  display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(15,23,42,.22)
}
.gm-select:hover{background:rgba(124,58,237,.9)}
.gm-select.is-on{background:var(--c-primary,#7c3aed);border-color:#fff}
.gm-pick-card :deep(.img-card__type){top:30px}
.gm-empty{font-size:var(--fs-sm,13px);color:var(--c-text-3,#888);margin-top:var(--sp-2,8px)}
.gm-tipbox{font-size:var(--fs-xs,12px);color:var(--c-primary,#7c3aed);background:var(--c-primary-50,#f5f3ff);
  border-radius:var(--r-sm,7px);padding:7px 10px;margin-top:var(--sp-3,12px);line-height:1.55}
.gm-ops{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);margin-top:var(--sp-2,8px)}
.gm-op{font-size:var(--fs-sm,13px);color:var(--c-text-2,#555);background:#fff;
  border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);padding:6px 13px;cursor:pointer}
.gm-op.is-on{color:#fff;background:var(--c-primary,#7c3aed);border-color:var(--c-primary,#7c3aed)}
.gm-ta{width:100%;min-height:60px;font-size:var(--fs-sm,13px);color:var(--c-text,#1f2733);line-height:1.6;
  background:#fff;border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,8px);padding:9px 11px;
  outline:none;resize:vertical;font-family:inherit;margin-top:var(--sp-2,8px);box-sizing:border-box}
.gm-foot{display:flex;align-items:center;gap:var(--sp-2,8px);flex-wrap:wrap}
.gm-size{font-size:var(--fs-xs,12px);color:var(--c-text-2,#555);background:#fff;
  border:1px solid var(--c-border,#e5e7eb);border-radius:var(--r-sm,7px);padding:5px 11px;cursor:pointer}
.gm-size.is-on{color:#fff;background:var(--c-primary,#7c3aed);border-color:var(--c-primary,#7c3aed)}
.gm-main{display:flex;align-items:center;gap:5px;font-size:var(--fs-sm,12px);color:var(--c-text-2,#555);cursor:pointer}
.gm-gen{margin-left:auto}
.gm-note{font-size:var(--fs-xs,12px);color:var(--c-warn,#b45309);background:var(--c-warn-bg,#fffbeb);
  border-radius:var(--r-sm,7px);padding:7px 10px;margin-top:var(--sp-2,8px);line-height:1.5}
</style>
