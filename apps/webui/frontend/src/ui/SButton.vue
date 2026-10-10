<script setup>
const props = defineProps({
  variant: { type: String, default: 'primary' },
  size: { type: String, default: 'md' },
  loading: Boolean, disabled: Boolean,
})
const emit = defineEmits(['click'])
function onClick(e) { if (props.loading || props.disabled) return; emit('click', e) }
</script>
<template>
  <button class="s-btn" :class="[`s-btn--${variant}`, `s-btn--${size}`, { 'is-disabled': disabled || loading }]"
          :disabled="disabled || loading" @click="onClick">
    <span v-if="loading" class="s-btn__spin"></span>
    <slot name="icon" /><slot />
  </button>
</template>
<style scoped>
.s-btn{display:inline-flex;align-items:center;gap:var(--sp-2);border-radius:var(--r-sm);
  font-size:var(--fs-md);font-weight:600;cursor:pointer;border:1px solid transparent;
  padding:8px 14px;transition:.15s;line-height:1}
.s-btn--sm{padding:5px 10px;font-size:var(--fs-sm)}
.s-btn--primary{background:var(--c-primary);color:#fff}
.s-btn--primary:hover{background:var(--c-primary-hover)}
.s-btn--ghost{background:#fff;color:var(--c-text-2);border-color:var(--c-border)}
.s-btn--ghost:hover{color:var(--c-primary);border-color:var(--c-primary-200)}
.s-btn--danger{background:var(--c-danger-bg);color:var(--c-danger)}
.s-btn--subtle{background:var(--c-primary-50);color:var(--c-primary)}
.s-btn.is-disabled{opacity:.55;cursor:not-allowed}
.s-btn__spin{width:12px;height:12px;border:2px solid #fff6;border-top-color:#fff;
  border-radius:50%;animation:s-spin .7s linear infinite}
@keyframes s-spin{to{transform:rotate(360deg)}}
</style>
