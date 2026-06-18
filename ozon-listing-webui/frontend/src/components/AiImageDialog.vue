<template>
  <el-dialog
    :model-value="modelValue"
    title="AI 生成图片（Agnes）"
    width="640px"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <el-form label-width="90px" label-position="left">
      <el-form-item label="模式">
        <el-radio-group v-model="mode">
          <el-radio value="img2img" :disabled="!images.length">图生图（保产品改场景）</el-radio>
          <el-radio value="text2img">文生图（营销图）</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="mode === 'img2img'" label="源图">
        <div class="src-pick">
          <div
            v-for="(im, i) in images" :key="i"
            class="src-item" :class="{ active: sourceUrl === im.url }"
            @click="sourceUrl = im.url"
          >
            <img :src="im.disp" loading="lazy" />
          </div>
        </div>
        <div class="hint">点选一张作为参考图（保留产品本体，按提示词改背景/场景）。</div>
      </el-form-item>

      <el-form-item label="提示词">
        <el-input v-model="prompt" type="textarea" :rows="4"
                  placeholder="英文/俄语效果更好；图生图要写清「改什么 + 保留什么」" />
        <div class="preset-bar">
          <el-button v-for="p in presets" :key="p.label" size="small" text type="primary"
                     @click="usePreset(p)">{{ p.label }}</el-button>
        </div>
      </el-form-item>

      <el-form-item label="尺寸">
        <el-select v-model="size" style="width:140px">
          <el-option label="1024×768 横" value="1024x768" />
          <el-option label="768×1024 竖" value="768x1024" />
          <el-option label="1024×1024 方" value="1024x1024" />
        </el-select>
        <el-checkbox v-model="asMain" style="margin-left:16px">设为主图（插到首位）</el-checkbox>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="generate">生成</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  draftId: { type: Number, required: true },
  // [{url, disp}]：url 是真相源（http 源图或 /media 本地图），disp 是显示用本地副本
  images: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'done'])

const mode = ref('img2img')
const sourceUrl = ref('')
const prompt = ref('')
const size = ref('1024x768')
const asMain = ref(false)
const loading = ref(false)

// 预设提示词：图生图强调「保留产品本体」（官方最佳实践：写清改什么+保留什么）
const presets = [
  { label: '白底主图', mode: 'img2img', asMain: true,
    text: 'Professional e-commerce product photo on a clean pure white studio background, soft natural shadow, high detail, while preserving the product shape, color, material and all details exactly the same' },
  { label: '生活场景图', mode: 'img2img', asMain: false,
    text: 'Place the same product in a cozy modern home interior scene, natural daylight, lifestyle photography, while preserving the product appearance exactly the same' },
  { label: '营销海报(文生图)', mode: 'text2img', asMain: false,
    text: 'Eye-catching e-commerce marketing banner for this product, clean composition, bright studio lighting, high visual density, no text' },
]

function usePreset(p) {
  mode.value = p.mode
  prompt.value = p.text
  asMain.value = p.asMain
}

// 打开时初始化：有图默认图生图选第一张，无图退文生图
watch(() => props.modelValue, (open) => {
  if (!open) return
  if (props.images.length) {
    mode.value = 'img2img'
    sourceUrl.value = props.images[0].url
  } else {
    mode.value = 'text2img'
    sourceUrl.value = ''
  }
}, { immediate: true })

async function generate() {
  const p = String(prompt.value || '').trim()
  if (!p) { ElMessage.warning('请填写提示词（可点预设）'); return }
  if (mode.value === 'img2img' && !sourceUrl.value) { ElMessage.warning('请选择一张源图'); return }
  loading.value = true
  try {
    const r = await api.aiImage(props.draftId, {
      mode: mode.value, prompt: p, size: size.value, as_main: asMain.value,
      source_url: mode.value === 'img2img' ? sourceUrl.value : undefined,
    })
    if (!r || !r.ok) { ElMessage.error((r && r.error) || '生成失败'); return }
    ElMessage.success('图片已生成并加入图集')
    emit('done', r.draft)
    emit('update:modelValue', false)
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally {
    loading.value = false
  }
}

defineExpose({ mode, sourceUrl, prompt, size, asMain, loading, generate, usePreset, presets })
</script>

<style scoped>
.src-pick { display: flex; flex-wrap: wrap; gap: 6px; }
.src-item { width: 64px; height: 64px; border: 2px solid transparent; border-radius: 4px;
  overflow: hidden; cursor: pointer; }
.src-item.active { border-color: var(--c-brand); }
.src-item img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hint { font-size: 12px; color: var(--c-text-3); margin-top: 4px; width: 100%; }
.preset-bar { margin-top: 4px; }
</style>
