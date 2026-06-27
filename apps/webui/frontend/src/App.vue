<script setup>
import { onMounted, onUnmounted } from 'vue'
import { setAuth } from './auth.js'
function consumeUrlToken() {
  try {
    const sp = new URLSearchParams(location.search)
    const t = sp.get('token')
    if (t) { setAuth(t, null); sp.delete('token')
      const qs = sp.toString(); history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash) }
  } catch (e) { /* ignore */ }
}
consumeUrlToken()
function onAuthLogout() { location.replace('#/login'); location.reload() }
onMounted(() => window.addEventListener('auth:logout', onAuthLogout))
onUnmounted(() => window.removeEventListener('auth:logout', onAuthLogout))
</script>
<template><router-view /></template>
