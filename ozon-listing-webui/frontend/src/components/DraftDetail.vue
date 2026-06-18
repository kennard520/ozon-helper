<template>
  <div class="draft-detail">
    <div class="detail-hero compact">
      <div class="detail-meta-line">
        <strong>商品详情</strong>
        <span>来源：{{ draft.source_platform || '未知' }}</span>
      </div>
      <div class="hero-actions">
        <el-button
          v-if="variantGroup"
          type="warning"
          :loading="publishingGroup"
          @click="onPublishGroup"
        >整组发布{{ variantList.length ? `（${variantList.length} 变体）` : '' }}</el-button>
        <el-button :loading="aiGenerating" @click="doAiGenerate">AI 生成卡片</el-button>
        <el-dropdown v-if="copyTargets.length" trigger="click" @command="copyToStore">
          <el-button>复制到其他店</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="s in copyTargets" :key="s.client_id" :command="String(s.client_id)">
                {{ s.name }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" @click="save">保存</el-button>
      </div>
    </div>

    <section class="source-summary">
      <div>
        <div class="source-summary-title">来源商品</div>
        <div class="source-summary-name" :title="draft.source_title">{{ draft.source_title || '-' }}</div>
      </div>
      <div class="source-summary-meta">
        <span>{{ draft.source_platform || '-' }}</span>
        <span>{{ draft.offer_id || draft.source_offer_id || '-' }}</span>
        <a v-if="draft.source_url" :href="draft.source_url" target="_blank" rel="noreferrer">打开来源链接</a>
      </div>
    </section>

    <el-tabs v-model="activeDetailTab" class="detail-tabs">
      <el-tab-pane label="商品信息" name="info" />
      <el-tab-pane label="特征" name="attrs" />
      <el-tab-pane label="媒体" name="media" />
      <el-tab-pane label="采购信息" name="purchase" />
    </el-tabs>
    <AiImageDialog v-model="aiImgDlg" :draft-id="draft.id" :images="aiDialogImages" @done="onAiImageDone" />
    <AiVideoDialog v-model="aiVidDlg" :draft-id="draft.id" :images="aiDialogImages" @done="onAiVideoDone" />

    <div class="detail-shell">
      <main class="detail-main">
        <!-- AI 待确认草案（内联，逐项可改/删，点应用才写入商品）-->
        <section v-if="proposalActive" class="detail-section ai-result-section">
          <div class="ai-result-header">
            <span class="ai-result-title">AI 待确认草案 <small class="ai-result-hint">逐项可改/删，点【应用】才写入商品</small></span>
          </div>

          <template v-for="(label, key) in proposalFieldLabels" :key="key">
            <div v-if="proposal.fields && key in proposal.fields" class="ai-row">
              <span class="ai-row-label">{{ label }}</span>
              <el-input :model-value="proposal.fields[key]" size="small" style="max-width:320px"
                        @change="(v) => editProposalField(key, v)" />
              <el-button link type="danger" size="small" @click="deleteProposalField(key)">删除</el-button>
            </div>
          </template>

          <div class="ai-row ai-row-block">
            <div class="ai-row-head"><span class="ai-row-label">特征（AI 已填）</span></div>
            <div v-if="!proposalAiAttrs.length" class="ai-preview-empty">（无）</div>
            <div v-for="a in proposalAiAttrs" :key="a.id" class="req-attr-item">
              <div class="ra-head">{{ a.name }}
                <el-button link type="danger" size="small" @click="deleteProposalAttr(a.id)">删除</el-button>
              </div>
              <el-input :model-value="a.value" size="small" @change="(v) => editProposalAttr(a.id, v)" />
            </div>
          </div>

          <div v-if="proposalMissingAttrs.length" class="ai-row ai-row-block">
            <div class="ai-row-head"><span class="ai-row-label">特征（待补充）</span></div>
            <div v-for="a in proposalMissingAttrs" :key="a.id" class="req-attr-item" :class="{ missing: a.required }">
              <div class="ra-head"><span v-if="a.required" class="req">*</span>{{ a.name }}</div>
              <el-input :model-value="a.value" size="small" placeholder="填值（可留空）"
                        @change="(v) => editProposalAttr(a.id, v)" />
            </div>
          </div>

          <div v-if="(proposal.keywords || []).length" class="ai-row">
            <span class="ai-row-label">关键词</span>
            <el-tag v-for="(kw, i) in proposal.keywords" :key="i" size="small" class="ai-kw-tag">{{ kw }}</el-tag>
          </div>

          <div class="proposal-actions">
            <el-button type="primary" @click="applyProposal">应用到商品</el-button>
            <el-button @click="discardProposal">放弃草案</el-button>
          </div>
        </section>

        <!-- 商品信息 -->
        <section v-show="activeDetailTab === 'info'" id="product-info" class="detail-section ozon-section">
          <div class="section-head">
            <span class="section-index">1</span>
            <div>
              <h3>商品信息</h3>
              <p>先确定 Ozon 卡片的名称、类目、价格和履约基础字段。</p>
            </div>
          </div>
          <el-form label-width="128px" label-position="left" class="ozon-form">
            <div class="field-grid">
              <el-form-item label="Ozon 标题 (RU)" class="field-wide">
                <div class="inline-action-field">
                  <el-input v-model="form.ozon_title" placeholder="默认=来源标题，可改成你要上架的俄语标题" />
                  <el-button
                    v-if="draft.source_platform === '1688'"
                    link
                    type="primary"
                    @click="doTranslate"
                  >翻译成俄语</el-button>
                </div>
              </el-form-item>
              <el-form-item label="类目" class="field-wide">
                <CategorySelect v-model="categoryModel" />
              </el-form-item>
              <el-form-item label="品牌">
                <el-input :model-value="NO_BRAND_NAME" disabled />
              </el-form-item>
              <el-form-item label="库存">
                <el-input v-model="form.stock" type="number" :min="0" />
              </el-form-item>
              <el-form-item label="售价(¥)">
                <div class="inline-action-field">
                  <el-input v-model="form.price" />
                  <el-button @click="emit('open-pricing')">智能定价</el-button>
                </div>
              </el-form-item>
              <el-form-item label="划线价(¥)">
                <el-input v-model="form.old_price" placeholder="留空=售价" />
              </el-form-item>
              <el-form-item label="克重(g)">
                <el-input v-model="form.weight_g" type="number" :min="0" placeholder="含包装重量" />
              </el-form-item>
              <el-form-item label="尺寸 长×宽×高(cm)" class="field-wide">
                <div class="dims-row">
                  <el-input v-model="form.length_mm" type="number" :min="0" placeholder="长" />
                  <span>×</span>
                  <el-input v-model="form.width_mm" type="number" :min="0" placeholder="宽" />
                  <span>×</span>
                  <el-input v-model="form.height_mm" type="number" :min="0" placeholder="高" />
                </div>
              </el-form-item>
            </div>
          </el-form>
        </section>

        <!-- 类目必填属性 -->
        <section v-show="activeDetailTab === 'attrs'" id="product-attrs" class="detail-section ozon-section">
          <div class="section-row section-head-row">
            <div class="section-head">
              <span class="section-index">3</span>
              <div>
                <h3>特征</h3>
                <p>按 Ozon 类目要求补齐必填属性，可选项默认收起。</p>
              </div>
            </div>
            <span>
              <el-button link type="primary" @click="autoMap">自动填充</el-button>
              <el-button link type="primary" @click="runRequiredCheck">重新检查</el-button>
            </span>
          </div>
          <div v-if="attrWarning" class="attr-warning">▲ {{ attrWarning }}</div>
          <template v-else>
            <div class="attr-group-label" v-if="required.length">必填（{{ required.length }}）</div>
            <div class="req-attr-list">
              <div
                v-for="a in required"
                :key="a.id"
                class="req-attr-item"
                :class="{ missing: missingIds.has(a.id) }"
              >
                <div class="ra-head">
                  <span class="attr-state-dot" :class="{ ok: !missingIds.has(a.id) }"></span>
                  <span class="req">*</span>{{ a.name || ('属性' + a.id) }}
                </div>
                <div class="ra-control">
                  <span v-if="Number(a.id) === 85" class="muted">用上方「品牌」下拉填</span>
                  <el-select
                    v-else-if="Number(a.dictionary_id) > 0"
                    v-model="attrInputs[a.id]"
                    filterable
                    remote
                    clearable
                    :remote-method="(q) => searchAttr(a, q)"
                    :loading="!!attrLoading[a.id]"
                    placeholder="输入俄文搜索取值"
                    @change="(id) => onAttrPick(a, id)"
                  >
                    <el-option
                      v-for="opt in (attrOptions[a.id] || [])"
                      :key="opt.id"
                      :label="opt.value"
                      :value="opt.id"
                    />
                  </el-select>
                  <el-input
                    v-else
                    v-model="attrInputs[a.id]"
                    placeholder="输入文本值（如型号名）"
                    @change="(v) => onAttrText(a, v)"
                  />
                </div>
              </div>
            </div>

            <!-- 简介/标签：与特征同样式，紧跟必填 -->
            <div class="req-attr-list">
              <div class="req-attr-item" :class="{ 'opt-filled': !!form.description }">
                <div class="ra-head">
                  <span class="attr-state-dot" :class="{ ok: !!form.description, neutral: !form.description }"></span>
                  简介
                </div>
                <div class="ra-control">
                  <el-input v-model="form.description" type="textarea" :rows="5" spellcheck="false" placeholder="商品描述、营销文本" />
                </div>
              </div>
              <div class="req-attr-item" :class="{ 'opt-filled': !!form.tags }">
                <div class="ra-head">
                  <span class="attr-state-dot" :class="{ ok: !!form.tags, neutral: !form.tags }"></span>
                  主题标签
                </div>
                <div class="ra-control">
                  <el-input v-model="form.tags" placeholder="多个标签用逗号或换行分隔" />
                </div>
              </div>
            </div>

            <div v-if="optional.length" class="attr-group-label">可选（{{ optionalFilledCount }}/{{ optional.length }} 已填）</div>
            <div v-if="optional.length" class="req-attr-list optional-list">
              <div
                v-for="a in optional"
                :key="a.id"
                class="req-attr-item"
                :class="{ 'opt-filled': !!attrInputs[a.id] }"
              >
                <div class="ra-head">
                  <span class="attr-state-dot" :class="{ ok: !!attrInputs[a.id], neutral: !attrInputs[a.id] }"></span>
                  {{ a.name || ('属性' + a.id) }}
                </div>
                <div class="ra-control">
                  <el-select
                    v-if="Number(a.dictionary_id) > 0"
                    v-model="attrInputs[a.id]"
                    filterable
                    remote
                    clearable
                    :remote-method="(q) => searchAttr(a, q)"
                    :loading="!!attrLoading[a.id]"
                    placeholder="输入俄文搜索取值（可留空）"
                    @change="(id) => onAttrPick(a, id)"
                  >
                    <el-option
                      v-for="opt in (attrOptions[a.id] || [])"
                      :key="opt.id"
                      :label="opt.value"
                      :value="opt.id"
                    />
                  </el-select>
                  <el-input
                    v-else
                    v-model="attrInputs[a.id]"
                    placeholder="输入文本值（可留空）"
                    @change="(v) => onAttrText(a, v)"
                  />
                </div>
              </div>
            </div>
          </template>

          <div v-if="attributesParseError" class="attr-warning">▲ 属性 JSON 解析失败，保存时将沿用原属性</div>
        </section>

        <!-- 媒体 -->
        <section v-show="activeDetailTab === 'media'" id="product-media" class="detail-section ozon-section">
          <div class="section-head">
            <span class="section-index">4</span>
            <div>
              <h3>媒体</h3>
              <p>先整理主图、详情图和视频，再生成卖点图提示词。</p>
            </div>
          </div>
          <div class="media-inline">
            <MediaManager
              :images="drawerImages"
              :video-url="draft.video_url || ''"
              :draft-id="draft.id"
              :local-map="localMap"
              @update:images="onImagesChange"
              @update:videoUrl="onVideoChange"
            >
              <template #image-actions>
                <el-button size="small" @click="openAiImage">AI 生成图片</el-button>
              </template>
              <template #video-actions>
                <el-button size="small" @click="openAiVideo">AI 生成视频</el-button>
              </template>
              <template #image-extra>
                <div class="prompt-card">
                  <div class="section-row">
                    <h4>ChatGPT 图片提示词</h4>
                    <span class="img-gen-bar">
                      卖点图
                      <el-input-number v-model="imgGenN" :min="1" :max="6" :controls="false" style="width:64px" size="small" />
                      张
                      <el-button type="primary" size="small" :loading="imgGenLoading" @click="doImagePrompts">生成提示词</el-button>
                    </span>
                  </div>
                  <div class="img-hint">基于标题/类目/参数/描述定制；图上文字要求俄语。生成后复制提示词 + 上传原图到 ChatGPT Pro 出图。</div>

                  <template v-if="imgPrompts">
                    <div class="img-prompt-block">
                      <div class="ipb-head"><b>主图提示词</b><el-button link type="primary" size="small" @click="copyText(imgPrompts.main)">复制</el-button></div>
                      <div class="ipb-text">{{ imgPrompts.main || '—' }}</div>
                    </div>
                    <div v-for="(p, i) in imgPrompts.selling_points" :key="i" class="img-prompt-block">
                      <div class="ipb-head"><b>卖点图 {{ i + 1 }}</b><el-button link type="primary" size="small" @click="copyText(p)">复制</el-button></div>
                      <div class="ipb-text">{{ p || '—' }}</div>
                    </div>
                    <div class="proposal-actions">
                      <el-button size="small" @click="copyText(allImgPromptsText)">复制全部</el-button>
                    </div>

                    <div v-if="(imgPrompts.source_images || []).length" class="img-prompt-block">
                      <div class="ipb-head"><b>参考原图（{{ imgPrompts.source_images.length }}）</b></div>
                      <div class="ai-thumb-row">
                        <el-image
                          v-for="(src, i) in imgPrompts.source_images.map(u => localMap[u] || u)"
                          :key="i" :src="src" :preview-src-list="imgPrompts.source_images.map(u => localMap[u] || u)"
                          :initial-index="i" fit="cover" class="ai-thumb" />
                      </div>
                    </div>

                    <div v-if="(imgPrompts.detail_images || []).length" class="img-prompt-block">
                      <div class="ipb-head"><b>详情图（{{ imgPrompts.detail_images.length }}）</b></div>
                      <div class="ai-thumb-row">
                        <el-image
                          v-for="(src, i) in detailThumbs"
                          :key="i" :src="src" :preview-src-list="detailThumbs"
                          :initial-index="i" fit="cover" class="ai-thumb" loading="lazy" />
                      </div>
                    </div>
                  </template>
                </div>
              </template>
            </MediaManager>
          </div>

          <section v-if="richContentJson" class="rich-section">
            <div class="rich-section-title">富文本预览</div>
            <RichContentPreview :rich-json="richContentJson" />
          </section>
        </section>

        <!-- 采购信息 -->
        <section v-show="activeDetailTab === 'purchase'" id="product-purchase" class="detail-section ozon-section">
          <div class="section-head">
            <span class="section-index">4</span>
            <div>
              <h3>采购信息</h3>
              <p>给内部采购和履约使用，不会作为 Ozon 商品卡片内容发布。</p>
            </div>
          </div>
          <el-form label-width="128px" label-position="left" class="ozon-form">
            <div class="field-grid">
              <el-form-item label="采购链接" class="field-wide">
                <el-input v-model="form.purchase_url" placeholder="客户下单后，从这个链接采购发货" />
              </el-form-item>
              <el-form-item label="供应商">
                <el-input v-model="form.supplier" placeholder="供应商名称、店铺名或联系人" />
              </el-form-item>
              <el-form-item label="成本价(¥)">
                <el-input v-model="form.cost_cny" placeholder="1688 进价或预估采购成本" />
              </el-form-item>
              <el-form-item label="采购备注" class="field-wide">
                <el-input
                  v-model="form.purchase_note"
                  type="textarea"
                  :rows="4"
                  placeholder="例如：客户下单后拍白色大号；非 1688 链接就在这里写供应商、微信、规格、注意事项"
                />
              </el-form-item>
            </div>
          </el-form>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api.js'
import { useAppStore } from '../stores/app.js'
import CategorySelect from './CategorySelect.vue'
import MediaManager from './MediaManager.vue'
import AiImageDialog from './AiImageDialog.vue'
import AiVideoDialog from './AiVideoDialog.vue'
import RichContentPreview from './RichContentPreview.vue'
import VariantList from './VariantList.vue'

const props = defineProps({
  draft: { type: Object, required: true },
})
const emit = defineEmits(['open-pricing'])

const store = useAppStore()

const NO_BRAND_NAME = 'Нет бренда'
const HASHTAGS_ATTR_ID = 23171
const activeDetailTab = ref('info')
const form = reactive({})
const imagesText = ref('')
const attributesText = ref('[]')
const attributesParseError = ref(false)
const aiGenerating = ref(false)
const publishingGroup = ref(false)

// 复制到其他店：候选店 = 除草稿当前店外的其它店
const copyTargets = computed(() =>
  store.storeList.filter((s) => String(s.client_id) !== String(props.draft.store_client_id)))
async function copyToStore(cid) {
  try {
    const r = await api.copyToStore(props.draft.id, cid)
    if (!r || !r.ok) { ElMessage.error((r && r.error) || '复制失败'); return }
    const name = (store.storeList.find((s) => String(s.client_id) === String(cid)) || {}).name || cid
    ElMessage.success(`已复制到「${name}」，切到该店即可看到`)
  } catch (e) {
    ElMessage.error('复制失败：' + ((e && e.message) || e))
  }
}

const variantGroup = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  return sr && sr.variant_group ? String(sr.variant_group) : ''
})

