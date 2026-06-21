<template>
  <el-dialog
    :model-value="modelValue"
    title="realFBS 智能定价"
    width="960px"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <div class="pricing-body">
      <!-- 左：参数 -->
      <div class="pricing-inputs">
        <el-form label-width="120px" label-position="left">
          <el-form-item label="佣金类目">
            <el-select
              v-model="selectedIdx"
              filterable
              placeholder="选佣金类目"
              @change="recompute"
            >
              <el-option
                v-for="(c, i) in categories"
                :key="i"
                :label="catLabel(c)"
                :value="i"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="目标毛利%">
            <el-input v-model="inputs.marginTargetPct" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="物流策略">
            <el-select v-model="inputs.strategy" @change="recompute">
              <el-option label="平衡" value="balanced" />
              <el-option label="最低运费" value="cost" />
              <el-option label="最快时效" value="speed" />
              <el-option label="评分优先" value="rating" />
            </el-select>
          </el-form-item>
          <el-form-item label="汇率 RUB→CNY">
            <el-input v-model="inputs.rubCny" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="支付费%">
            <el-input v-model="inputs.paymentPct" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="广告%">
            <el-input v-model="inputs.adPct" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="退货预留%">
            <el-input v-model="inputs.returnReservePct" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="损耗预留%">
            <el-input v-model="inputs.lossReservePct" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="包装(¥)">
            <el-input v-model="inputs.packingCny" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="国内运费(¥)">
            <el-input v-model="inputs.domesticShipCny" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="其他固定(¥)">
            <el-input v-model="inputs.otherFixedCny" type="number" @input="recompute" />
          </el-form-item>
          <el-form-item label="限制">
            <el-checkbox v-model="inputs.hasBattery" @change="recompute">带电池</el-checkbox>
            <el-checkbox v-model="inputs.isLiquid" @change="recompute">含液体</el-checkbox>
          </el-form-item>
        </el-form>
      </div>

      <!-- 右：结果 -->
      <div class="pricing-result">
        <div v-if="!result || !result.bestRoute" class="pr-bad">
          没有匹配的 realFBS 线路：检查重量/尺寸/货值/电池液体限制，或换物流策略。
        </div>
        <template v-else>
          <div class="pr-prices">
            <div class="pr-price"><span>销售价</span><strong>{{ Math.round(result.targetRub) }} ₽</strong></div>
            <div class="pr-price line"><span>划线价</span><strong>{{ Math.round(result.linePriceRub) }} ₽</strong></div>
          </div>
          <div class="pr-row"><span>推荐售价(¥)</span><b>{{ money(result.targetCny) }}</b></div>
          <div class="pr-row"><span>保本价</span>{{ Math.round(result.breakevenCny / (Number(inputs.rubCny) || DEFAULTS.rubCny)) }} ₽ · {{ money(result.breakevenCny) }}</div>
          <div class="pr-row"><span>利润</span>
            <b :class="result.profitCny >= 0 ? 'good' : 'bad'">{{ money(result.profitCny) }}</b>
            · 毛利 {{ pctTxt(result.margin) }}
          </div>
          <div class="pr-row"><span>佣金</span>{{ pctTxt(result.commission) }}（{{ tierLabel(result.tierIndex) }} ₽档）</div>
          <div class="pr-row"><span>计费重</span>{{ Math.round(result.chargeable.billable) }}g</div>
          <div class="pr-route">
            <div class="pr-route-head">推荐线路</div>
            <strong>{{ result.bestRoute.provider }} · {{ result.bestRoute.serviceLevel }}</strong>
            <div class="muted">
              {{ result.bestRoute.deliveryMethod }} · 时效 {{ result.bestRoute.etaDays || '-' }}
              · 运费 {{ money(result.bestRoute.costCny) }}
              · 可用线路 {{ result.availableRoutes.length }}/{{ routes.length }}
            </div>
          </div>
          <div
            v-for="(d, i) in (result.diagnostics || [])"
            :key="i"
            class="pr-diag"
            :class="d.level"
          >{{ d.text }}</div>
        </template>
      </div>
    </div>

    <!-- 全宽区：成本构成 / 线路排行 / 被拦原因 -->
    <template v-if="result && result.bestRoute">
      <div class="pr-section">
        <div class="pr-section-title">推荐售价成本构成</div>
        <div class="pr-bar">
          <span
            v-for="p in (result.costBreakdown || [])"
            :key="p.key"
            class="pr-bar-seg"
            :style="{ width: (p.pctOfPositive * 100) + '%', background: p.color }"
            :title="`${p.label} ${money(p.value)}`"
          ></span>
        </div>
        <div class="pr-legend">
          <span v-for="p in (result.costBreakdown || [])" :key="p.key" class="pr-legend-item">
            <i :style="{ background: p.color }"></i>{{ p.label }} {{ money(p.value) }}（{{ pctTxt(p.pctOfPrice) }}）
          </span>
        </div>
      </div>

      <div class="pr-section">
        <div class="pr-section-title">可用 realFBS 线路排行（{{ result.availableRoutes.length }}/{{ routes.length }}）</div>
        <el-table :data="result.availableRoutes.slice(0, 8)" size="small" border>
          <el-table-column label="线路" min-width="120">
            <template #default="{ row }">{{ row.provider }}</template>
          </el-table-column>
          <el-table-column label="等级" min-width="110">
            <template #default="{ row }">{{ row.serviceLevel || '-' }}</template>
          </el-table-column>
          <el-table-column label="评分" width="70" align="center">
            <template #default="{ row }">{{ row.ozonRating || '-' }}</template>
          </el-table-column>
          <el-table-column label="时效" width="90" align="center">
            <template #default="{ row }">{{ row.etaDays || '-' }}</template>
          </el-table-column>
          <el-table-column label="运费" width="90" align="right">
            <template #default="{ row }">{{ money(row.costCny) }}</template>
          </el-table-column>
          <el-table-column label="佣金" width="80" align="center">
            <template #default="{ row }">{{ pctTxt(row.commission) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="blockedRoutes.length" class="pr-section">
        <div class="pr-section-title">被拦线路 · 为什么不能走（{{ blockedRoutes.length }}）</div>
        <div v-for="(b, i) in blockedRoutes.slice(0, 8)" :key="i" class="pr-blocked-row">
          <b>{{ b.provider }}</b><span v-if="b.serviceLevel"> · {{ b.serviceLevel }}</span>
          <span class="pr-blocked-reason">{{ b.reason }}</span>
        </div>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!result || !result.bestRoute" @click="apply">应用到草稿</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { OZON_REALFBS_DATA } from '../utils/pricingData.js'
