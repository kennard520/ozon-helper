<script setup>
import { computed } from 'vue'
import SAlert from '../../ui/SAlert.vue'

const props = defineProps({
  grandTotal: { type: Object, default: null },
  degraded: { type: Boolean, default: false },
})

function fmtNum(v) {
  if (v == null) return '0'
  if (v >= 10000) return (v / 10000).toFixed(1) + '万'
  return Number(v).toLocaleString('zh-CN')
}

// 会话率 = 访问 / 曝光
const sessionRate = computed(() => {
  const gt = props.grandTotal
  if (!gt || !gt.exposure) return 0
  return Math.round((gt.sessions / gt.exposure) * 1000) / 10
})

// 核心诊断标题（最突出问题）
const diagTitle = computed(() => {
  const gt = props.grandTotal
  if (!gt) return ''
  if (gt.sku_count > 0 && gt.sku_with_traffic === 0) return '全店零曝光·请检查上架/广告状态'
  if (gt.ordered_units === 0 && gt.sessions > 0) return '有访问·零下单：转化链路断点'
  if (gt.conv_cart_pct != null && gt.conv_cart_pct < 2 && gt.sessions > 0) return `加购转化偏低（${gt.conv_cart_pct}%）`
  if (gt.sku_with_traffic < gt.sku_count) return `${gt.sku_count - gt.sku_with_traffic} 个商品无曝光`
  return ''
})

const showCore = computed(() => !!diagTitle.value)
</script>
<template>
  <div>
    <!-- 降级单独提示 -->
    <SAlert v-if="degraded" variant="warn" title="数据降级" style="margin-bottom:8px">
      当前账号无 Premium，曝光/访问数据不可用，仅展示下单与收入。
    </SAlert>

    <!-- 核心诊断卡 -->
    <div v-if="showCore && grandTotal" class="db">
      <div class="db__icon">🚨</div>
      <div class="db__body">
        <div class="db__title">{{ diagTitle }}</div>
        <div class="db__metrics">
          曝光 <b>{{ fmtNum(grandTotal.exposure) }}</b>
          · 访问 <b>{{ fmtNum(grandTotal.sessions) }}</b>
          · 会话率 <b>{{ sessionRate }}%</b>
          · 加购 <b>{{ fmtNum(grandTotal.cart) }}</b>
          · 下单 <b>{{ fmtNum(grandTotal.ordered_units) }}</b>
        </div>
        <div class="db__checklist">
          排查清单：价格 / 主图 / 详情 / 评价 / 运费
        </div>
        <div class="db__cta">
          → 切到「搜索词洞察」tab 看引流词是否精准
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.db { display: flex; gap: var(--sp-3); align-items: flex-start; background: var(--c-danger-bg); border: 1px solid #fecaca; border-radius: var(--r-md); padding: var(--sp-4); }
.db__icon { font-size: 22px; line-height: 1.2; }
.db__body { flex: 1; min-width: 0; }
.db__title { font-weight: 700; color: var(--c-text); font-size: var(--fs-lg); }
.db__metrics { font-size: var(--fs-sm); color: var(--c-text-2); margin-top: 6px; }
.db__metrics b { color: var(--c-danger); font-weight: 700; }
.db__checklist { font-size: var(--fs-sm); color: var(--c-text-2); margin-top: 6px; }
.db__cta { font-size: var(--fs-sm); color: var(--c-primary); font-weight: 600; margin-top: 6px; }
</style>