const variantList = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  return Array.isArray(sr.variants) ? sr.variants : []
})

async function onPublishGroup() {
  const grp = variantGroup.value
  if (!grp) return
  try {
    await ElMessageBox.confirm(
      `将把该分组(${grp})的所有变体合并成一张卡发布到 Ozon。这是不可逆操作，确定？`,
      '整组发布确认',
      { type: 'warning', confirmButtonText: '发布', cancelButtonText: '取消' }
    )
  } catch (e) {
    return // 用户取消
  }
  publishingGroup.value = true
  try {
    const r = await api.publishGroup(grp)
    if (r && r.published) {
      ElMessage.success(`已提交整组发布：${r.count} 个变体（型号名 ${r.model_name}）`)
    } else {
      ElMessage.error('整组发布未成功：' + (JSON.stringify(r && r.errors || r) || '未知'))
    }
  } catch (e) {
    ElMessage.error('整组发布失败：' + (e && e.message ? e.message : String(e)))
  } finally {
    publishingGroup.value = false
  }
}

// ChatGPT 图片提示词（即用即弃，不写库）
const imgGenN = ref(3)
const imgGenLoading = ref(false)
const imgPrompts = ref(null)
// 详情图缩略图：优先本地副本(detail_local，避 1688 防盗链 FAILED)，按下标对齐；缺位回退源 URL
const detailThumbs = computed(() => {
  const p = imgPrompts.value
  if (!p) return []
  const src = p.detail_images || []
  const loc = p.detail_local || []
  return src.map((u, i) => loc[i] || u)
})
const allImgPromptsText = computed(() => {
  const p = imgPrompts.value
  if (!p) return ''
  const lines = [`主图: ${p.main || ''}`]
  ;(p.selling_points || []).forEach((s, i) => lines.push(`卖点图${i + 1}: ${s || ''}`))
  // 附远程原图 URL（公网可访问，ChatGPT 能直接抓取当参考图；本地 /media 它访问不到故不附）
  const imgs = (p.source_images || []).filter(Boolean)
  if (imgs.length) {
    lines.push('主图参考（请抓取以下图片作为产品参考）:\n' + imgs.map((u, i) => `${i + 1}. ${u}`).join('\n'))
  }
  // 1688 详情长图：材质/细节/场景，给 ChatGPT 更全的实物参考，生成主图更贴合
  const det = (p.detail_images || []).filter(Boolean)
  if (det.length) {
    lines.push('详情图参考（产品细节/材质/场景）:\n' + det.map((u, i) => `${i + 1}. ${u}`).join('\n'))
  }
  return lines.join('\n\n')
})
async function doImagePrompts() {
  imgGenLoading.value = true
  try {
    const r = await api.aiImagePrompts(props.draft.id, Number(imgGenN.value) || 3)
    if (!r || !r.ok) { ElMessage.error((r && r.error) || '生成失败'); return }
    imgPrompts.value = r
    ElMessage.success('提示词已生成')
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally {
    imgGenLoading.value = false
  }
}
async function copyText(t) {
  try {
    await navigator.clipboard.writeText(String(t || ''))
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败（浏览器不支持或无剪贴板权限）')
  }
}

// 抽屉用图片数组（来源于编辑框真相源 imagesText）
const drawerImages = computed(() =>
  String(imagesText.value || '').split('\n').map((s) => s.trim()).filter(Boolean))

// 源URL → 本地副本路径的映射（仅用于显示，不影响数据真相源）
const localMap = computed(() => {
  const out = {}
  const imgs = Array.isArray(props.draft.images) ? props.draft.images : []
  const loc = Array.isArray(props.draft.local_images) ? props.draft.local_images : []
  imgs.forEach((u, i) => { if (u && loc[i]) out[u] = loc[i] })
  return out
})

// 必填属性状态
const required = ref([])
const optional = ref([])
const missing = ref([])
const attrWarning = ref('')
const requiredSummary = ref('选好类目后检查')
const showOptional = ref(false)
const attrLanguage = ref('ZH_HANS')
const attrInputs = reactive({})
const attrOptions = reactive({})
const attrLoading = reactive({})

const missingIds = computed(() => new Set(missing.value.map((m) => m.id)))
const optionalFilledCount = computed(
  () => optional.value.filter((a) => !!attrInputs[a.id]).length)

// --- AI 待确认草案 ---
const proposalActive = computed(() => !!(props.draft && props.draft.ai_proposal))
const proposal = computed(() => (props.draft && props.draft.ai_proposal) || null)
const proposalFieldLabels = {
  ozon_title: '俄语标题', description: '描述', brand_name: '品牌',
  weight_g: '重量(g)', length_mm: '长(cm)', width_mm: '宽(cm)', height_mm: '高(cm)', category_path: '类目',
}
const proposalAiAttrs = computed(() => (proposal.value?.attributes || []).filter((a) => a.source === 'ai'))
const proposalMissingAttrs = computed(() => (proposal.value?.attributes || []).filter((a) => a.source === 'missing'))

const categoryModel = computed({
  get: () => ({ cat: form.category_id, type: form.type_id }),
  set: (v) => { form.category_id = v.cat ?? ''; form.type_id = v.type ?? '' },
})

function initFromDraft(d) {
  const src = d || {}
  // attributes 后端可能存成 {}（空字典默认值）或数组；编辑态统一按数组处理
  const attrsArr = Array.isArray(src.attributes) ? src.attributes : []
  const attrTags = attrTextValue(attrsArr.find((a) => Number(a?.id) === HASHTAGS_ATTR_ID))
  Object.assign(form, {
    purchase_url: src.purchase_url ?? '',
    ozon_title: src.ozon_title ?? '',
    category_id: src.category_id ?? '',
    type_id: src.type_id ?? '',
    brand_id: src.brand_name === NO_BRAND_NAME ? (src.brand_id ?? null) : null,
    brand_name: NO_BRAND_NAME,
    cost_cny: src.cost_cny ?? '',
    price: src.price ?? '',
    old_price: src.old_price ?? '',
    stock: src.stock ?? 0,
    weight_g: src.weight_g ?? 0,
    length_mm: src.length_mm ?? 0,
    width_mm: src.width_mm ?? 0,
    height_mm: src.height_mm ?? 0,
    purchase_note: src.purchase_note ?? '',
    supplier: src.supplier ?? '',
    offer_id: src.offer_id ?? '',
    description: src.description ?? '',
    tags: Array.isArray(src.tags)
      ? src.tags.join(', ')
      : (Array.isArray(src.source_raw?.tags) ? src.source_raw.tags.join(', ') : String(src.source_raw?.tags || attrTags || '')),
  })
  imagesText.value = (Array.isArray(src.images) ? src.images : []).join('\n')
  attributesText.value = JSON.stringify(attrsArr, null, 2)
  attributesParseError.value = false
  // 当前属性值回填到必填控件
  for (const k of Object.keys(attrInputs)) delete attrInputs[k]
  for (const a of attrsArr) {
    if (a && a.id != null && Array.isArray(a.values)) {
      const txt = a.values.map((v) => v.value || '').filter(Boolean).join(' , ')
      if (txt) attrInputs[a.id] = txt
    }
  }
  attrInputs[85] = form.brand_name || NO_BRAND_NAME
}

function numOrNull(v) {
  return v === '' || v === null || v === undefined ? null : Number(v)
}

function collectPatch() {
  let attributes
  try {
    attributes = JSON.parse(attributesText.value || '[]')
    if (!Array.isArray(attributes)) attributes = []
    attributesParseError.value = false
  } catch {
    attributes = Array.isArray(props.draft.attributes) ? props.draft.attributes : []
    attributesParseError.value = true
  }
  const price = form.price
  const tags = splitTags(form.tags)
  attributes = attributes.filter((a) => Number(a?.id) !== HASHTAGS_ATTR_ID)
  const hashtagValue = cleanHashtags(tags)
  if (hashtagValue) {
    attributes.push({ id: HASHTAGS_ATTR_ID, values: [{ value: hashtagValue }] })
  }
  return {
    purchase_url: form.purchase_url,
    ozon_title: form.ozon_title,
    description: form.description,
    category_id: form.category_id,
    type_id: form.type_id,
    brand_id: form.brand_name === NO_BRAND_NAME ? (form.brand_id === '' ? null : (form.brand_id ?? null)) : null,
    brand_name: NO_BRAND_NAME,
    stock: Number(form.stock || 0),
    weight_g: numOrNull(form.weight_g),
    length_mm: numOrNull(form.length_mm),
    width_mm: numOrNull(form.width_mm),
    height_mm: numOrNull(form.height_mm),
    price,
    old_price: (String(form.old_price || '').trim()) || price,
    cost_cny: numOrNull(form.cost_cny),
    images: imagesText.value.split('\n').map((v) => v.trim()).filter(Boolean),
    purchase_note: form.purchase_note,
    supplier: form.supplier,
    offer_id: form.offer_id,
    attributes,
    source_raw: { ...(props.draft.source_raw || {}), tags },
  }
}

function splitTags(value) {
  return String(value || '')
    .split(/[\n,，]+/)
    .map((v) => v.trim())
    .filter(Boolean)
}

function cleanHashtags(tags) {
  const out = []
  const seen = new Set()
  for (const raw of tags || []) {
    const body = String(raw || '').trim().replace(/^#+/, '').replace(/\s+/g, '_')
    if (!body || seen.has(body)) continue
    seen.add(body)
    out.push(`#${body}`)
    if (out.length >= 30) break
  }
  return out.join(' ')
}

function attrTextValue(attr) {
  const values = Array.isArray(attr?.values) ? attr.values : []
  return values.map((v) => v?.value || '').filter(Boolean).join(' ')
}

async function save() {
  await ensureDefaultBrandResolved()
  const r = await api.patchDraft(props.draft.id, collectPatch())
  if (r && r.draft) store.upsertDraft(r.draft)
  return r
}

async function ensureDefaultBrandResolved() {
  if (form.brand_id || form.brand_name !== NO_BRAND_NAME || !form.category_id || !form.type_id) return
  try {
    const r = await api.attributeValues(form.category_id, form.type_id, 85, NO_BRAND_NAME, 'RU')
    const items = r.result || []
    const hit = items.find((it) => String(it.value || '').trim().toLowerCase() === NO_BRAND_NAME.toLowerCase()) || items[0]
    if (hit && hit.id) {
      form.brand_id = hit.id
      form.brand_name = hit.value || NO_BRAND_NAME
      attrInputs[85] = form.brand_name
    }
  } catch {
    // Ozon 字典暂时不可用时，仍保留“无品牌”显示；发布前校验会继续提示品牌缺失。
  }
}

async function doTranslate() {
  await save()
  const r = await api.translateDraft(props.draft.id)
  store.upsertDraft(r.draft)
  initFromDraft(r.draft)
  if (r.still_cjk) ElMessage.warning(r.note || '仍含中文')
  else ElMessage.success('已翻译')
  return r
}

async function doAiGenerate() {
  await save()  // 先保存当前编辑，让 source_raw 等字段是最新的
  aiGenerating.value = true
  let r
  try {
    r = await api.aiGenerate(props.draft.id)
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
    return
  } finally {
    aiGenerating.value = false
  }
  if (!r || !r.ok) {
    ElMessage.error((r && r.error) || 'AI 生成失败')
    return
  }
  if (r.mode === 'applied') {
    // 自动模式：后端已写入草稿，直接回填 form
    if (r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft); await runRequiredCheck() }
    ElMessage.success('AI 已自动应用')
  } else {
    // 人工模式（draft）：后端写了 ai_proposal，按当前 filter/page 重拉草稿让待确认区渲染
    // （不强拉 status:'all'——store 当前可能在别的 tab/页，会 find 不到当前 draft）
    await store.loadDrafts()
    ElMessage.success('AI 草案已生成，确认后点应用')
  }
}

// 草案补丁统一容错：req() 非 2xx 会 throw，旧代码没接住 → 静默无反应（曾导致
// "点应用没反应"：重复点击草案已清空时后端 400 被吞）。统一弹后端中文错误。
async function proposalPatch(patch, errLabel = '操作失败') {
  try {
    const r = await api.aiProposalPatch(props.draft.id, patch)
    if (r) store.upsertDraft({ ...props.draft, ai_proposal: r.proposal })
  } catch (err) {
    ElMessage.error(`${errLabel}: ` + ((err && err.message) || err))
  }
}

async function editProposalField(key, value) { await proposalPatch({ op: 'edit_field', key, value }) }
async function deleteProposalField(key) { await proposalPatch({ op: 'delete_field', key }) }
async function editProposalAttr(id, value) { await proposalPatch({ op: 'edit_attr', id, value }) }
async function deleteProposalAttr(id) { await proposalPatch({ op: 'delete_attr', id }) }

async function applyProposal() {
  try {
    const r = await api.aiProposalApply(props.draft.id)
    if (!r) { ElMessage.error('应用失败'); return }
    if (r.draft) {
      const hit = store.upsertDraft(r.draft)
      initFromDraft(r.draft)
      await runRequiredCheck()
      if (!hit) await store.loadDrafts()   // 草稿不在当前分页页面 → 兜底重拉，让草案区消失
    }
    if (r.unmapped && r.unmapped.length) ElMessage.warning(`${r.unmapped.length} 个特征未匹配字典，请手动确认`)
    else ElMessage.success('已应用到商品')
  } catch (err) {
    ElMessage.error('应用失败: ' + ((err && err.message) || err))
  }
}

async function discardProposal() {
  try {
    const r = await api.aiProposalPatch(props.draft.id, { op: 'discard' })
    if (r) store.upsertDraft({ ...props.draft, ai_proposal: null })
  } catch (err) {
    ElMessage.error('放弃失败: ' + ((err && err.message) || err))
  }
}

async function onImagesChange(arr) {
  imagesText.value = (arr || []).join('\n')
  await save()
}

// --- Agnes 生图/生视频 ---
const aiImgDlg = ref(false)
const aiVidDlg = ref(false)

// 打开前先 save()：后端按 DB 里的草稿取图/取标题，且生成完成后会用 DB 状态回填表单，
// 不存会把用户未保存的编辑悄悄丢掉（与 doAiGenerate 的约定一致）
async function openAiImage() {
  await save()
  aiImgDlg.value = true
}

async function openAiVideo() {
  await save()
  aiVidDlg.value = true
}
// 对话框选图列表：url 为真相源、disp 优先本地副本（避 1688 防盗链）
const aiDialogImages = computed(() =>
  drawerImages.value.map((u) => ({ url: u, disp: localMap.value[u] || u })))

const richContentJson = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  return (sr && sr.rich_content_json) || null
})