import { solvePrice, routeStatus } from '../utils/pricing.js'
import { api } from '../api.js'

// 把英文拦截原因翻成中文（routeStatus.reasons 是英文）
function zhReason(r) {
  const s = String(r || '')
  if (s.includes('weight')) return '计费重超出该线路范围'
  if (s.includes('RUB price')) return '售价不在该线路货值区间'
  if (s.includes('battery')) return '该线路禁带电池'
  if (s.includes('liquid')) return '该线路禁含液体'
  if (s.includes('dimensions')) return '尺寸超过该线路限制'
  if (s.includes('rate')) return '运费规则无法解析'
  return s || '不满足该线路条件'
}

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  draft: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue', 'apply'])

const categories = OZON_REALFBS_DATA.categories
// 运费路线：默认用内置静态做兜底；开窗时从后端可维护表拉取覆盖（见下方 watch）
const routes = ref(OZON_REALFBS_DATA.routes)

// 与 static/pricing.js readInput() / DEFAULTS 一致的默认值
const DEFAULTS = {
  marginTargetPct: 30,
  rubCny: 0.0927,
  packingCny: 3,
  domesticShipCny: 0,
  otherFixedCny: 0,
  paymentPct: 0.4,
  adPct: 0,
  returnReservePct: 3,
  lossReservePct: 2,
  strategy: 'balanced',
  hasBattery: false,
  isLiquid: false,
}

