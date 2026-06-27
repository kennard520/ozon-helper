<script setup>
import { ref, computed } from 'vue'
import SBadge from '../../ui/SBadge.vue'
import SButton from '../../ui/SButton.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
})
const emit = defineEmits(['open-draft'])

const onlyProblems = ref(false)

const displayRows = computed(() => {
  if (!onlyProblems.value) return props.rows
  return props.rows.filter(r => r.diagnostics && r.diagnostics.length > 0)
})

function badgeVariant(tag) {
  if (tag === '缺货') return 'danger'
  if (tag === '0曝光') return 'neutral'
  if (tag.includes('高曝光')) return 'warn'
  if (tag.includes('加购')) return 'info'
  return 'neutral'
}

function fmt(v) {
  if (v == null) return '—'
  return v
}
</script>
<template>
  <div class="pt">
    <div class="pt__toolbar">
      <label class="pt__toggle">
        <input type="checkbox" v-model="onlyProblems" />
        仅看问题商品
      </label>
      <span class="pt__count">{{ displayRows.length }} / {{ rows.length }} 商品</span>
    </div>
    <div class="pt__wrap">
      <table class="pt__table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>商品名</th>
            <th>价格</th>
            <th>库存</th>
            <th>曝光</th>
            <th>访问</th>
            <th>加购</th>
            <th>下单</th>
            <th>转化率</th>
            <th>收入</th>
            <th>诊断</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in displayRows" :key="row.sku" class="pt__row" @click="emit('open-draft', row)">
            <td class="pt__sku">{{ row.sku }}</td>
            <td class="pt__title">{{ row.title || '—' }}</td>
            <td>{{ fmt(row.price) }}</td>
            <td :class="{ 'pt__val--danger': row.stock === 0 }">{{ fmt(row.stock) }}</td>
            <td>{{ fmt(row.exposure) }}</td>
            <td>{{ fmt(row.sessions) }}</td>
            <td>{{ fmt(row.cart) }}</td>
            <td>{{ fmt(row.ordered_units) }}</td>
            <td>{{ row.conv_cart_pct != null ? row.conv_cart_pct + '%' : '—' }}</td>
            <td>{{ fmt(row.revenue) }}</td>
            <td class="pt__tags">
              <SBadge
                v-for="tag in (row.diagnostics || [])"
                :key="tag"
                :variant="badgeVariant(tag)"
                style="margin-right:4px"
              >{{ tag }}</SBadge>
            </td>
          </tr>
          <tr v-if="displayRows.length === 0">
            <td colspan="11" class="pt__empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
<style scoped>
.pt { }
.pt__toolbar { display: flex; align-items: center; gap: var(--sp-4); padding: var(--sp-3) 0; font-size: var(--fs-sm); }
.pt__toggle { display: flex; align-items: center; gap: 6px; cursor: pointer; color: var(--c-text-2); }
.pt__count { color: var(--c-text-4); margin-left: auto; }
.pt__wrap { overflow-x: auto; }
.pt__table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.pt__table th { background: var(--c-bg); color: var(--c-text-3); font-weight: 600; padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--c-border); white-space: nowrap; }
.pt__table td { padding: 8px 10px; border-bottom: 1px solid var(--c-border-light, var(--c-border)); color: var(--c-text-2); }
.pt__row { cursor: pointer; }
.pt__row:hover td { background: var(--c-bg); }
.pt__sku { color: var(--c-text-4); font-size: var(--fs-xs); }
.pt__title { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-text); }
.pt__val--danger { color: var(--c-danger); }
.pt__tags { white-space: nowrap; }
.pt__empty { text-align: center; color: var(--c-text-4); padding: 24px; }
</style>