function onAiImageDone(draft) {
  // 后端已把生成图写进 draft.images，回填表单（imagesText 是真相源）
  if (draft) { store.upsertDraft(draft); initFromDraft(draft) }
}

async function onAiVideoDone() {
  // 视频在后台线程写库（video_url + source_raw.video_local），重拉当前页让详情刷新
  await store.loadDrafts()
}

async function onVideoChange(url) {
  const r = await api.patchDraft(props.draft.id, { video_url: url })
  if (r && r.draft) store.upsertDraft(r.draft)
}

// 有值的排前面（稳定排序：同状态保持原相对顺序）。attrInputs[id] 有值=已填。
function _sortByFilled(list) {
  return [...list].sort((x, y) => (attrInputs[y.id] ? 1 : 0) - (attrInputs[x.id] ? 1 : 0))
}

// ---- 必填校验（带竞态保护）----
let reqCheckSeq = 0
async function runRequiredCheck() {
  const seq = ++reqCheckSeq
  const stale = () => seq !== reqCheckSeq
  attrWarning.value = ''
  if (!form.category_id || !form.type_id) {
    requiredSummary.value = '请先选好类目'
    required.value = []
    optional.value = []
    missing.value = []
    return
  }
  requiredSummary.value = '检查中…'
  try {
    const res = await api.requiredCheck(props.draft.id, attrLanguage.value)
    if (stale()) return
    if (res.attr_warning) {
      attrWarning.value = res.attr_warning
      requiredSummary.value = '无法获取'
      required.value = []
      optional.value = []
      missing.value = []
      return
    }
    // 有值的排前面、没值的往下（加载时排一次，稳定排序保留原相对顺序；不在打字时实时跳）
    required.value = _sortByFilled(filterDetachedTextAttrs(res.required || []))
    optional.value = _sortByFilled(filterDetachedTextAttrs(res.optional || []))
    missing.value = filterDetachedTextAttrs(res.missing || [])
    if (!required.value.length) {
      requiredSummary.value = '无必填属性'
    } else {
      const missCount = missing.value.length
      requiredSummary.value = missCount
        ? `缺 ${missCount} / ${required.value.length}`
        : `已齐 ${required.value.length}`
    }
  } catch (err) {
    if (stale()) return
    requiredSummary.value = '检查失败'
    attrWarning.value = String((err && err.message) || err)
  }
}