const inputs = reactive({ ...DEFAULTS })
const result = ref(null)

// 被拦线路：在推荐售价下用 routeStatus 逐条判定，列出"不能走"的线路 + 原因
const blockedRoutes = computed(() => {
  const r = result.value
  if (!r || !r.bestRoute) return []
  const input = buildInput()
  const priceRub = r.targetRub || 0
  const okKeys = new Set((r.availableRoutes || []).map((x) => `${x.provider}|${x.serviceLevel}`))
  const out = []
  for (const route of routes.value) {
    if (okKeys.has(`${route.provider}|${route.serviceLevel}`)) continue
    const st = routeStatus(route, input, priceRub)
    if (!st.ok) out.push({ provider: route.provider, serviceLevel: route.serviceLevel, reason: zhReason(st.reasons[0]) })
  }
  return out
})

// 默认选中绿区类目 Decor, Cleaning & Storage，否则第一个
function defaultIdx() {
  const i = categories.findIndex((c) => c.subEn === 'Decor, Cleaning & Storage')
  return i >= 0 ? i : 0
}
const selectedIdx = ref(defaultIdx())

function catLabel(c) {
  const lo = (c.rfbs[0] * 100).toFixed(0)
  const hi = (c.rfbs[c.rfbs.length - 1] * 100).toFixed(0)
  return `${c.subZh || c.subEn}（${c.parentZh || c.parentEn} · 佣金 ${lo}%~${hi}%）`
}
function findIdx(parentEn, subEn) {
  return categories.findIndex((c) => c.parentEn === parentEn && c.subEn === subEn)
}

// 无保存映射时，按草稿的 Ozon 中文类目路径匹配佣金类目（parentZh/subZh），
// 比硬默认"装饰/清洁/储物"贴谱（如 麦克风→电子产品）。匹配不到才退默认。
async function autoMatchCommission(cat, type) {
  try {
    const r = await api.categoryResolve(cat, type)
    const path = String((r && r.leaf && r.leaf.path) || '')
    if (!path) return
    const segs = path.split('/').map((s) => s.trim()).filter(Boolean)
    const top = segs[0] || ''
    const hit = (a, b) => a && b && (a === b || a.includes(b) || b.includes(a))
    // 1) 顶级类目匹配 parentZh 且某段匹配 subZh（最精准）
    let i = categories.findIndex((c) => hit(c.parentZh, top) && segs.some((s) => hit(c.subZh, s)))
    // 2) 只顶级类目匹配 parentZh
    if (i < 0) i = categories.findIndex((c) => hit(c.parentZh, top))
    // 3) 任意路径段匹配 parentZh
    if (i < 0) i = categories.findIndex((c) => segs.some((s) => hit(c.parentZh, s)))
    if (i >= 0) selectedIdx.value = i
  } catch { /* 无 resolve / 未 mock，忽略 */ }
}

const money = (v, c = '¥', d = 2) => (Number.isFinite(v) ? `${c}${v.toFixed(d)}` : '-')
const pctTxt = (v) => (Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '-')
const tierLabel = (i) => ['≤1500', '1500-5000', '>5000'][i] ?? '-'

