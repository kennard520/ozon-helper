<template>
  <div class="vcp">
    <!-- 头部 -->
    <div class="vcp-header">
      <span class="vcp-header__title">
        变体 {{ wb.variantCount }} 个
        <span class="vcp-header__sel">· 已选 {{ wb.selectedVariantIds.size }}</span>
      </span>
      <SButton variant="ghost" size="sm" disabled>+ 新增</SButton>
    </div>

    <!-- 操作行 -->
    <div class="vcp-tools">
      <SButton variant="ghost" size="sm" @click="wb.selectAll()">全选</SButton>
      <SButton variant="ghost" size="sm" @click="wb.invertSelection()">反选</SButton>
      <SButton variant="ghost" size="sm" @click="wb.clearSelection()">清空</SButton>
      <ElInput v-model="q" size="small" clearable placeholder="搜索变体…" class="vcp-tools__search" />
    </div>

    <!-- 卡网格 -->
    <div class="vcp-cards">
      <div v-if="!shown.length" class="vcp-cards__empty">暂无变体</div>
      <div
        v-for="v in shown"
        :key="v.id"
        class="vcard"
        :class="{ 'is-current': v.id === wb.currentVariantId }"
        @click="wb.setCurrentVariant(v.id)"
      >
        <!-- 多选 -->
        <ElCheckbox
          class="vcard__check"
          :model-value="wb.selectedVariantIds.has(v.id)"
          @click.stop
          @change="wb.toggleVariant(v.id)"
        />

        <!-- 缩略图 -->
        <div class="vcard__thumb">
          <img v-if="v.image" :src="v.image" />
          <span v-else class="vcard__noimg">无图</span>
        </div>

        <!-- 正文 -->
        <div class="vcard__body">
          <!-- 颜色芯片 + spec -->
          <div class="vcard__spec-row">
            <span class="vcard__color-dot" />
            <span class="vcard__spec" :title="v.spec">{{ v.spec || '—' }}</span>
          </div>
          <!-- 价 + 状态 -->
          <div class="vcard__foot">
            <span class="vcard__price">{{ v.price != null ? v.price + ' ₽' : '—' }}</span>
            <SBadge :variant="statusVariant(v.status)">{{ statusLabel(v.status) }}</SBadge>
          </div>
          <!-- N/7 进度 -->
          <div class="vcard__prog">
            <div class="vcard__prog-bar"><div class="vcard__prog-fill" :style="{ width: ((v.done || 0) / 7 * 100) + '%' }"></div></div>
            <span class="vcard__prog-txt">{{ v.done || 0 }}/7</span>
          </div>
        </div>

        <!-- × 删除 -->
        <button class="vcard__del" title="删除" @click.stop="onDelete(v)">×</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElInput, ElCheckbox, ElMessageBox } from 'element-plus'
import { SButton, SBadge } from '../../ui/index.js'
import { useWorkbenchStore } from '../../stores/workbench.js'
import { api } from '../../api.js'

const wb = useWorkbenchStore()
const emit = defineEmits(['variant-deleted'])

const q = ref('')
const shown = computed(() =>
  wb.variants.filter(v => !q.value || String(v.spec || '').includes(q.value))
)

function statusLabel(s) {
  return { ready: '待发布', published: '已发布', failed: '失败', invalid: '待完善' }[s] || s || '—'
}
function statusVariant(s) {
  if (s === 'ready' || s === 'published') return 'success'
  if (s === 'failed') return 'danger'
  return 'neutral'
}

async function onDelete(v) {
  try {
    await ElMessageBox.confirm('删除该变体草稿?', '删除', { type: 'warning' })
    await api.deleteDraft(v.id)
    await wb.reload()
    emit('variant-deleted', v.id)
  } catch {
    // 取消忽略
  }
}
</script>

<style scoped>
.vcp {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 头部 */
.vcp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.vcp-header__title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--c-text-1);
}
.vcp-header__sel {
  font-weight: 400;
  color: var(--c-text-3);
  font-size: var(--fs-sm);
}

/* 操作行 */
.vcp-tools {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.vcp-tools__search {
  flex: 1;
  min-width: 0;
}

/* 卡网格 */
.vcp-cards {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-2);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.vcp-cards__empty {
  color: var(--c-text-4);
  text-align: center;
  padding: 32px 0;
  font-size: var(--fs-sm);
}

/* 变体卡 */
.vcard {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: all 0.15s;
  background: #fff;
}
.vcard:hover {
  background: var(--c-bg-2);
  border-color: var(--c-border-hover, var(--c-border));
}
.vcard.is-current {
  background: var(--c-primary-50);
  border-color: var(--c-primary-200);
}
.vcard.is-current::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--c-primary);
  border-radius: var(--r-md) 0 0 var(--r-md);
}

.vcard__check { flex: 0 0 auto; margin-top: 2px; }

/* 缩略图 */
.vcard__thumb {
  width: 44px;
  height: 58px;
  border-radius: var(--r-sm);
  overflow: hidden;
  flex: 0 0 auto;
  background: var(--c-bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.vcard__thumb img { width: 100%; height: 100%; object-fit: cover; }
.vcard__noimg { font-size: var(--fs-xs); color: var(--c-text-4); }

/* 正文 */
.vcard__body { flex: 1; min-width: 0; }

.vcard__spec-row {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-1);
}
.vcard__color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--c-primary);
  flex: 0 0 auto;
}
.vcard__spec {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vcard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.vcard__price {
  font-size: var(--fs-sm);
  color: var(--c-primary);
  font-weight: 700;
  font-family: monospace;
}

/* 删除按钮 */
.vcard__del {
  position: absolute;
  top: var(--sp-2);
  right: var(--sp-2);
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: var(--c-text-4);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  border-radius: var(--r-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.vcard:hover .vcard__del { opacity: 1; }
.vcard__del:hover { background: var(--c-danger-50, #fef2f2); color: var(--c-danger, #ef4444); }

/* 进度条 */
.vcard__prog{display:flex;align-items:center;gap:6px;margin-top:6px}
.vcard__prog-bar{flex:1;height:4px;border-radius:2px;background:var(--c-border);overflow:hidden}
.vcard__prog-fill{height:100%;background:var(--c-primary);transition:width .2s}
.vcard__prog-txt{font-size:var(--fs-xs);color:var(--c-text-3)}
</style>