function filterDetachedTextAttrs(items) {
  return (items || []).filter((a) => !isDetachedTextAttr(a))
}

function isDetachedTextAttr(attr) {
  const id = Number(attr?.id)
  if (id === HASHTAGS_ATTR_ID) return true
  const name = String(attr?.name || '').trim().toLowerCase()
  return [
    '简介',
    '描述',
    '主题标签',
    '#хештеги',
    'хештеги',
    'аннотация',
    'описание',
    'описание товара',
  ].includes(name)
}

async function searchAttr(a, q) {
  if (!form.category_id || !form.type_id) return
  if (!q || q.length < 2) return
  attrLoading[a.id] = true
  try {
    const r = await api.attributeValues(form.category_id, form.type_id, a.id, q, attrLanguage.value)
    attrOptions[a.id] = r.result || []
  } finally {
    attrLoading[a.id] = false
  }
}

async function onAttrPick(a, id) {
  const opt = (attrOptions[a.id] || []).find((o) => o.id === id)
  const values = opt ? [{ dictionary_value_id: opt.id, value: opt.value }] : []
  setLocalAttribute(a.id, values)
  await save()
  await runRequiredCheck()
}

async function onAttrText(a, v) {
  const text = String(v || '').trim()
  setLocalAttribute(a.id, text ? [{ value: text }] : [])
  await save()
  await runRequiredCheck()
}