function buildInput() {
  const d = props.draft || {}
  return {
    costCny: Number(d.cost_cny) || 0,
    weightG: Number(d.weight_g) || 0,
    lengthCm: Number(d.length_mm) || 0,   // length_mm 列实存厘米(历史名)
    widthCm: Number(d.width_mm) || 0,
    heightCm: Number(d.height_mm) || 0,
    marginTargetPct: Number(inputs.marginTargetPct) || 0,
    adPct: Number(inputs.adPct) || 0,
    strategy: inputs.strategy,
    rubCny: Number(inputs.rubCny) || DEFAULTS.rubCny,
    paymentPct: Number(inputs.paymentPct) || 0,
    returnReservePct: Number(inputs.returnReservePct) || 0,
    lossReservePct: Number(inputs.lossReservePct) || 0,
    packingCny: Number(inputs.packingCny) || 0,
    domesticShipCny: Number(inputs.domesticShipCny) || 0,
    otherFixedCny: Number(inputs.otherFixedCny) || 0,
    hasBattery: !!inputs.hasBattery,
    isLiquid: !!inputs.isLiquid,
  }
}

function recompute() {
  const cat = categories[selectedIdx.value] || categories[0]
  result.value = solvePrice(buildInput(), routes.value, cat)
}

async function apply() {
  if (!result.value || !result.value.bestRoute) return
  const cat = categories[selectedIdx.value]
  const r = result.value
  // 内部 price 统一存 CNY 人民币（弹窗里的 ₽ 仅作俄区买家视角展示）
  const salePrice = String(Math.round(r.targetCny))
  const linePrice = String(Math.round(r.linePriceCny))
  const snapshot = {
    marginTargetPct: Number(inputs.marginTargetPct) || 0,
    adPct: Number(inputs.adPct) || 0,
    paymentPct: Number(inputs.paymentPct) || 0,
    returnReservePct: Number(inputs.returnReservePct) || 0,
    lossReservePct: Number(inputs.lossReservePct) || 0,
    packingCny: Number(inputs.packingCny) || 0,
    domesticShipCny: Number(inputs.domesticShipCny) || 0,
    otherFixedCny: Number(inputs.otherFixedCny) || 0,
    hasBattery: !!inputs.hasBattery,
    isLiquid: !!inputs.isLiquid,
    strategy: inputs.strategy,
    commissionParentEn: cat.parentEn,
    commissionSubEn: cat.subEn,
    commissionRfbs: cat.rfbs,
    rubCny: Number(inputs.rubCny) || DEFAULTS.rubCny,
    rubCnyAt: new Date().toISOString(),
    result: {
      targetRub: Math.round(r.targetRub),
      linePriceRub: Math.round(r.linePriceRub),
      targetCny: r.targetCny,
      profitCny: r.profitCny,
      margin: r.margin,
      tierIndex: r.tierIndex,
      commission: r.commission,
      bestRoute: {
        provider: r.bestRoute.provider,
        serviceLevel: r.bestRoute.serviceLevel,
        deliveryMethod: r.bestRoute.deliveryMethod,
        etaDays: r.bestRoute.etaDays,
        costCny: r.bestRoute.costCny,
      },
    },
    computedAt: new Date().toISOString(),
  }
  emit('apply', { price: salePrice, old_price: linePrice, pricing: snapshot })
  try {
    await api.saveCommissionMap({
      cat: props.draft.category_id,
      type: props.draft.type_id,
      parent_en: cat.parentEn,
      sub_en: cat.subEn,
      rfbs: cat.rfbs,
    })
    await api.saveSettings({ rub_cny: Number(inputs.rubCny) || DEFAULTS.rubCny })
  } catch { /* 持久化失败不阻断 */ }
  emit('update:modelValue', false)
}

