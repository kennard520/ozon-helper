<script setup>
import { computed } from 'vue'
import { allowedInLite } from '../local-lite.js'
import { useAppStore } from '../stores/app.js'
const store = useAppStore()
const nav = [
  { to: '/', label: '商品工作台', icon: '📦' },
  { to: '/analytics', label: '数据分析', icon: '📊' },
  { to: '/stores', label: '店铺管理', icon: '🏬' },
  { to: '/warehouses', label: '仓库管理', icon: '🏢' },
  { to: '/fulfillment', label: '备货发货', icon: '🚚' },
  { to: '/settings', label: '系统设置', icon: '⚙️' },
]
const visibleNav = computed(() => nav.filter(n => !store.localLite || allowedInLite(n.to)))
const groups = computed(() => [
  { name: '经营', items: visibleNav.value.filter(n => ['/', '/analytics', '/campaigns'].includes(n.to)) },
  { name: '履约', items: visibleNav.value.filter(n => ['/warehouses', '/fulfillment'].includes(n.to)) },
  { name: '配置', items: visibleNav.value.filter(n => ['/stores', '/settings'].includes(n.to)) },
].filter(g => g.items.length))
const icons = {
  '/': 'M3 3h7v9H3z M14 3h7v5h-7z M3 16h7v5H3z M14 12h7v9h-7z',
  '/analytics': 'M6 20V14 M12 20V10 M18 20V4',
  '/campaigns': 'M3 11L21 6v12L3 14z M7 15v6h4l-1-5',
  '/stores': 'M3 7l3-4h12l3 4 M3 7h18v4H3z M5 11v10h14V11 M10 21v-6h4v6',
  '/warehouses': 'M3 9l9-6 9 6v12H3z M7 13h10 M7 17h10',
  '/fulfillment': 'M3 5h11v13H3z M14 10h4l3 4v4h-7 M5 18v3h3v-3 M16 18v3h3v-3',
  '/settings': 'M9 3h6l1 4 4 2v6l-4 2-1 4H9l-1-4-4-2V9l4-2z M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
}
</script>
<template>
  <aside class="sb">
    <div class="sb__brand"><span class="sb__logo">O</span><span class="sb__name">Ozon Helper <b>{{ store.localLite ? '本地版' : 'Pro' }}</b></span></div>
    <nav class="sb__nav">
      <div v-for="group in groups" :key="group.name" class="sb__section">
        <div class="sb__section-label">{{ group.name }}</div>
        <router-link v-for="n in group.items" :key="n.to" :to="n.to" :title="n.label" class="sb__item" active-class="is-active" :exact="n.to==='/'">
          <svg class="sb__ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path :d="icons[n.to]" /></svg>
          <span class="sb__label">{{ n.label }}</span>
        </router-link>
      </div>
    </nav>
    <router-link to="/stores" class="sb__foot" title="店铺管理"><span class="sb__store-icon">▣</span><div class="sb__store-info"><div>{{ store.currentStoreName || '尚未配置店铺' }}</div><div class="sb__mode">{{ store.currentStore ? '当前店铺' : '添加店铺后开始发布' }}</div></div></router-link>
  </aside>
</template>
<style scoped>
.sb{display:flex;flex-direction:column;height:100%;background:var(--c-bg-2);border-right:1px solid var(--c-border);padding:var(--sp-4) var(--sp-3)}
.sb__brand{font-size:var(--fs-lg);font-weight:700;color:var(--c-primary);padding:0 var(--sp-3) var(--sp-3)}
.sb__store{font-size:var(--fs-xs);color:var(--c-text-3);font-weight:400;margin-top:6px;display:flex;align-items:center;gap:6px}
.sb__store .dot{width:7px;height:7px;border-radius:50%;background:var(--c-success)}
.sb__nav{display:flex;flex-direction:column;gap:2px;margin-top:var(--sp-3)}
.sb__item{display:flex;align-items:center;gap:var(--sp-3);padding:10px var(--sp-3);border-radius:var(--r-md);
  color:var(--c-text-2);text-decoration:none;font-size:var(--fs-md)}
.sb__item:hover{background:var(--c-primary-50)}
.sb__item.is-active{background:var(--c-primary-100);color:var(--c-primary);font-weight:600}
.sb__foot{margin-top:auto;padding:var(--sp-3);font-size:var(--fs-xs);color:var(--c-text-4)}
.sb__mode{font-family:monospace;margin-top:2px}
</style>