// 写入属性 JSON textarea（真相源）
function setLocalAttribute(attrId, values) {
  let arr = []
  try { arr = JSON.parse(attributesText.value || '[]') } catch { arr = [] }
  if (!Array.isArray(arr)) arr = []
  arr = arr.filter((a) => !(a && Number(a.id) === Number(attrId) && 'values' in a))
  if (values && values.length) arr.push({ id: Number(attrId), values })
  attributesText.value = JSON.stringify(arr, null, 2)
}

async function autoMap() {
  if (!form.category_id || !form.type_id) {
    requiredSummary.value = '请先选好类目'
    return
  }
  requiredSummary.value = '自动填充中…'
  try {
    await save() // 先存当前编辑，避免覆盖
    const r = await api.autoMap(props.draft.id)
    if (r && r.error) { requiredSummary.value = r.error; return }
    if (r && r.draft) store.upsertDraft(r.draft)
    const mc = (r && r.mapped_count) || 0
    const um = (r && r.unmapped ? r.unmapped.length : 0)
    requiredSummary.value = `已填 ${mc} 项${um ? `，${um} 项没匹配上` : ''}`
    await runRequiredCheck()
  } catch (err) {
    requiredSummary.value = '自动填充失败：' + ((err && err.message) || err)
  }
}