// 打开时回填参数与佣金类目
function restoreFromSnapshot(p) {
  inputs.marginTargetPct = p.marginTargetPct ?? DEFAULTS.marginTargetPct
  inputs.adPct = p.adPct ?? DEFAULTS.adPct
  inputs.strategy = p.strategy || DEFAULTS.strategy
  inputs.rubCny = p.rubCny ?? DEFAULTS.rubCny
  inputs.paymentPct = p.paymentPct ?? DEFAULTS.paymentPct
  inputs.returnReservePct = p.returnReservePct ?? DEFAULTS.returnReservePct
  inputs.lossReservePct = p.lossReservePct ?? DEFAULTS.lossReservePct
  inputs.packingCny = p.packingCny ?? DEFAULTS.packingCny
  inputs.domesticShipCny = p.domesticShipCny ?? DEFAULTS.domesticShipCny
  inputs.otherFixedCny = p.otherFixedCny ?? DEFAULTS.otherFixedCny
  inputs.hasBattery = !!p.hasBattery
  inputs.isLiquid = !!p.isLiquid
  if (p.commissionSubEn) {
    const i = findIdx(p.commissionParentEn, p.commissionSubEn)
    if (i >= 0) selectedIdx.value = i
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    // 运费路线优先从后端表拉（可 CSV 维护）；拉不到/空则用内置静态兜底
    try {
      const rr = await api.realfbsRoutes()
      if (rr && Array.isArray(rr.routes) && rr.routes.length) routes.value = rr.routes
    } catch { /* 用静态兜底 */ }
    const d = props.draft || {}
    if (d.pricing && d.pricing.commissionSubEn) {
      restoreFromSnapshot(d.pricing)
    } else if (d.category_id && d.type_id) {
      let matched = false
      try {
        const m = await api.getCommissionMap(d.category_id, d.type_id)
        if (m && m.sub_en) {
          const i = findIdx(m.parent_en, m.sub_en)
          if (i >= 0) { selectedIdx.value = i; matched = true }
        }
      } catch { /* 无映射或未 mock，忽略 */ }
      if (!matched) await autoMatchCommission(d.category_id, d.type_id)
    }
    recompute()
  },
)

defineExpose({ recompute, apply, result, inputs })
</script>

<style scoped>
.pricing-body { display: flex; gap: 20px; }
.pricing-inputs { flex: 1; }
.pricing-result { flex: 1; }
.pr-bad { color: var(--c-danger); padding: 12px; }
.pr-prices { display: flex; gap: 24px; margin-bottom: 12px; }
.pr-price span { display: block; font-size: 12px; color: var(--c-text-3); }
.pr-price strong { font-size: 22px; }
.pr-price.line strong { color: var(--c-text-3); text-decoration: line-through; }
.pr-row { padding: 4px 0; }
.pr-row .good { color: var(--c-success); }
.pr-row .bad { color: var(--c-danger); }
.pr-route { margin-top: 12px; padding: 10px; background: rgba(0,0,0,0.03); border-radius: 6px; }
.pr-route-head { font-size: 12px; color: var(--c-text-3); margin-bottom: 4px; }
.muted { color: var(--c-text-3); font-size: 12px; margin-top: 4px; }
.pr-diag { margin-top: 6px; font-size: 13px; padding: 4px 8px; border-radius: 4px; }
.pr-diag.warn { background: rgba(245,158,11,0.12); color: var(--c-warning); }
.pr-diag.bad { background: rgba(239,68,68,0.12); color: var(--c-danger); }
.pr-diag.info { background: rgba(59,130,246,0.1); color: var(--c-info); }
.pr-diag.good { background: rgba(16,185,129,0.1); color: var(--c-success); }

/* 全宽区：成本构成 / 线路排行 / 被拦原因 */
.pr-section { margin-top: 18px; }
.pr-section-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; color: var(--c-text); }
.pr-bar {
  display: flex; width: 100%; height: 16px; border-radius: var(--r-pill);
  overflow: hidden; background: var(--c-surface-2);
}
.pr-bar-seg { height: 100%; }
.pr-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-top: 10px; }
.pr-legend-item { display: inline-flex; align-items: center; font-size: 12px; color: var(--c-text-2); }
.pr-legend-item i { width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; display: inline-block; }
.pr-blocked-row { font-size: 13px; padding: 4px 0; border-bottom: 1px solid var(--c-border-soft); }
.pr-blocked-reason { color: var(--c-danger); margin-left: 8px; }
</style>
