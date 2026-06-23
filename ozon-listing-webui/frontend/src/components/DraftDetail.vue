<template>
  <div class="draft-detail">
    <div class="detail-hero compact">
      <div class="detail-meta-line">
        <strong>商品详情</strong>
        <span>来源：{{ draft.source_platform || '未知' }}</span>
      </div>
      <div class="hero-actions">
        <el-button :loading="copyLoading" @click="doTryCopy">一键复制(官方)</el-button>
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

    <section class="smart-listing">
      <div class="smart-head">
        <b>⚡ 一键上架</b>
        <span class="smart-hint">理解 → 推荐 → 逐图俄化/重做 → 候选应用 → 富文本</span>
        <el-button size="small" :loading="understandLoading" @click="runStep(wfStep('understand'))">看图理解</el-button>
        <el-button size="small" :loading="recommendLoading" @click="doRecommend">智能推荐</el-button>
        <el-button size="small" :loading="aiGenerating" @click="doAiGenerate(true)">生成文案(标题/简介/标签)</el-button>
        <el-button size="small" :loading="planLoading" @click="loadPlan(true)">图集计划</el-button>
        <el-button size="small" :loading="copyLoading" @click="doTryCopy">一键复制(官方)</el-button>
      </div>
      <div class="wf-flow">
        <div class="wf-flow-head">
          <b>流程</b>
          <span class="wf-hint">结果自动保存,失败可单步重跑,也可手动逐步</span>
          <el-button type="primary" size="small" :loading="wfRunning" @click="runAuto">⚡ 一键自动跑(到发布)</el-button>
        </div>
        <div class="wf-step" v-for="(s, i) in WF" :key="s.id">
          <span class="wf-idx">{{ i + 1 }}</span>
          <span class="wf-dot" :class="wfState(s)"></span>
          <span class="wf-label">{{ s.label }}</span>
          <span class="wf-eta">{{ s.eta }}</span>
          <span class="wf-st" :class="wfState(s)">{{ wfStateText(s) }}</span>
          <el-button link size="small" :loading="wfStatus[s.id] === 'running'"
                     :disabled="wfRunning || (!wfDepOk(s) && !wfDone(s.id))" @click="runStep(s)">
            {{ wfDone(s.id) ? '重跑' : '运行' }}
          </el-button>
        </div>
      </div>
      <div v-if="understanding" class="smart-und">
        <div class="smart-und-h"><b>理解结果</b> <small>(看图抽取,供文案/作图复用)</small></div>
        <div v-if="understanding.type || understanding.material">品类:{{ understanding.type || '-' }} ｜ 材质:{{ understanding.material || '-' }}</div>
        <div v-if="understandingSpecs.length">规格:{{ understandingSpecs.join(' / ') }}</div>
        <div v-if="(understanding.points || []).length">卖点:{{ understanding.points.join(' · ') }}</div>
        <div v-if="(understanding.scenes || []).length">场景:{{ understanding.scenes.join(' · ') }}</div>
        <div v-if="(understanding.kit || []).length">包装:{{ understanding.kit.join(' · ') }}</div>
        <div v-if="(understanding.images || []).length" class="smart-roles">
          图片角色:<span v-for="im in understanding.images" :key="im.idx">图{{ im.idx }}·{{ im.role }}</span>
        </div>
      </div>
      <div v-if="recommendation" class="smart-rec">
        <div>推荐:<b>{{ recommendation.recommended }}</b> — {{ recommendation.reason }}</div>
        <table v-if="recommendation.per_image && recommendation.per_image.length" class="smart-pi">
          <tr v-for="p in recommendation.per_image" :key="p.idx">
            <td>图{{ p.idx }}</td><td>{{ p.role }}</td><td>默认:{{ p.default }}</td>
            <td>
              <el-button link size="small" :loading="imgActionLoading" @click="doWhiten(p.idx)">白底主图</el-button>
              <el-button link size="small" :loading="imgActionLoading" @click="doLocalize(p.idx)">俄化</el-button>
              <el-button link size="small" :loading="imgActionLoading" @click="doRegen(p)">重做</el-button>
              <el-button link size="small" :loading="imgActionLoading" @click="doScene(p.idx)">场景图</el-button>
            </td>
          </tr>
        </table>
      </div>
      <div v-if="plan.length" class="smart-plan">
        <div class="smart-und-h"><b>图集计划</b> <small>(按槽生成,同类挑不同源图,避免重复同角度)</small></div>
        <table class="smart-pi">
          <tr v-for="s in plan" :key="s.slot_id">
            <td>{{ s.label }}</td>
            <td>来源:图{{ s.source_idx }}</td>
            <td><span :class="['plan-st', s.status]">{{ planStatusText(s.status) }}</span></td>
            <td>
              <el-button link size="small" :loading="imgActionLoading" @click="doPlanSlot(s.slot_id)">
                {{ s.status === 'todo' ? '生成' : '重生成' }}
              </el-button>
            </td>
          </tr>
        </table>
      </div>
      <div v-if="candidates.length" class="smart-cands">
        <div>候选区 {{ candidates.length }} 张(数字请核对):</div>
        <div class="smart-cand-grid">
          <img v-for="(c, i) in candidates" :key="i" :src="c.url" :title="c.angle" />
        </div>
        <el-button size="small" type="primary" @click="doApplyCandidates">全部应用到图集</el-button>
        <el-button size="small" @click="doDiscardCandidates">清空候选</el-button>
      </div>
    </section>

    <el-tabs v-model="activeDetailTab" class="detail-tabs">
      <el-tab-pane label="商品信息" name="info" />
      <el-tab-pane label="特征" name="attrs" />
      <el-tab-pane label="图片" name="images" />
      <el-tab-pane label="视频" name="video" />
      <el-tab-pane label="富文本" name="richtext" />
      <el-tab-pane label="采购信息" name="purchase" />
    </el-tabs>
    <AiImageDialog v-model="aiImgDlg" :draft-id="draft.id" :images="aiDialogImages" @done="onAiImageDone" />
    <AiVideoDialog v-model="aiVidDlg" :draft-id="draft.id" :images="aiDialogImages" @done="onAiVideoDone" />

    <el-dialog v-model="preflightDlg" title="发布前核对" width="560px">
      <div v-if="preflightData">
        <div class="pf-banner info">ℹ️ 仅供参考,可直接发布;不完善的部分发布后也能在 Ozon 后台改</div>
        <ul class="pf-list">
          <li v-for="(c, i) in preflightData.checks" :key="i" :class="'pf-' + c.severity">
            <span class="pf-tag">{{ pfTag(c.severity) }}</span><span>{{ c.label }}</span>
          </li>
          <li v-for="(p, i) in preflightData.passed" :key="'p' + i" class="pf-pass">
            <span class="pf-tag">✓</span><span>{{ p }}</span>
          </li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="preflightDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmPublish">确认发布到 Ozon</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="slideshowDlg" title="多图生成视频(浏览器本地合成,不传服务器)" width="660px">
      <div class="ss-hint">勾选要进视频的图(按勾选顺序播放,每张约 2-3 秒 + 淡入)。本地用 Canvas 合成 MP4,不占服务器。</div>
      <div class="ss-grid">
        <div v-for="(u, i) in drawerImages" :key="i" class="ss-cell" :class="{ sel: ssSel.includes(i) }" @click="toggleSs(i)">
          <img :src="localMap[u] || u" loading="lazy" />
          <span v-if="ssSel.includes(i)" class="ss-num">{{ ssSel.indexOf(i) + 1 }}</span>
        </div>
      </div>
      <template #footer>
        <span class="ss-foot">已选 {{ ssSel.length }} 张 ≈ {{ ssDuration }}s</span>
        <el-button @click="slideshowDlg = false">取消</el-button>
        <el-button type="primary" :loading="ssLoading" :disabled="!ssSel.length" @click="doMakeSlideshow">生成视频</el-button>
      </template>
    </el-dialog>

    <div class="detail-shell">
      <main class="detail-main">
        <!-- AI 待确认草案（内联，逐项可改/删，点应用才写入商品）-->
        <section v-if="proposalActive" class="detail-section ai-result-section">
          <div class="ai-result-header">
            <span class="ai-result-title">AI 待确认草案 <small class="ai-result-hint">改好点【应用到商品】写入</small></span>
          </div>
          <div class="ai-field">
            <label>俄语标题</label>
            <el-input :model-value="(proposal.fields || {}).ozon_title || ''"
                      @change="(v) => editProposalField('ozon_title', v)" placeholder="俄语标题" />
          </div>
          <div class="ai-field">
            <label>简介（商品描述 + 营销文案）</label>
            <el-input type="textarea" :autosize="{ minRows: 4, maxRows: 16 }"
                      :model-value="(proposal.fields || {}).description || ''"
                      @change="(v) => editProposalField('description', v)" placeholder="俄语简介" />
          </div>
          <div class="ai-field">
            <label>标签 #Хештеги（空格分隔）</label>
            <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
                      :model-value="proposalTags" @change="editProposalTags" placeholder="#тег1 #тег2 …" />
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
              <el-form-item label="尺寸 长×宽×高(mm)" class="field-wide">
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
              <el-button link type="primary" :loading="!!attrLoading.ai" @click="doAiFill">AI 填特征</el-button>
              <el-button link type="primary" @click="runRequiredCheck">重新检查</el-button>
            </span>
          </div>
          <div v-if="attrWarning" class="attr-warning">▲ {{ attrWarning }}</div>
          <template v-else>
            <!-- 区别特征(变体维度)：合并成一张卡时各变体不同的属性(如颜色)，置顶突出、不折叠 -->
            <template v-if="aspects.length">
              <div class="attr-group-label">区别特征（变体）<span class="muted">— 合并成一张卡时各变体靠它区分</span></div>
              <div class="req-attr-list">
                <div v-for="a in aspects" :key="a.id" class="req-attr-item" :class="{ missing: missingIds.has(a.id) }">
                  <div class="ra-head">
                    <span class="attr-state-dot" :class="{ ok: attrHasValue(a.id), neutral: !attrHasValue(a.id) }"></span>
                    <span v-if="a.is_required" class="req">*</span>{{ a.name || ('属性' + a.id) }}
                  </div>
                  <div class="ra-control">
                    <el-select
                      v-if="Number(a.dictionary_id) > 0"
                      v-model="attrInputs[a.id]"
                      :multiple="!!a.is_collection"
                      :multiple-limit="a.max_value_count || 0"
                      filterable
                      clearable
                      :remote="!!attrOversized[a.id]"
                      :remote-method="(q) => searchAttr(a, q)"
                      :loading="!!attrLoading[a.id]"
                      placeholder="点开选择（可输中文搜）"
                      @visible-change="(open) => open && ensureAttrOptions(a)"
                      @change="(id) => onAttrPick(a, id)"
                    >
                      <el-option v-for="opt in (attrOptions[a.id] || [])" :key="opt.id" :label="opt.value" :value="opt.id" />
                    </el-select>
                    <el-input v-else v-model="attrInputs[a.id]" placeholder="输入文本值" @change="(v) => onAttrText(a, v)" />
                  </div>
                </div>
              </div>
            </template>

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
                    :multiple="!!a.is_collection"
                    :multiple-limit="a.max_value_count || 0"
                    filterable
                    clearable
                    :remote="!!attrOversized[a.id]"
                    :remote-method="(q) => searchAttr(a, q)"
                    :loading="!!attrLoading[a.id]"
                    placeholder="点开选择（可输中文搜）"
                    @visible-change="(open) => open && ensureAttrOptions(a)"
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

            <div v-if="optional.length" class="attr-group-label">
              可选（{{ optionalFilledCount }}/{{ optional.length }} 已填）
              <el-button link type="primary" size="small" @click="showOptional = !showOptional">
                {{ showOptional ? '收起未填项' : '展开未填项' }}
              </el-button>
            </div>
            <div v-if="optionalShown.length" class="req-attr-list optional-list">
              <div
                v-for="a in optionalShown"
                :key="a.id"
                class="req-attr-item"
                :class="{ 'opt-filled': attrHasValue(a.id) }"
              >
                <div class="ra-head">
                  <span class="attr-state-dot" :class="{ ok: !!attrInputs[a.id], neutral: !attrInputs[a.id] }"></span>
                  {{ a.name || ('属性' + a.id) }}
                </div>
                <div class="ra-control">
                  <el-select
                    v-if="Number(a.dictionary_id) > 0"
                    v-model="attrInputs[a.id]"
                    :multiple="!!a.is_collection"
                    :multiple-limit="a.max_value_count || 0"
                    filterable
                    clearable
                    :remote="!!attrOversized[a.id]"
                    :remote-method="(q) => searchAttr(a, q)"
                    :loading="!!attrLoading[a.id]"
                    placeholder="点开选择（可输中文搜）"
                    @visible-change="(open) => open && ensureAttrOptions(a)"
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
        <section v-show="activeDetailTab === 'images'" id="product-images" class="detail-section ozon-section">
          <div class="section-head">
            <span class="section-index">4</span>
            <div>
              <h3>图片</h3>
              <p>整理主图/详情图;下方可多选图 → 批量 白底/细节/俄化/场景 → 候选区。</p>
            </div>
          </div>
          <div class="media-inline">
            <MediaManager
              only="images"
              :images="drawerImages"
              :video-url="draft.video_url || ''"
              :draft-id="draft.id"
              :local-map="localMap"
              :image-types="imageTypes"
              @update:images="onImagesChange"
              @update:videoUrl="onVideoChange"
            >
              <template #image-actions>
                <el-button size="small" @click="openAiImage">AI 生成图片</el-button>
                <el-button size="small" @click="sortByType">按类型排序</el-button>
              </template>
              <template #image-extra>
                <div class="batch-card">
                  <div class="section-row">
                    <h4>多选图 → 批量出图</h4>
                    <span class="batch-bar">
                      已选 {{ batchSel.length }} 张
                      <el-button size="small" :disabled="!batchSel.length" :loading="batchLoading" @click="runBatch('white')">白底图</el-button>
                      <el-button size="small" :disabled="!batchSel.length" :loading="batchLoading" @click="runBatch('detail')">细节图</el-button>
                      <el-button size="small" :disabled="!batchSel.length" :loading="batchLoading" @click="runBatch('localize')">俄化</el-button>
                      <el-button size="small" :disabled="!batchSel.length" :loading="batchLoading" @click="runBatch('scene')">场景图</el-button>
                      <el-button size="small" :disabled="!batchSel.length" :loading="batchLoading" @click="runBatch('redo')">重做</el-button>
                    </span>
                  </div>
                  <div class="img-hint">多色变体/Ozon 竞品图：用每张图<b>自己的真实产品</b>「重做」成你的原创图——颜色天然正确，也跟竞品不同。</div>
                  <div class="img-hint">勾选要处理的图(可多选),点动作 → 逐张生成进候选区,确认后「全部应用」。</div>
                  <div class="batch-grid">
                    <div v-for="(u, i) in drawerImages" :key="i" class="batch-cell" :class="{ sel: batchSel.includes(i) }" @click="toggleBatch(i)">
                      <img :src="localMap[u] || u" loading="lazy" />
                      <span v-if="batchSel.includes(i)" class="batch-num">{{ batchSel.indexOf(i) + 1 }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </MediaManager>
          </div>
        </section>

        <!-- 视频 -->
        <section v-show="activeDetailTab === 'video'" id="product-video" class="detail-section ozon-section">
          <div class="section-head">
            <span class="section-index">5</span>
            <div>
              <h3>视频</h3>
              <p>上传视频，或用主图 AI 生成短视频。</p>
            </div>
          </div>
          <div class="media-inline">
            <MediaManager
              only="video"
              :images="drawerImages"
              :video-url="draft.video_url || ''"
              :draft-id="draft.id"
              :local-map="localMap"
              @update:images="onImagesChange"
              @update:videoUrl="onVideoChange"
            >
              <template #video-actions>
                <el-button size="small" @click="openAiVideo">AI 生成视频</el-button>
                <el-button size="small" @click="slideshowDlg = true">多图生成视频</el-button>
              </template>
            </MediaManager>
          </div>
        </section>

        <!-- 富文本 -->
        <section v-show="activeDetailTab === 'richtext'" id="product-richtext" class="detail-section ozon-section">
          <div class="section-head">
            <span class="section-index">6</span>
            <div>
              <h3>富文本</h3>
              <p>把图集拼成 Ozon A+ 富文本（每张图一个全宽块）。</p>
            </div>
          </div>
          <div class="rich-actions">
            <el-button size="small" :loading="richLoading" @click="doRichContent">生成富文本</el-button>
          </div>
          <section v-if="richContentJson" class="rich-section">
            <div class="rich-section-title">富文本预览</div>
            <RichContentPreview :rich-json="richContentJson" />
          </section>
          <div v-else class="rich-empty">还没有富文本，点上面「生成富文本」生成。</div>
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
import { makeSlideshowVideo } from '../slideshow.js'
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
const aspects = ref([])   // 区别特征(变体维度 is_aspect，如颜色)：置顶突出、不折叠
const missing = ref([])
const attrWarning = ref('')
const requiredSummary = ref('选好类目后检查')
const showOptional = ref(true)   // 表体可选字段默认展开（用户要求「放出来」）；仍可点「收起未填项」折叠
const attrLanguage = ref('ZH_HANS')
const attrInputs = reactive({})
const attrOptions = reactive({})
const attrLoading = reactive({})
const attrOversized = reactive({})   // attr_id -> true：字典过大，下拉不预载、回退实时搜
const attrOptLoaded = reactive({})   // attr_id -> true：全量选项已从缓存/官网加载过，避免重复请求

const missingIds = computed(() => new Set(missing.value.map((m) => m.id)))
// 是否已填:多选看数组非空、单选看标量非空(空数组 [] 是 truthy，不能直接 !! 判)
function attrHasValue(id) { const v = attrInputs[id]; return Array.isArray(v) ? v.length > 0 : (v != null && v !== '') }
const optionalFilledCount = computed(
  () => optional.value.filter((a) => attrHasValue(a.id)).length)
// 默认只显示有值的可选属性（空的非必填收起，减少干扰）；点「展开未填项」才显示全部
const optionalShown = computed(
  () => (showOptional.value ? optional.value : optional.value.filter((a) => attrHasValue(a.id))))

// --- AI 待确认草案 ---
const proposalActive = computed(() => !!(props.draft && props.draft.ai_proposal))
const proposal = computed(() => (props.draft && props.draft.ai_proposal) || null)
const proposalFieldLabels = {
  ozon_title: '俄语标题', description: '描述', brand_name: '品牌',
  weight_g: '重量(g)', length_mm: '长(mm)', width_mm: '宽(mm)', height_mm: '高(mm)', category_path: '类目',
}
const proposalAiAttrs = computed(() => (proposal.value?.attributes || []).filter((a) => a.source === 'ai'))
const proposalMissingAttrs = computed(() => (proposal.value?.attributes || []).filter((a) => a.source === 'missing'))
// 标签 = 草案里 attr 23171(#Хештеги)的值
// 主题标签清洗:把(可能整串/下划线连写的)值规整成 "#a #b"——保留词内 _(умный_дом)、只拆标签之间、去重≤30。
// 显示用，发布时后端 _hashtag_values 也会再拆一遍。
function cleanTags(s) {
  const seen = new Set(); const out = []
  for (const part of String(s || '').replace(/#/g, ' #').split(/\s+/)) {
    const t = part.replace(/^#+/, '').replace(/^_+|_+$/g, '').trim()
    if (!t || seen.has('#' + t)) continue
    seen.add('#' + t); out.push('#' + t)
    if (out.length >= 30) break
  }
  return out.join(' ')
}
const proposalTags = computed(() => {
  const a = (proposal.value?.attributes || []).find((x) => String(x.id) === '23171')
  return a ? cleanTags(a.value || '') : ''
})
function editProposalTags(v) { editProposalAttr(23171, cleanTags(v)) }

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
    // 已发布/已应用的 attr 23171 优先(AI 文案应用后就是它);否则回退采集的 tags。清洗成 "#a #b" 显示
    tags: cleanTags(attrTags)
      || cleanTags(Array.isArray(src.tags) ? src.tags.join(' ') : '')
      || cleanTags(Array.isArray(src.source_raw?.tags) ? src.source_raw.tags.join(' ') : String(src.source_raw?.tags || '')),
  })
  imagesText.value = (Array.isArray(src.images) ? src.images : []).join('\n')
  attributesText.value = JSON.stringify(attrsArr, null, 2)
  attributesParseError.value = false
  // 当前属性值回填到必填控件
  for (const k of Object.keys(attrInputs)) delete attrInputs[k]
  for (const k of Object.keys(attrOptLoaded)) delete attrOptLoaded[k]   // 换草稿:清「已加载」标记，重新按需拉
  for (const a of attrsArr) {
    if (a && a.id != null && Array.isArray(a.values) && a.values.length) {
      const dvids = a.values.map((v) => Number(v && v.dictionary_value_id) || 0).filter(Boolean)
      if (dvids.length) {
        // 字典属性:先按数组存所有 id(多选用)；单选会在 runRequiredCheck 拿到 is_collection 后归一化成标量。
        // 同时种当前选项保证回显(下拉打开会补全量)。
        attrInputs[a.id] = dvids
        attrOptions[a.id] = a.values
          .filter((v) => Number(v && v.dictionary_value_id))
          .map((v) => ({ id: Number(v.dictionary_value_id), value: v.value || String(v.dictionary_value_id) }))
      } else {
        const txt = a.values.map((v) => v.value || '').filter(Boolean).join(' , ')
        if (txt) attrInputs[a.id] = txt    // 自由文本属性
      }
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

async function doAiGenerate(copyOnly = false) {
  await save()  // 先保存当前编辑，让 source_raw 等字段是最新的
  aiGenerating.value = true
  let r
  try {
    r = copyOnly ? await api.aiCopy(props.draft.id) : await api.aiGenerate(props.draft.id)
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

const infoLoading = ref(false)
const copyLoading = ref(false)

async function doInfographic() {
  const wm = window.prompt('信息图右下角店铺水印文字（留空则不加）：', '')
  if (wm === null) return  // 取消
  infoLoading.value = true
  try {
    // 卖点：从描述切几条（主图作底，底部叠俄语标题+要点）
    const bullets = String(props.draft.description || '')
      .split(/[\n。.;；]+/).map((s) => s.trim()).filter(Boolean).slice(0, 4)
    const r = await api.makeInfographic(props.draft.id, { bullets, watermark: wm })
    if (r && r.ok) {
      if (r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) }
      ElMessage.success('俄语信息图已生成，已加入图片')
    } else {
      ElMessage.error((r && r.error) || '生成失败')
    }
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally {
    infoLoading.value = false
  }
}

async function doTryCopy() {
  copyLoading.value = true
  try {
    const r = await api.tryCopy(props.draft.id)
    if (r && r.copyable) {
      ElMessage.success(`可复制，已建官方复制卡（状态 ${r.status}，货号 ${r.offer_id}）`)
      await store.loadDrafts()
    } else {
      ElMessage.warning('此商品不可复制（源卡禁止复制），请走原创建卡')
    }
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally {
    copyLoading.value = false
  }
}

const richLoading = ref(false)
async function doRichContent() {
  richLoading.value = true
  try {
    // 富文本=有序大图(billboard)，俄语文字烤在图里；默认跳过主图、其余进富文本
    const r = await api.makeRichContent(props.draft.id, {})
    if (r && r.ok) {
      if (r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) }
      ElMessage.success(`富文本已生成（${r.blocks} 张大图）`)
    } else {
      ElMessage.error((r && r.error) || '生成失败')
    }
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally {
    richLoading.value = false
  }
}

// 一键上架:理解 / 推荐 / 逐图俄化重做 / 候选应用
const understandLoading = ref(false)
const recommendLoading = ref(false)
const recommendation = ref(null)
const candidates = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  return Array.isArray(sr.ai_image_candidates) ? sr.ai_image_candidates : []
})
const understanding = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  return (sr.understanding && typeof sr.understanding === 'object') ? sr.understanding : null
})
const understandingSpecs = computed(() => {
  const sp = (understanding.value && understanding.value.specs) || {}
  return Object.entries(sp).filter(([, v]) => v).map(([k, v]) => `${k}:${v}`)
})
// 图集类型 {图url: 类型}：AI 生成图取 source_raw.image_types；源图按看图理解的角色(按下标对齐)兜底
const imageTypes = computed(() => {
  const sr = (props.draft && props.draft.source_raw) || {}
  const out = { ...(sr.image_types || {}) }
  const roles = {}
  for (const im of ((sr.understanding && sr.understanding.images) || [])) {
    if (im && typeof im.idx === 'number') roles[im.idx] = im.role || ''
  }
  drawerImages.value.forEach((u, i) => { if (!out[u] && roles[i]) out[u] = roles[i] })
  return out
})
const TYPE_ORDER = ['白底', '主图', '整体', '细节', '场景', '尺寸', '卖点', '包装', '其他']
function sortByType() {
  const t = imageTypes.value
  const rank = (u) => { const i = TYPE_ORDER.indexOf(t[u] || '其他'); return i < 0 ? TYPE_ORDER.length : i }
  const sorted = drawerImages.value
    .map((u, i) => [u, i]).sort((a, b) => (rank(a[0]) - rank(b[0])) || (a[1] - b[1])).map((x) => x[0])
  onImagesChange(sorted)
  ElMessage.success('已按类型排序(主图→细节→场景→尺寸→卖点)')
}
async function doUnderstand() {
  understandLoading.value = true
  try {
    const r = await api.understand(props.draft.id)
    if (r && r.ok) {
      if (r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) }   // 回填的尺寸/价格即时刷进表单
      const af = r.autofill || {}
      const bits = []
      if (af.length_mm) bits.push(`尺寸 ${af.length_mm}×${af.width_mm}×${af.height_mm}cm`)
      if (af.weight_g) bits.push(`重量 ${af.weight_g}g`)
      if (af.price) bits.push(`默认价 ¥${af.price}/划线¥${af.old_price}`)
      ElMessage.success((r.cached ? '理解(缓存命中)' : '看图理解完成') + (bits.length ? ' · 已填 ' + bits.join('、') : ''))
    }
  } catch (err) { ElMessage.error(String((err && err.message) || err)) } finally { understandLoading.value = false }
}
// 类别识别(AI 类别下钻)→ 写入类目。特征是按类别来的，这是特征识别的前置。
async function doRecognizeCategory() {
  const r = await api.recognizeCategory(props.draft.id)
  if (r && r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft); await runRequiredCheck() }
  if (!r || !r.matched) throw new Error((r && r.note) || '未识别出类别')
  ElMessage.success('类别:' + (r.category_path || `${r.category_id}/${r.type_id}`))
}
// 特征值识别(按类别把采集特征填进上架属性)。需类别已定。
async function doAutoMapAttrs() {
  // 用 AI 按当前类目填特征(1688 参数名≠Ozon 属性名，按名硬对的 auto_map 几乎填不上 → 用 AI 语义对应)
  const r = await api.aiFillAttributes(props.draft.id)
  if (r && r.error) throw new Error(r.error)
  if (r && r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) }
  await runRequiredCheck()
  ElMessage.success(`AI 填特征 ${r && r.mapped_count != null ? r.mapped_count : ''} 项`)
}
// 「特征」tab 里点的「AI 填特征」(强；auto_map 是快速按名对，弱)
async function doAiFill() {
  attrLoading.ai = true
  try {
    const r = await api.aiFillAttributes(props.draft.id)
    if (r && r.error) { ElMessage.error(r.error); return }
    if (r && r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) }
    await runRequiredCheck()
    ElMessage.success(`AI 填特征 ${r && r.mapped_count != null ? r.mapped_count : ''} 项`)
  } catch (e) { ElMessage.error('AI 填特征失败: ' + ((e && e.message) || e)) } finally { attrLoading.ai = false }
}
async function doRecommend() {
  recommendLoading.value = true
  try {
    const r = await api.recommend(props.draft.id)
    if (r && r.ok) { recommendation.value = r.recommendation; if (!r.has_understanding) ElMessage.info('还没看图理解,建议先点「看图理解」') }
  } catch (err) { ElMessage.error(String((err && err.message) || err)) } finally { recommendLoading.value = false }
}
const imgActionLoading = ref(false)
// 选图生成(白底/俄化/重做/场景)统一走它：单一 loading 防并发，结果进候选区
async function _imgAction(fn, okMsg) {
  imgActionLoading.value = true
  try {
    const r = await fn()
    if (r && r.ok) { if (r.draft) store.upsertDraft(r.draft); ElMessage.success(okMsg) }
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally { imgActionLoading.value = false }
}
function doWhiten(idx) {
  return _imgAction(() => api.whitenMain(props.draft.id, { source_index: idx }), '白底主图完成,已进候选区')
}
function doLocalize(idx) {
  return _imgAction(() => api.localizeImage(props.draft.id, { source_index: idx }), '俄化完成,已进候选区')
}
function doRegen(p) {
  return _imgAction(() => api.regenImage(props.draft.id, { source_index: p.idx, role: (p && p.role) || '' }), '重做完成,已进候选区')
}
function doScene(idx) {
  return _imgAction(() => api.sceneImage(props.draft.id, { source_index: idx }), '场景图完成,已进候选区')
}
// 图集计划:槽位清单(待做/候选中/已应用),按槽生成避免重复同角度
const plan = ref([])
const planLoading = ref(false)
function planStatusText(s) { return s === 'applied' ? '✅已应用' : (s === 'candidate' ? '候选中' : '待做') }
async function loadPlan(force = false) {
  planLoading.value = true
  try {
    const r = await api.imagePlan(props.draft.id, force)
    if (r && r.ok) plan.value = r.plan || []
  } catch (err) { ElMessage.error(String((err && err.message) || err)) } finally { planLoading.value = false }
}
async function doPlanSlot(slotId) {
  await _imgAction(() => api.generatePlanSlot(props.draft.id, slotId), '已生成,进候选区')
  loadPlan()
}

// ===== 流程编排(像 n8n:依赖顺序 + 状态 + 一键自动 + 单步重跑;结果都存草稿) =====
const WF = [
  { id: 'understand', label: '看图理解(让文案/作图更准)', eta: '~40s', dep: [] },
  { id: 'category', label: '类别识别', eta: '~20s', dep: [], optional: true },
  // 文案排在特征前：特征里的「简介(Аннотация)」复用文案生成的俄语描述，文案先跑才填得上
  { id: 'copy', label: '文案 标题/简介/标签', eta: '~90s', dep: [] },
  { id: 'attrs', label: '特征值识别(按类别填)', eta: '~10s', dep: ['category'], optional: true },
  { id: 'images', label: '图集出图', eta: '~2-3min', dep: ['understand'] },
  { id: 'apply', label: '应用候选到图集', eta: '即时', dep: ['images'] },
  { id: 'rich', label: '富文本', eta: '即时', dep: ['apply'] },
  { id: 'publish', label: '发布上线', eta: '~30s', dep: ['copy', 'apply', 'rich'] },
]
const wfRunning = ref(false)
const wfStatus = reactive({})   // step_id -> 'running' | 'failed' | ''

async function runImagePlan() {
  await loadPlan(true)
  const todo = plan.value.filter((s) => s.status === 'todo').map((s) => s.slot_id)
  for (const sid of todo) {
    const r = await api.generatePlanSlot(props.draft.id, sid)
    if (r && r.draft) store.upsertDraft(r.draft)
  }
  await loadPlan()
}
const preflightDlg = ref(false)
const preflightData = ref(null)
function pfTag(sev) { return { error: '⛔', warn: '⚠', verify: '🔍' }[sev] || '✓' }
async function doPublishRaw() {
  const r = await api.publish(props.draft.id)
  if (r && r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) }
  if (!r || !r.published) throw new Error('发布未成功: ' + JSON.stringify((r && r.errors) || r || ''))
  ElMessage.success('已发布到 Ozon')
}
async function autoPublish() {   // 不拦:直接发布(问题去 Ozon 后台改)。Ozon 必填项不全时 publish 本身会返回错误
  await doPublishRaw()
}
async function openPublishCheck() {   // 手动:先弹「发布前核对」
  try { preflightData.value = await api.publishPreflight(props.draft.id); preflightDlg.value = true } catch (e) {
    ElMessage.error('核对失败: ' + ((e && e.message) || e))
  }
}
async function confirmPublish() {
  preflightDlg.value = false
  wfStatus.publish = 'running'
  try { await doPublishRaw(); wfStatus.publish = 'ok' } catch (e) {
    wfStatus.publish = 'failed'; ElMessage.error(`发布失败: ${(e && e.message) || e}`)
  }
}
const wfRun = {
  understand: () => doUnderstand(),
  category: () => doRecognizeCategory(),
  attrs: () => doAutoMapAttrs(),
  copy: async () => { await doAiGenerate(true); await applyProposal() },
  images: () => runImagePlan(),
  apply: () => doApplyCandidates(),
  rich: () => doRichContent(),
  publish: () => autoPublish(),
}
function wfDone(id) {
  const d = props.draft || {}
  const sr = d.source_raw || {}
  const typed = Object.keys(sr.image_types || {}).length > 0
  switch (id) {
    case 'understand': return !!understanding.value
    case 'category': return !!(d.category_id && d.type_id)
    // 已填特征:存在「真·类目属性」({id,values})，排除总会有的 9048/23171/85(型号名/标签/品牌)，
    // 否则光有个 9048 就被当成"已填"→ 一键时跳过 auto_map → 属性没填上就发布了。
    case 'attrs': return (Array.isArray(d.attributes) ? d.attributes : [])
      .some((a) => a && a.id != null && ![9048, 23171, 85].includes(Number(a.id))
        && Array.isArray(a.values) && a.values.length)
    case 'copy': return !!(d.ozon_title && d.description)
    case 'images': return candidates.value.length > 0 || typed
    case 'apply': return typed && candidates.value.length === 0
    case 'rich': return !!richContentJson.value
    case 'publish': return !!d.ozon_product_id || d.status === 'published'
  }
  return false
}
function wfIsDone(id) { return wfStatus[id] === 'ok' || wfDone(id) }   // 本次跑成功(ok) 或 据草稿推导已完成
function wfDepOk(s) { return (s.dep || []).every((id) => wfIsDone(id)) }
function wfStep(id) { return WF.find((s) => s.id === id) }
function wfState(s) {
  if (wfStatus[s.id] === 'running') return 'running'
  if (wfStatus[s.id] === 'failed') return 'failed'
  if (wfIsDone(s.id)) return 'done'
  return wfDepOk(s) ? 'pending' : 'wait'
}
function wfStateText(s) {
  return { running: '进行中…', failed: '失败', done: '✅完成', pending: '待运行', wait: '等依赖' }[wfState(s)]
}
async function runStep(s) {
  if (s.id === 'publish') return openPublishCheck()   // 手动发布:先过「发布前核对」
  wfStatus[s.id] = 'running'
  try { await wfRun[s.id](); wfStatus[s.id] = 'ok' } catch (e) {
    wfStatus[s.id] = 'failed'; ElMessage.error(`「${s.label}」失败: ${(e && e.message) || e}`)
  }
}
async function runAuto() {
  try {
    await ElMessageBox.confirm(
      '「一键自动」会按顺序跑:看图理解 → 类别识别 → 文案 → 特征值识别 → 图集出图 → 应用候选 → 富文本 → 发布,并**真正发布上线到 Ozon**(出图数字/文案不再人工核对)。确定?',
      '全自动到发布', { type: 'warning', confirmButtonText: '开始', cancelButtonText: '取消', dangerouslyUseHTMLString: false })
  } catch (e) { return }
  wfRunning.value = true
  try {
    for (const s of WF) {
      if (wfIsDone(s.id)) continue
      wfStatus[s.id] = 'running'
      try {
        await wfRun[s.id]()
        // 关键:每步后拉最新草稿,让下一步的 candidates/understanding/images 等计算是最新值,
        // 否则紧凑循环里响应式滞后 → 下一步读到旧状态(曾导致"候选没应用就发布")
        await store.loadDrafts()
      } catch (e) {
        wfStatus[s.id] = 'failed'
        ElMessage.error(`「${s.label}」失败,流程停在这步,可单步「重跑」继续: ${(e && e.message) || e}`)
        return
      }
      wfStatus[s.id] = 'ok'
    }
    ElMessage.success('全流程跑完 🎉')
  } finally { wfRunning.value = false }
}
async function doApplyCandidates() {
  // 不传索引 = 后端应用全部候选(权威，避免前端响应式滞后读到空候选 → 静默不应用)
  try {
    const r = await api.applyCandidates(props.draft.id)
    if (r && r.ok) { if (r.draft) { store.upsertDraft(r.draft); initFromDraft(r.draft) } ElMessage.success(`已应用 ${r.added} 张到图集`) }
    if (plan.value.length) loadPlan()   // 应用后刷新计划槽位状态(→已应用)
  } catch (err) {
    const msg = String((err && err.message) || err)
    if (msg.includes('没有候选图')) return   // 候选已空(可能此前已应用)→ 当作完成，不报错不中断
    throw err   // 真错误：抛出，让单步/一键流程显示并停下，不再静默吞掉后继续发布
  }
}
async function doDiscardCandidates() {
  try {
    const r = await api.discardCandidates(props.draft.id)
    if (r && r.ok) { if (r.draft) store.upsertDraft(r.draft); ElMessage.success('候选已清空') }
  } catch (err) { ElMessage.error(String((err && err.message) || err)) }
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

// 多图生成视频(浏览器本地 Canvas+MediaRecorder,不传服务器合成)
const slideshowDlg = ref(false)
const ssSel = ref([])            // 勾选的图下标(有序,即播放顺序)
const ssLoading = ref(false)
const ssDuration = computed(() => Math.max(8, Math.ceil(ssSel.value.length * 2.2)))
function toggleSs(i) {
  const at = ssSel.value.indexOf(i)
  if (at >= 0) ssSel.value.splice(at, 1)
  else ssSel.value.push(i)
}
async function doMakeSlideshow() {
  if (!ssSel.value.length) return
  ssLoading.value = true
  try {
    const urls = ssSel.value.map((i) => { const u = drawerImages.value[i]; return localMap.value[u] || u })
    const { blob, ext } = await makeSlideshowVideo(urls)
    const file = new File([blob], `slideshow.${ext}`, { type: blob.type })
    const r = await api.uploadMedia(props.draft.id, file, 'video')
    if (r && r.url) {
      await onVideoChange(r.url)
      ElMessage.success(`视频已生成(${ext.toUpperCase()})并上传`)
      slideshowDlg.value = false
      ssSel.value = []
    }
  } catch (err) {
    ElMessage.error(String((err && err.message) || err))
  } finally { ssLoading.value = false }
}

// 多选图 → 批量出图(白底/细节/俄化/场景/重做),逐张调现成端点 → 候选区
const batchSel = ref([])
const batchLoading = ref(false)
function toggleBatch(i) {
  const at = batchSel.value.indexOf(i)
  if (at >= 0) batchSel.value.splice(at, 1)
  else batchSel.value.push(i)
}
async function runBatch(action) {
  if (!batchSel.value.length) return
  const id = props.draft.id
  const callMap = {
    white: (i) => api.whitenMain(id, { source_index: i }),
    localize: (i) => api.localizeImage(id, { source_index: i }),
    scene: (i) => api.sceneImage(id, { source_index: i }),
    detail: (i) => api.regenImage(id, { source_index: i, role: '细节' }),
    redo: (i) => api.regenImage(id, { source_index: i }),   // 用该图自己的真实产品重做成原创图
  }
  const name = { white: '白底图', localize: '俄化', scene: '场景图', detail: '细节图', redo: '重做' }[action]
  const call = callMap[action]
  batchLoading.value = true
  let ok = 0
  try {
    for (const i of [...batchSel.value]) {
      try {
        const r = await call(i)
        if (r && r.ok) { if (r.draft) store.upsertDraft(r.draft); ok++ }
      } catch (e) { /* 单张失败不影响其余 */ }
    }
    ElMessage.success(`${name}:${ok}/${batchSel.value.length} 张已进候选区`)
    batchSel.value = []
  } finally { batchLoading.value = false }
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
    aspects.value = []
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
      aspects.value = []
      missing.value = []
      return
    }
    // 有值的排前面、没值的往下（加载时排一次，稳定排序保留原相对顺序；不在打字时实时跳）
    aspects.value = _sortByFilled(filterDetachedTextAttrs(res.aspects || []))
    required.value = _sortByFilled(filterDetachedTextAttrs(res.required || []))
    optional.value = _sortByFilled(filterDetachedTextAttrs(res.optional || []))
    missing.value = filterDetachedTextAttrs(res.missing || [])
    // 按 is_collection 归一化 attrInputs：多选要数组、单选要标量(否则 el-select 报错/回显错)
    for (const a of [...aspects.value, ...required.value, ...optional.value]) {
      const cur = attrInputs[a.id]
      if (a.is_collection) {
        if (cur != null && cur !== '' && !Array.isArray(cur)) attrInputs[a.id] = [cur]
      } else if (Array.isArray(cur)) {
        attrInputs[a.id] = cur.length ? cur[0] : ''
      }
    }
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

// 打开字典下拉时:加载全量选项(后端先查 DB 缓存,缺了拉 Ozon 回写)。已加载过则跳过。
// oversized(字典过大)→ 不预载,该控件回退「输入俄文实时搜」。
async function ensureAttrOptions(a) {
  if (!form.category_id || !form.type_id) return
  if (Number(a.dictionary_id) <= 0 || attrOptLoaded[a.id]) return
  attrLoading[a.id] = true
  try {
    const r = await api.attributeOptions(form.category_id, form.type_id, a.id, attrLanguage.value)
    if (r.oversized) {
      attrOversized[a.id] = true            // 太大:保留已种的当前值,靠实时搜
    } else {
      const opts = r.values || []
      // 合并已种的当前值(initFromDraft 种的),避免覆盖掉当前选中项的显示
      const cur = (attrOptions[a.id] || []).filter((o) => !opts.some((x) => x.id === o.id))
      attrOptions[a.id] = [...cur, ...opts]
    }
    attrOptLoaded[a.id] = true
  } catch (e) {
    /* 失败不阻断:控件仍可输入实时搜 */
  } finally {
    attrLoading[a.id] = false
  }
}

async function onAttrPick(a, val) {
  // 单选 val=id；多选 val=[id,...]。统一成 id 数组再组装上架值。
  const ids = Array.isArray(val) ? val : (val == null || val === '' ? [] : [val])
  const opts = attrOptions[a.id] || []
  const values = ids
    .map((id) => { const o = opts.find((x) => x.id === id); return o ? { dictionary_value_id: o.id, value: o.value } : null })
    .filter(Boolean)
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

// 旧的「自动填充(快)」按名硬对(autoMap)已移除——1688 中文参数名≠Ozon 俄文属性名几乎填不上，
// 由「AI 填特征」(doAiFill→aiFillAttributes)完全取代。api.autoMap 后端保留备用。

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

defineExpose({ form, imagesText, attributesText, collectPatch, save, runRequiredCheck, doTranslate, doAiGenerate, onImagesChange, onVideoChange, proposalActive, proposal, proposalAiAttrs, proposalMissingAttrs, editProposalField, deleteProposalField, editProposalAttr, deleteProposalAttr, applyProposal, discardProposal, imgGenN, imgGenLoading, imgPrompts, allImgPromptsText, detailThumbs, doImagePrompts, copyText, aiImgDlg, aiVidDlg, aiDialogImages, openAiImage, openAiVideo, onAiImageDone, onAiVideoDone, attrLanguage, showOptional })
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
.rich-actions { margin-bottom: 12px; }
.rich-empty { color: var(--c-text-3); font-size: 13px; margin-top: 8px; }
.ss-hint { color: var(--c-text-3); font-size: 12px; margin-bottom: 10px; line-height: 1.5; }
.ss-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; max-height: 360px; overflow-y: auto; }
.ss-cell { position: relative; aspect-ratio: 3/4; border: 2px solid transparent; border-radius: 8px; overflow: hidden; cursor: pointer; background: rgba(0,0,0,0.04); }
.ss-cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ss-cell.sel { border-color: var(--c-info, #3b82f6); }
.ss-num { position: absolute; left: 4px; top: 4px; min-width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 999px; background: var(--c-info, #3b82f6); color: #fff; font-size: 11px; font-weight: 700; }
.ss-foot { margin-right: auto; color: var(--c-text-3); font-size: 12px; }
.batch-card { margin-top: 8px; }
.batch-bar { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--c-text-3); }
.batch-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-top: 8px; }
.batch-cell { position: relative; aspect-ratio: 3/4; border: 2px solid transparent; border-radius: 8px; overflow: hidden; cursor: pointer; background: rgba(0,0,0,0.04); }
.batch-cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
.batch-cell.sel { border-color: var(--c-info, #3b82f6); }
.batch-num { position: absolute; left: 4px; top: 4px; min-width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 999px; background: var(--c-info, #3b82f6); color: #fff; font-size: 11px; font-weight: 700; }
.pf-banner { padding: 8px 10px; border-radius: 6px; font-size: 13px; margin-bottom: 10px; }
.pf-banner.info { background: rgba(59,130,246,0.1); color: var(--c-info, #2563eb); }
.pf-list { list-style: none; margin: 0; padding: 0; font-size: 13px; line-height: 1.7; }
.pf-list li { display: flex; gap: 8px; align-items: baseline; padding: 2px 0; }
.pf-tag { flex: none; }
.pf-error { color: var(--c-danger, #d4380d); }
.pf-warn, .pf-verify { color: var(--c-warning, #d48806); }
.pf-pass { color: var(--c-text-3); }
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
.ai-field { display: flex; flex-direction: column; gap: 5px; margin-top: 12px; }
.ai-field > label { font-size: 12px; font-weight: 600; color: var(--gp-muted); }
.ai-field .el-input, .ai-field .el-textarea { width: 100%; }
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

/* 一键上架面板 */
.smart-listing { border: 1px solid var(--c-border-soft); border-radius: 8px; padding: 10px 12px; margin: 8px 0; background: var(--c-surface-2); }
.smart-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.smart-hint { color: var(--c-text-3); font-size: 12px; }
.smart-und { margin-top: 8px; font-size: 13px; line-height: 1.7; background: var(--c-surface-1); border-radius: 6px; padding: 8px 10px; }
.smart-und-h small { color: var(--c-text-3); }
.smart-roles span { display: inline-block; margin-right: 8px; color: var(--c-text-2); }
.smart-rec { margin-top: 8px; font-size: 13px; }
.smart-pi { width: 100%; margin-top: 6px; font-size: 12px; border-collapse: collapse; }
.smart-pi td { padding: 2px 6px; border-bottom: 1px solid var(--c-border-soft); }
.smart-cands { margin-top: 8px; font-size: 13px; }
.wf-flow { margin: 10px 0; padding: 10px 12px; border: 1px solid var(--c-border-soft); border-radius: 8px; background: var(--c-surface-1); }
.wf-flow-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.wf-hint { color: var(--c-text-3); font-size: 12px; margin-right: auto; }
.wf-step { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 3px 0; }
.wf-idx { width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 999px; background: var(--c-surface-2, #eee); color: var(--c-text-2); font-size: 11px; }
.wf-dot { width: 9px; height: 9px; border-radius: 999px; background: var(--c-text-3); }
.wf-dot.running { background: var(--c-warning, #d48806); animation: wfblink 1s infinite; }
.wf-dot.failed { background: var(--c-danger, #d4380d); }
.wf-dot.done { background: var(--c-success, #389e0d); }
.wf-dot.pending { background: var(--c-info, #3b82f6); }
.wf-dot.wait { background: var(--c-text-3); opacity: 0.4; }
.wf-label { min-width: 150px; }
.wf-eta { color: var(--c-text-3); font-size: 12px; min-width: 60px; }
.wf-st { font-size: 12px; margin-right: auto; }
.wf-st.failed { color: var(--c-danger, #d4380d); }
.wf-st.done { color: var(--c-success, #389e0d); }
.wf-st.running { color: var(--c-warning, #d48806); }
@keyframes wfblink { 50% { opacity: 0.3; } }
.smart-plan { margin-top: 10px; font-size: 13px; }
.plan-st { font-size: 12px; padding: 1px 6px; border-radius: 4px; }
.plan-st.todo { color: var(--c-text-3); }
.plan-st.candidate { color: var(--c-warning, #d48806); }
.plan-st.applied { color: var(--c-success, #389e0d); }
.smart-cand-grid { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0; }
.smart-cand-grid img { height: 64px; border: 1px solid var(--c-border-soft); border-radius: 4px; }
</style>
