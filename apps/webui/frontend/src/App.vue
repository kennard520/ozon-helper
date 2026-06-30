<script setup>
import { onMounted, onUnmounted } from 'vue'
import { consumeUrlToken } from './auth.js'
consumeUrlToken()
function onAuthLogout() { location.replace('#/login'); location.reload() }
onMounted(() => window.addEventListener('auth:logout', onAuthLogout))
onUnmounted(() => window.removeEventListener('auth:logout', onAuthLogout))
</script>
<template><router-view /></template>
