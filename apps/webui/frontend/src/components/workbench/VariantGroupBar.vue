<template>
  <div class="vgb">
    <!-- 标题行：变体组 + 总数 + 说明小字 -->
    <div class="vgb-head">
      <span class="vgb-head__title">🔗 变体组</span>
      <span class="vgb-head__count">共 {{ wb.variantCount }} 个变体</span>
      <span class="vgb-head__hint">（同组合并成一张 Ozon 多变体卡）</span>
    </div>

    <!-- 横排胶囊 -->
    <div class="vgb-pills">
      <div v-if="!wb.variants.length" class="vgb-pills__empty">暂无变体</div>
      <div
        v-for="v in wb.variants"
        :key="v.id"
        class="vpill"
        :class="{ 'is-current': v.id === wb.currentVariantId }"
        @click="onSelect(v)"
      >
        <!-- 缩略图（无图占位） -->
        <div class="vpill__thumb">
          <img v-if="v.image" :src="v.image" />
          <span v-else class="vpill__noimg">无图</span>
        </div>

        <!-- 颜色点 -->
        <span class="vpill__dot" :style="{ background: variantColor(v) }" :title="variantColorName(v)" />

        <!-- spec 文本（过长省略） -->
        <span class="vpill__spec" :title="v.spec">{{ v.spec || '—' }}</span>

        <!-- 完成度 N/7 -->
        <span class="vpill__done">{{ v.done || 0 }}/7</span>
        <span
          v-if="wb.variantTaskChecking(v.id) || wb.variantTaskRunning(v.id)"
          class="vpill__spinner"
          title="该变体有任务正在处理"
          aria-label="任务处理中"
        ></span>

        <!-- hover 出现的小 × 删除 -->
        <button class="vpill__del" title="删除变体" @click.stop="onDelete(v)">×</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ElMessageBox } from 'element-plus'
import { useWorkbenchStore, variantColor, variantColorName } from '../../stores/workbench.js'
import { api } from '../../api.js'

const wb = useWorkbenchStore()
const emit = defineEmits(['variant-deleted'])

async function onSelect(v) {
  wb.setCurrentVariant(v.id)
  const job = await wb.checkVariantTask(v.id)
  if (String((job && job.status) || '').toLowerCase() === 'done') await wb.reload()
}

// 状态徽标文案 / 语义（从 VariantCardsPane 搬过来，保持口径一致）
// 当前胶囊条暂只用颜色点 + spec + 完成度，状态函数保留以备扩展，不直接渲染。
// （需求未要求状态徽标上条，故此处不引入 SBadge，避免无用渲染）

// 删除变体：确认弹窗 → 调 api.deleteDraft → 成功后 emit 让父级 loadDrafts
async function onDelete(v) {
  try {
    await ElMessageBox.confirm('删除该变体草稿？', '删除', { type: 'warning' })
    await api.deleteDraft(v.id)
    emit('variant-deleted', v.id)
  } catch {
    // 取消忽略
  }
}
</script>

<style scoped>
.vgb {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--c-border);
  background: var(--c-white);
}

/* 标题行 */
.vgb-head {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.vgb-head__title {
  font-size: var(--fs-md);
  font-weight: 700;
  color: var(--c-text);
}
.vgb-head__count {
  font-size: var(--fs-sm);
  color: var(--c-text-2);
}
.vgb-head__hint {
  font-size: var(--fs-xs);
  color: var(--c-text-3);
}

/* 胶囊：自动折行铺满，不横向滚动 */
.vgb-pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
.vgb-pills__empty {
  color: var(--c-text-4);
  font-size: var(--fs-sm);
  padding: var(--sp-2) 0;
}

/* 单个胶囊 */
.vpill {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-1) var(--sp-3) var(--sp-1) var(--sp-1);
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-bg-2);
  cursor: pointer;
  flex: 0 0 auto;
  max-width: 240px;
  transition: background 0.15s, border-color 0.15s;
}
.vpill:hover {
  background: var(--c-bg);
}
/* 当前选中：紫色描边 + 浅紫底 */
.vpill.is-current {
  background: var(--c-primary-50);
  border-color: var(--c-primary);
}

/* 缩略图 */
.vpill__thumb {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  overflow: hidden;
  flex: 0 0 auto;
  background: var(--c-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}
.vpill__thumb img { width: 100%; height: 100%; object-fit: cover; }
.vpill__noimg { font-size: 9px; color: var(--c-text-4); }

/* 颜色点 */
.vpill__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
  box-shadow: inset 0 0 0 1px rgba(20, 20, 40, 0.12);
}

/* spec 文本（省略） */
.vpill__spec {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* 完成度 */
.vpill__done {
  font-size: var(--fs-xs);
  color: var(--c-text-3);
  flex: 0 0 auto;
  font-family: monospace;
}

.vpill__spinner {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--c-primary-100, #dce8ff);
  border-top-color: var(--c-primary, #7c3aed);
  flex: 0 0 auto;
  animation: vpill-spin .8s linear infinite;
}

@keyframes vpill-spin { to { transform: rotate(360deg); } }

/* hover 小 × */
.vpill__del {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border: 1px solid var(--c-border);
  background: var(--c-white);
  color: var(--c-text-3);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.vpill:hover .vpill__del { opacity: 1; }
.vpill__del:hover { background: var(--c-danger-bg); color: var(--c-danger); border-color: var(--c-danger); }
</style>