// 切换草稿时重建表单并重新校验
watch(() => props.draft, (d) => {
  initFromDraft(d)
  runRequiredCheck()
}, { immediate: true })

// 类目变化时重新校验
watch(() => [form.category_id, form.type_id], () => {
  ensureDefaultBrandResolved()
  runRequiredCheck()
})

watch(attrLanguage, () => {
  Object.keys(attrOptions).forEach((key) => { attrOptions[key] = [] })
})

defineExpose({ form, imagesText, attributesText, collectPatch, save, runRequiredCheck, autoMap, doTranslate, doAiGenerate, onImagesChange, onVideoChange, proposalActive, proposal, proposalAiAttrs, proposalMissingAttrs, editProposalField, deleteProposalField, editProposalAttr, deleteProposalAttr, applyProposal, discardProposal, imgGenN, imgGenLoading, imgPrompts, allImgPromptsText, detailThumbs, doImagePrompts, copyText, aiImgDlg, aiVidDlg, aiDialogImages, openAiImage, openAiVideo, onAiImageDone, onAiVideoDone, attrLanguage, showOptional })
</script>

<style scoped>
.draft-detail {
  --detail-blue: var(--c-brand);
  --detail-text: var(--c-text);
  --detail-muted: var(--c-text-2);
  --detail-border: rgba(0, 0, 0, 0.08);
  --detail-soft: rgba(0, 0, 0, 0.03);
  container-type: inline-size;
  color: var(--detail-text);
  max-width: 1280px;
  margin: 0 auto;
  padding: 4px 8px 40px;
}
.detail-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
}
.detail-hero.compact {
  align-items: center;
  margin-bottom: 8px;
}
.detail-meta-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
  color: var(--detail-muted);
  font-size: 13px;
}
.detail-meta-line strong {
  color: var(--detail-text);
  font-size: 16px;
}
.hero-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.detail-tabs {
  margin-bottom: 18px;
}
.source-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  margin: 0 0 14px;
  padding: 14px 16px;
  border: 1px solid var(--detail-border);
  border-radius: 14px;
  background: var(--detail-soft);
}
.source-summary-title {
  color: var(--detail-muted);
  font-size: 12px;
  margin-bottom: 4px;
}
.source-summary-name {
  color: var(--detail-text);
  font-weight: 700;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.source-summary-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  color: var(--detail-muted);
  font-size: 12px;
  white-space: nowrap;
}
.source-summary-meta span {
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--detail-soft);
}
.source-summary-meta a {
  color: var(--detail-blue);
  font-weight: 700;
  text-decoration: none;
}
:deep(.detail-tabs .el-tabs__header) {
  margin-bottom: 0;
}
:deep(.detail-tabs .el-tabs__item) {
  font-weight: 700;
}
.detail-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 28px;
  align-items: start;
}
.detail-main {
  min-width: 0;
}
.ozon-section,
.ai-result-section {
  border: 1px solid var(--detail-border);
  border-radius: 18px;
  background: var(--gp-glass);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 8px 28px rgba(20, 34, 59, 0.06);
}
.ozon-section {
  padding: 24px;
}
.section-head,
.section-head-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.section-head {
  margin-bottom: 20px;
}
.section-head-row {
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  color: var(--c-surface);
  background: var(--detail-blue);
  font-weight: 700;
  flex: 0 0 auto;
}
.section-head h3,
.prompt-card h4,
.validation-card h4 {
  margin: 0;
  font-size: 20px;
  line-height: 1.25;
}
.section-head p {
  margin: 4px 0 0;
  color: var(--detail-muted);
  font-size: 13px;
}
.field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  column-gap: 18px;
}
.field-wide {
  grid-column: 1 / -1;
}
.inline-action-field {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
}
.inline-action-field .el-input {
  flex: 1;
}
.media-inline { width: 100%; }
.detail-section { margin-bottom: 18px; scroll-margin-top: 76px; }
.section-row { display: flex; justify-content: space-between; align-items: center; }
.dims-row { display: flex; align-items: center; gap: 6px; }
.dims-row .el-input { max-width: 140px; }
.req { color: var(--c-danger); margin: 0 2px; }
.attr-warning { color: var(--c-danger); font-size: 13px; margin: 4px 0; }
.req-attr-list {
  display: grid;
  gap: 10px;
}
.req-attr-item {
  display: grid;
  grid-template-columns: minmax(180px, 280px) minmax(0, 1fr);
  align-items: center;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(0,0,0,0.06);
}
.req-attr-item.missing .ra-head { color: var(--c-danger); }
.ra-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.ra-control {
  min-width: 0;
}
.req-attr-state { margin-left: 8px; font-size: 12px; color: var(--c-text-3); }
.attr-state-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--c-danger);
  flex: 0 0 auto;
}
.attr-state-dot.ok {
  background: var(--c-success);
}
/* 非必填且为空：白点（描边可见；必填且为空仍是基础红点；有值统一绿点） */
.attr-state-dot.neutral {
  background: var(--c-surface);
  box-shadow: 0 0 0 1px var(--c-border) inset;
}
.attr-group-label { font-size: 12px; color: var(--c-text-3); font-weight: 600; margin: 6px 0 8px; }
.optional-toggle { margin: 8px 0 4px; }
.optional-list { opacity: 0.95; }
.req-attr-item.opt-filled .ra-head { color: var(--c-success); }
.muted { color: var(--c-text-3); }
.prompt-card,
.validation-card {
  margin-top: 18px;
  border: 1px solid var(--detail-border);
  border-radius: 14px;
  background: var(--detail-soft);
  padding: 16px;
}
.media-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.variant-section { margin-top: 12px; }
.rich-section {
  margin-top: 18px;
  border: 1px solid var(--detail-border);
  border-radius: 14px;
  background: var(--gp-glass);
  padding: 16px;
}
.rich-section-title { font-size: 15px; font-weight: 700; color: var(--detail-text); margin-bottom: 10px; }
/* AI 内联结果区块 */
.ai-result-section { background: rgba(139,92,246,0.08); border-color: rgba(139,92,246,0.3); padding: 16px 18px; }
.ai-result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.ai-result-title { font-size: 14px; font-weight: 600; color: var(--gp-purple-soft); }
.ai-result-hint { font-size: 12px; font-weight: 400; color: var(--gp-faint); margin-left: 8px; }
/* AI 行布局 */
.ai-row { display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; border-top: 1px dashed rgba(139,92,246,0.2); font-size: 13px; }
.ai-row-block { flex-direction: column; }
.ai-row-head { display: flex; align-items: center; gap: 8px; }
.ai-row-label { min-width: 110px; color: var(--gp-muted); font-weight: 500; flex-shrink: 0; }
/* 关键词 */
.ai-kw-tag { background: rgba(139,92,246,0.15); }
/* 特征列表 */
.ai-preview-empty { font-size: 13px; color: var(--c-text-3); padding: 2px 0; }
.proposal-actions { margin-top: 12px; display: flex; gap: 8px; }
/* 图片缩略图（AI 待确认草案区 + 图片提示词参考图共用） */
.ai-thumb-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.ai-thumb { width: 64px; height: 64px; border-radius: 4px; border: 1px solid var(--c-border-soft); }
/* ChatGPT 图片提示词面板 */
.img-gen-bar { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.img-hint { font-size: 12px; color: var(--c-text-3); margin: 6px 0; line-height: 1.5; }
.img-prompt-block { margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }
.ipb-head { display: flex; justify-content: space-between; align-items: center; }
.ipb-text { font-size: 13px; color: var(--gp-text); white-space: pre-wrap; word-break: break-word; margin-top: 4px; }

:deep(.ozon-form .el-form-item) {
  margin-bottom: 18px;
}
:deep(.el-input__wrapper),
:deep(.el-textarea__inner) {
  border-radius: 10px;
}

@media (max-width: 1080px) {
  .detail-shell {
    grid-template-columns: 1fr;
  }
  .detail-sidebar {
    position: static;
  }
}

@media (max-width: 720px) {
  .draft-detail {
    padding: 0 0 32px;
  }
  .detail-hero {
    flex-direction: column;
  }
  .detail-hero h2 {
    font-size: 22px;
  }
  .ozon-stepper {
    overflow-x: auto;
    gap: 12px;
  }
  .step-pill {
    white-space: nowrap;
  }
  .ozon-section {
    padding: 16px;
    border-radius: 14px;
  }
  .field-grid,
  .req-attr-item {
    grid-template-columns: 1fr;
  }
  :deep(.ozon-form .el-form-item) {
    display: block;
  }
  :deep(.ozon-form .el-form-item__label) {
    width: auto !important;
    justify-content: flex-start;
    margin-bottom: 6px;
  }
  :deep(.ozon-form .el-form-item__content) {
    margin-left: 0 !important;
  }
  .inline-action-field,
  .dims-row {
    flex-wrap: wrap;
  }
}

@container (max-width: 900px) {
  .detail-shell {
    grid-template-columns: 1fr;
    gap: 18px;
  }
  .detail-sidebar {
    position: static;
  }
  .detail-hero {
    flex-direction: column;
    gap: 12px;
  }
  .detail-hero h2 {
    font-size: 26px;
    max-width: none;
  }
  .hero-actions {
    flex-wrap: wrap;
  }
  .ozon-stepper {
    overflow-x: auto;
    gap: 12px;
  }
  .step-pill {
    white-space: nowrap;
  }
  .field-grid {
    grid-template-columns: 1fr;
  }
  .section-head-row {
    flex-wrap: wrap;
  }
}

@container (max-width: 620px) {
  .detail-hero h2 {
    font-size: 24px;
  }
  .ozon-section {
    padding: 16px;
    border-radius: 14px;
  }
  .section-head,
  .section-head-row {
    gap: 10px;
  }
  .req-attr-item {
    grid-template-columns: 1fr;
  }
  :deep(.ozon-form .el-form-item) {
    display: block;
  }
  :deep(.ozon-form .el-form-item__label) {
    width: auto !important;
    justify-content: flex-start;
    margin-bottom: 6px;
  }
  :deep(.ozon-form .el-form-item__content) {
    margin-left: 0 !important;
  }
  .inline-action-field,
  .dims-row {
    flex-wrap: wrap;
  }
}
</style>
