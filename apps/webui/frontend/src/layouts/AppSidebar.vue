<script setup>
import { useAppStore } from '../stores/app.js'
const store = useAppStore()
const nav = [
  { to: '/', label: '商品草稿', icon: '📦' },
  { to: '/analytics', label: '数据分析', icon: '📊' },
  { to: '/stores', label: '店铺管理', icon: '🏬' },
  { to: '/warehouses', label: '仓库管理', icon: '🏢' },
  { to: '/fulfillment', label: '备货发货', icon: '🚚' },
  { to: '/settings', label: '系统设置', icon: '⚙️' },
]
</script>
<template>
  <aside class="sb">
    <div class="sb__brand">上品助手 <b>Pro</b><div class="sb__store"><span class="dot"></span>{{ store.currentStoreName || 'RU-Store' }}</div></div>
    <nav class="sb__nav">
      <router-link v-for="n in nav" :key="n.to" :to="n.to" class="sb__item" active-class="is-active" :exact="n.to==='/'">
        <span class="sb__ico">{{ n.icon }}</span>{{ n.label }}
      </router-link>
    </nav>
    <div class="sb__foot"><div>Version 2026.06</div><div class="sb__mode">本地数据 · 凭证不出本机</div></div>
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
