<script setup>
import SAlert from '../../ui/SAlert.vue'

const props = defineProps({
  grandTotal: { type: Object, default: null },
  degraded: { type: Boolean, default: false },
})

function insight(gt) {
  if (!gt) return ''
  const parts = []
  if (gt.sku_count > 0 && gt.sku_with_traffic === 0) parts.push('全部商品无曝光，请检查上架状态')
  else if (gt.sku_with_traffic < gt.sku_count) parts.push(`${gt.sku_count - gt.sku_with_traffic} 个商品无曝光`)
  if (gt.ordered_units === 0 && gt.sessions > 0) parts.push('有访问但零下单，建议优化价格或详情')
  else if (gt.conv_cart_pct != null && gt.conv_cart_pct < 2) parts.push(`转化率 ${gt.conv_cart_pct}% 偏低`)
  return parts.join('；')
}
</script>
<template>
  <div>
    <SAlert v-if="degraded" variant="warn" title="数据降级" style="margin-bottom:8px">
      当前账号无 Premium，曝光/访问数据不可用，仅展示下单与收入。
    </SAlert>
    <SAlert v-if="grandTotal && insight(grandTotal)" variant="warn" :title="insight(grandTotal)" />
  </div>
</template>
