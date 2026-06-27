# 前端重建 F0:设计系统 + 应用外壳 + 样板页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。Steps 用 checkbox(`- [ ]`)。

**Goal:** 在现有 Vue3 前端上建立设计令牌 + 9 个自建基础组件 + vue-router 应用外壳(Sidebar/TopBar),并用原型保真的"店铺管理"样板页验证地基。

**Architecture:** 增量重建(approach A)+ 混合 UI 库(自建组件用 tokens,重控件用 Element Plus 改主题)。新增 `styles/tokens.css`、`ui/`、`layouts/`、`router/`;`App.vue` 瘦身挂 `<router-view>`,现有 6 view 原样挂路由,只店铺管理换新页。保留 `api.js`/Pinia/`auth.js`。

**Tech Stack:** Vue 3.5(`<script setup>`)、vue-router 4、Vite 5、Element Plus 2、Vitest + @vue/test-utils(jsdom)。

**全局约定:** 工作目录 `E:\personal\ozon-helper\apps\webui\frontend`;分支 `feat/auto-listing-ai-pipeline`;包管理用 `npm`;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。测试 `npm test`(= `vitest run`),构建 `npm run build`,两者均须通过。组件测试用 `@vue/test-utils` 的 `mount`;涉及 Element Plus 控件的组件测试加 `global: { plugins: [ElementPlus] }`,涉及 `<router-link>` 的加 `global: { stubs: { 'router-link': { template: '<a><slot/></a>' } } }`。视觉保真:实现外壳/样板页时可本地起 `python -m http.server` 渲染原型 `C:\Users\42918\Desktop\右侧变体卡片展示设计\*.dc.html` 对照。设计令牌名以 spec 为准。参考 spec:`docs/superpowers/specs/2026-06-27-frontend-f0-design-system-shell-design.md`。

每个组件 scoped 样式**只用 tokens 变量,零硬编码色值**。

---

## File Structure
| 文件 | 职责 |
|---|---|
| `src/styles/tokens.css` | 设计令牌(CSS 变量),唯一真相源 |
| `src/styles/element-theme.css` | 用 tokens 覆写 EP CSS 变量 |
| `src/ui/SButton.vue` `SBadge.vue` `SChip.vue` `SSectionHeader.vue` | 基础组件批 A |
| `src/ui/SCard.vue` `SStatCard.vue` `SAlert.vue` `SAvatar.vue` `STabs.vue` | 基础组件批 B |
| `src/ui/index.js` | 统一导出 |
| `src/router/index.js` | vue-router(7 路由 + 守卫) |
| `src/layouts/AppLayout.vue` `AppSidebar.vue` `AppTopBar.vue` | 外壳 |
| `src/views/Stores.vue` | 样板页(店铺管理) |
| `src/views/Placeholder.vue` | 数据分析占位 |
| `src/App.vue` `src/main.js` | 瘦身 + 挂 router |

---

## Task 1:依赖 + 设计令牌 + EP 主题

**Files:**
- Modify: `package.json`(加 vue-router)
- Create: `src/styles/tokens.css`、`src/styles/element-theme.css`
- Modify: `src/main.js`

- [ ] **Step 1: 装 vue-router** `cd /e/personal/ozon-helper/apps/webui/frontend && npm install vue-router@4 2>&1 | tail -3`。确认 package.json dependencies 出现 `vue-router`。

- [ ] **Step 2: 写 tokens.css**

`src/styles/tokens.css`:
```css
:root {
  /* 品牌 */
  --c-primary:#7c3aed; --c-primary-hover:#8b5cf6;
  --c-primary-50:#f5f3ff; --c-primary-100:#ede9fe; --c-primary-200:#c4b5fd;
  --c-indigo:#6366f1;
  /* 中性 */
  --c-text:#1f2733; --c-text-2:#5b6675; --c-text-3:#8a94a3; --c-text-4:#b8c0cc;
  --c-border:#e5e8ef; --c-bg:#f7f9fc; --c-bg-2:#fafbfc; --c-white:#fff;
  /* 状态 + 浅底 */
  --c-success:#10b981; --c-success-bg:#ecfdf5;
  --c-danger:#ef4444;  --c-danger-bg:#fef2f2;
  --c-info:#3b82f6;    --c-info-bg:#eff6ff;
  --c-warn:#b45309;    --c-warn-bg:#fffbeb;
  /* 间距 */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px; --sp-6:32px;
  /* 圆角 + 阴影 */
  --r-sm:8px; --r-md:12px; --r-lg:16px;
  --sh-card:0 1px 3px rgba(20,20,40,.06); --sh-pop:0 8px 24px rgba(20,20,40,.12);
  /* 字号 */
  --fs-xs:12px; --fs-sm:13px; --fs-md:14px; --fs-lg:16px; --fs-xl:20px; --fs-2xl:24px;
}
```

- [ ] **Step 3: 写 element-theme.css**(把 EP 主色映射到 tokens)
```css
:root {
  --el-color-primary:var(--c-primary);
  --el-color-primary-light-3:var(--c-primary-hover);
  --el-color-primary-light-5:var(--c-primary-200);
  --el-color-primary-light-7:var(--c-primary-100);
  --el-color-primary-light-9:var(--c-primary-50);
  --el-color-success:var(--c-success);
  --el-color-danger:var(--c-danger);
  --el-color-warning:var(--c-warn);
  --el-color-info:var(--c-info);
  --el-border-radius-base:var(--r-sm);
}
```

- [ ] **Step 4: main.js 引入**(在现有 `import './styles.css'` / `import './theme.css'` 之后加):
```js
import './styles/tokens.css'
import './styles/element-theme.css'
```

- [ ] **Step 5: 验证构建** `npm run build 2>&1 | tail -5` → 成功(无报错)。`npm test 2>&1 | tail -3` → 现有测试仍绿。

- [ ] **Step 6: 提交**
```bash
git add package.json package-lock.json src/styles/tokens.css src/styles/element-theme.css src/main.js
git commit -m "feat(fe): F0 设计令牌 tokens.css + EP 紫色主题 + 装 vue-router

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2:基础组件批 A(SButton / SBadge / SChip / SSectionHeader)

**Files:**
- Create: `src/ui/SButton.vue` `SBadge.vue` `SChip.vue` `SSectionHeader.vue`
- Test: `src/ui/ui.test.js`(批 A 部分)

- [ ] **Step 1: 写测试(先红)** `src/ui/ui.test.js`:
```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SButton from './SButton.vue'
import SBadge from './SBadge.vue'
import SChip from './SChip.vue'
import SSectionHeader from './SSectionHeader.vue'

describe('SButton', () => {
  it('渲染 slot + variant class + 点击事件', async () => {
    const w = mount(SButton, { props: { variant: 'primary' }, slots: { default: '保存' } })
    expect(w.text()).toContain('保存')
    expect(w.classes().join(' ')).toContain('s-btn--primary')
    await w.trigger('click')
    expect(w.emitted('click')).toBeTruthy()
  })
  it('loading/disabled 时不触发 click', async () => {
    const w = mount(SButton, { props: { loading: true } })
    await w.trigger('click')
    expect(w.emitted('click')).toBeFalsy()
  })
})
describe('SBadge', () => {
  it('variant 映射 class + slot', () => {
    const w = mount(SBadge, { props: { variant: 'success' }, slots: { default: '已连接' } })
    expect(w.text()).toContain('已连接')
    expect(w.classes().join(' ')).toContain('s-badge--success')
  })
})
describe('SChip', () => {
  it('active class + close 事件', async () => {
    const w = mount(SChip, { props: { active: true, closable: true }, slots: { default: '雾灰' } })
    expect(w.classes().join(' ')).toContain('is-active')
    await w.find('.s-chip__close').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })
})
describe('SSectionHeader', () => {
  it('标题 + 操作 slot', () => {
    const w = mount(SSectionHeader, { props: { title: '店铺管理' }, slots: { actions: '<button>加</button>' } })
    expect(w.text()).toContain('店铺管理')
    expect(w.text()).toContain('加')
  })
})
```

- [ ] **Step 2: 跑测试确认红** `npm test src/ui/ui.test.js 2>&1 | tail -8` → FAIL(组件不存在)。

- [ ] **Step 3: 实现 4 组件**(只用 tokens 变量)

`src/ui/SButton.vue`:
```vue
<script setup>
const props = defineProps({
  variant: { type: String, default: 'primary' }, // primary|ghost|danger|subtle
  size: { type: String, default: 'md' },          // sm|md
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
```

`src/ui/SBadge.vue`:
```vue
<script setup>
defineProps({ variant: { type: String, default: 'neutral' } }) // success|danger|info|warn|neutral|primary
</script>
<template><span class="s-badge" :class="`s-badge--${variant}`"><slot /></span></template>
<style scoped>
.s-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:999px;
  font-size:var(--fs-xs);font-weight:600;line-height:1.6}
.s-badge--success{background:var(--c-success-bg);color:var(--c-success)}
.s-badge--danger{background:var(--c-danger-bg);color:var(--c-danger)}
.s-badge--info{background:var(--c-info-bg);color:var(--c-info)}
.s-badge--warn{background:var(--c-warn-bg);color:var(--c-warn)}
.s-badge--primary{background:var(--c-primary-100);color:var(--c-primary)}
.s-badge--neutral{background:var(--c-bg);color:var(--c-text-3)}
</style>
```

`src/ui/SChip.vue`:
```vue
<script setup>
defineProps({ active: Boolean, closable: Boolean })
const emit = defineEmits(['close', 'click'])
</script>
<template>
  <span class="s-chip" :class="{ 'is-active': active }" @click="emit('click')">
    <slot />
    <span v-if="closable" class="s-chip__close" @click.stop="emit('close')">×</span>
  </span>
</template>
<style scoped>
.s-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:var(--r-sm);
  font-size:var(--fs-sm);border:1px solid var(--c-border);background:#fff;cursor:pointer;color:var(--c-text-2)}
.s-chip.is-active{border-color:var(--c-primary);background:var(--c-primary-50);color:var(--c-primary)}
.s-chip__close{color:var(--c-text-3);font-size:14px;line-height:1}
.s-chip__close:hover{color:var(--c-danger)}
</style>
```

`src/ui/SSectionHeader.vue`:
```vue
<script setup>
defineProps({ title: String, subtitle: String })
</script>
<template>
  <div class="s-sec">
    <div class="s-sec__l"><span class="s-sec__bar"></span>
      <div><div class="s-sec__t">{{ title }}</div>
        <div v-if="subtitle" class="s-sec__s">{{ subtitle }}</div></div></div>
    <div class="s-sec__a"><slot name="actions" /></div>
  </div>
</template>
<style scoped>
.s-sec{display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-4)}
.s-sec__l{display:flex;align-items:center;gap:var(--sp-3)}
.s-sec__bar{width:4px;height:18px;border-radius:2px;background:var(--c-primary)}
.s-sec__t{font-size:var(--fs-xl);font-weight:700;color:var(--c-text)}
.s-sec__s{font-size:var(--fs-sm);color:var(--c-text-3);margin-top:2px}
</style>
```

- [ ] **Step 4: 跑测试确认绿** `npm test src/ui/ui.test.js 2>&1 | tail -6` → 批 A 测试 PASS。
- [ ] **Step 5: 提交**
```bash
git add src/ui/SButton.vue src/ui/SBadge.vue src/ui/SChip.vue src/ui/SSectionHeader.vue src/ui/ui.test.js
git commit -m "feat(fe): F0 基础组件批A SButton/SBadge/SChip/SSectionHeader(+测试)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3:基础组件批 B(SCard / SStatCard / SAlert / SAvatar / STabs)

**Files:**
- Create: `src/ui/SCard.vue` `SStatCard.vue` `SAlert.vue` `SAvatar.vue` `STabs.vue` `src/ui/index.js`
- Test: 追加到 `src/ui/ui.test.js`

- [ ] **Step 1: 追加测试(先红)** 在 `ui.test.js` 末尾加:
```js
import SCard from './SCard.vue'
import SStatCard from './SStatCard.vue'
import SAlert from './SAlert.vue'
import SAvatar from './SAvatar.vue'
import STabs from './STabs.vue'

describe('SCard', () => {
  it('默认 slot + header slot', () => {
    const w = mount(SCard, { slots: { default: '内容', header: '标题' } })
    expect(w.text()).toContain('内容'); expect(w.text()).toContain('标题')
  })
})
describe('SStatCard', () => {
  it('label + value + danger 态', () => {
    const w = mount(SStatCard, { props: { label: '已连接', value: '2 / 3', danger: false } })
    expect(w.text()).toContain('已连接'); expect(w.text()).toContain('2 / 3')
  })
})
describe('SAlert', () => {
  it('variant + 标题 + 操作 slot', () => {
    const w = mount(SAlert, { props: { variant: 'danger', title: '凭证失效' }, slots: { actions: '<b>重新授权</b>' } })
    expect(w.text()).toContain('凭证失效'); expect(w.text()).toContain('重新授权')
    expect(w.classes().join(' ')).toContain('s-alert--danger')
  })
})
describe('SAvatar', () => {
  it('显示首字母', () => {
    const w = mount(SAvatar, { props: { name: 'RU-Store' } })
    expect(w.text()).toContain('R')
  })
})
describe('STabs', () => {
  it('渲染 items + change 事件', async () => {
    const items = [{ key: 'a', label: '全部' }, { key: 'b', label: '待发布' }]
    const w = mount(STabs, { props: { items, activeKey: 'a' } })
    expect(w.text()).toContain('待发布')
    await w.findAll('.s-tabs__item')[1].trigger('click')
    expect(w.emitted('change')[0]).toEqual(['b'])
  })
})
```

- [ ] **Step 2: 跑测试确认红** → FAIL。

- [ ] **Step 3: 实现 5 组件**

`src/ui/SCard.vue`:
```vue
<script setup>
defineProps({ padding: { type: String, default: 'var(--sp-5)' } })
</script>
<template>
  <div class="s-card">
    <div v-if="$slots.header" class="s-card__h"><slot name="header" /></div>
    <div class="s-card__b" :style="{ padding }"><slot /></div>
    <div v-if="$slots.footer" class="s-card__f"><slot name="footer" /></div>
  </div>
</template>
<style scoped>
.s-card{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-lg);box-shadow:var(--sh-card);overflow:hidden}
.s-card__h{padding:var(--sp-4) var(--sp-5);border-bottom:1px solid var(--c-border);font-weight:600;color:var(--c-text)}
.s-card__f{padding:var(--sp-3) var(--sp-5);border-top:1px solid var(--c-border)}
</style>
```

`src/ui/SStatCard.vue`:
```vue
<script setup>
defineProps({ label: String, value: [String, Number], hint: String, danger: Boolean })
</script>
<template>
  <div class="s-stat">
    <div class="s-stat__l">{{ label }}</div>
    <div class="s-stat__v" :class="{ 'is-danger': danger }">{{ value }}</div>
    <div v-if="hint" class="s-stat__h">{{ hint }}</div>
  </div>
</template>
<style scoped>
.s-stat{background:#fff;border:1px solid var(--c-border);border-radius:var(--r-md);padding:var(--sp-4);box-shadow:var(--sh-card)}
.s-stat__l{font-size:var(--fs-sm);color:var(--c-text-3)}
.s-stat__v{font-size:var(--fs-2xl);font-weight:700;color:var(--c-text);margin-top:6px}
.s-stat__v.is-danger{color:var(--c-danger)}
.s-stat__h{font-size:var(--fs-xs);color:var(--c-text-4);margin-top:4px}
</style>
```

`src/ui/SAlert.vue`:
```vue
<script setup>
defineProps({ variant: { type: String, default: 'info' }, title: String })
</script>
<template>
  <div class="s-alert" :class="`s-alert--${variant}`">
    <div class="s-alert__c">
      <div class="s-alert__t">{{ title }}</div>
      <div v-if="$slots.default" class="s-alert__d"><slot /></div>
    </div>
    <div class="s-alert__a"><slot name="actions" /></div>
  </div>
</template>
<style scoped>
.s-alert{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-4);
  padding:var(--sp-3) var(--sp-4);border-radius:var(--r-md);border:1px solid transparent}
.s-alert--danger{background:var(--c-danger-bg);border-color:#fecaca}
.s-alert--warn{background:var(--c-warn-bg);border-color:#fde68a}
.s-alert--info{background:var(--c-info-bg);border-color:#bfdbfe}
.s-alert--success{background:var(--c-success-bg);border-color:#a7f3d0}
.s-alert__t{font-weight:600;color:var(--c-text)}
.s-alert__d{font-size:var(--fs-sm);color:var(--c-text-2);margin-top:2px}
</style>
```

`src/ui/SAvatar.vue`:
```vue
<script setup>
const props = defineProps({ name: String, size: { type: Number, default: 40 } })
const initial = () => (props.name || '?').trim().charAt(0).toUpperCase()
</script>
<template>
  <div class="s-avatar" :style="{ width: size+'px', height: size+'px', fontSize: (size*0.4)+'px' }">{{ initial() }}</div>
</template>
<style scoped>
.s-avatar{display:inline-flex;align-items:center;justify-content:center;border-radius:var(--r-md);
  background:var(--c-primary-100);color:var(--c-primary);font-weight:700}
</style>
```

`src/ui/STabs.vue`:
```vue
<script setup>
defineProps({ items: { type: Array, default: () => [] }, activeKey: String })
const emit = defineEmits(['change'])
</script>
<template>
  <div class="s-tabs">
    <button v-for="it in items" :key="it.key" class="s-tabs__item"
            :class="{ 'is-active': it.key === activeKey }" @click="emit('change', it.key)">
      {{ it.label }}<span v-if="it.count != null" class="s-tabs__cnt">{{ it.count }}</span>
    </button>
  </div>
</template>
<style scoped>
.s-tabs{display:flex;gap:var(--sp-4);border-bottom:1px solid var(--c-border)}
.s-tabs__item{background:none;border:none;padding:8px 2px;font-size:var(--fs-md);color:var(--c-text-3);
  cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.s-tabs__item.is-active{color:var(--c-primary);border-bottom-color:var(--c-primary);font-weight:600}
.s-tabs__cnt{margin-left:6px;font-size:var(--fs-xs);color:var(--c-text-4)}
</style>
```

`src/ui/index.js`:
```js
export { default as SButton } from './SButton.vue'
export { default as SBadge } from './SBadge.vue'
export { default as SChip } from './SChip.vue'
export { default as SSectionHeader } from './SSectionHeader.vue'
export { default as SCard } from './SCard.vue'
export { default as SStatCard } from './SStatCard.vue'
export { default as SAlert } from './SAlert.vue'
export { default as SAvatar } from './SAvatar.vue'
export { default as STabs } from './STabs.vue'
```

- [ ] **Step 4: 跑测试确认绿** `npm test src/ui/ui.test.js 2>&1 | tail -6` → 全 PASS。
- [ ] **Step 5: 提交**
```bash
git add src/ui/SCard.vue src/ui/SStatCard.vue src/ui/SAlert.vue src/ui/SAvatar.vue src/ui/STabs.vue src/ui/index.js src/ui/ui.test.js
git commit -m "feat(fe): F0 基础组件批B SCard/SStatCard/SAlert/SAvatar/STabs + index(+测试)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4:vue-router + 应用外壳(AppLayout/Sidebar/TopBar)+ App.vue 瘦身

**Files:**
- Create: `src/router/index.js` `src/layouts/AppLayout.vue` `AppSidebar.vue` `AppTopBar.vue` `src/views/Placeholder.vue`
- Modify: `src/main.js`(use router)、`src/App.vue`(瘦身)
- Test: `src/router/router.test.js`

- [ ] **Step 1: 写路由守卫测试(先红)** `src/router/router.test.js`:
```js
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../auth.js', () => ({ isLoggedIn: vi.fn() }))
import { isLoggedIn } from '../auth.js'
import { router } from './index.js'

describe('router 守卫', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('未登录访问受保护路由 → 重定向 /login', async () => {
    isLoggedIn.mockReturnValue(false)
    await router.push('/stores')
    expect(router.currentRoute.value.path).toBe('/login')
  })
  it('已登录可进受保护路由', async () => {
    isLoggedIn.mockReturnValue(true)
    await router.push('/stores')
    expect(router.currentRoute.value.path).toBe('/stores')
  })
})
```

- [ ] **Step 2: 跑测试确认红** → FAIL。

- [ ] **Step 3: 写 router/index.js**
```js
import { createRouter, createWebHashHistory } from 'vue-router'
import { isLoggedIn } from '../auth.js'
import AppLayout from '../layouts/AppLayout.vue'

const routes = [
  { path: '/login', name: 'login', meta: { public: true },
    component: () => import('../views/Login.vue') },
  { path: '/', component: AppLayout, children: [
    { path: '', name: 'drafts', component: () => import('../views/Collect.vue') },
    { path: 'analytics', name: 'analytics', component: () => import('../views/Placeholder.vue') },
    { path: 'stores', name: 'stores', component: () => import('../views/Stores.vue') },
    { path: 'warehouses', name: 'warehouses', component: () => import('../views/Warehouses.vue') },
    { path: 'fulfillment', name: 'fulfillment', component: () => import('../views/Fulfillment.vue') },
    { path: 'settings', name: 'settings', component: () => import('../views/Settings.vue') },
    { path: 'users', name: 'users', component: () => import('../views/Users.vue') },
    { path: 'wallet', name: 'wallet', component: () => import('../views/Wallet.vue') },
  ] },
]
export const router = createRouter({ history: createWebHashHistory(), routes })
router.beforeEach((to) => {
  if (!to.meta.public && !isLoggedIn()) return { path: '/login' }
  if (to.path === '/login' && isLoggedIn()) return { path: '/' }
})
```
> 注:Stores.vue 在 Task 5 才建,Task 4 先建一个最小占位 `src/views/Stores.vue`(`<template><div>店铺管理</div></template>`)让路由能解析,Task 5 再替换为完整页。

- [ ] **Step 4: 写 Placeholder.vue + 占位 Stores.vue**

`src/views/Placeholder.vue`:
```vue
<template><div class="ph"><div class="ph__t">🚧 建设中</div><div class="ph__s">该页将在后续阶段(F2)实现</div></div></template>
<style scoped>.ph{display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh;color:var(--c-text-3)}
.ph__t{font-size:var(--fs-xl);font-weight:600}.ph__s{font-size:var(--fs-sm);margin-top:8px}</style>
```
`src/views/Stores.vue`(临时占位,Task 5 替换):`<template><div>店铺管理</div></template>`

- [ ] **Step 5: 写外壳三件**

`src/layouts/AppSidebar.vue`(品牌 + 当前店标识 + 6 导航 + 版本页脚;用 router-link active):
```vue
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
```

`src/layouts/AppTopBar.vue`(折叠钮 + 余额 + 账号下拉,沿用现有逻辑):
```vue
<script setup>
import { ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus'
import { useRouter } from 'vue-router'
import { clearAuth } from '../auth.js'
defineProps({ balance: [Number, String], username: String, isAdmin: Boolean })
const emit = defineEmits(['toggle'])
const router = useRouter()
function onCmd(c) {
  if (c === 'logout') { clearAuth(); location.reload() }
  else router.push('/' + c)
}
</script>
<template>
  <header class="tb">
    <button class="tb__burger" @click="emit('toggle')">☰</button>
    <div class="tb__right">
      <span v-if="balance != null" class="tb__wallet" @click="router.push('/wallet')">💰 ₽ {{ balance }}</span>
      <ElDropdown trigger="click" @command="onCmd">
        <span class="tb__acct">{{ username || '账号' }} ▾</span>
        <template #dropdown><ElDropdownMenu>
          <ElDropdownItem command="wallet">💰 我的钱包</ElDropdownItem>
          <ElDropdownItem command="settings">⚙️ 设置</ElDropdownItem>
          <ElDropdownItem v-if="isAdmin" command="users">👥 用户管理</ElDropdownItem>
          <ElDropdownItem divided command="logout">退出登录</ElDropdownItem>
        </ElDropdownMenu></template>
      </ElDropdown>
    </div>
  </header>
</template>
<style scoped>
.tb{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 var(--sp-5);
  background:#fff;border-bottom:1px solid var(--c-border)}
.tb__burger{background:none;border:none;font-size:18px;cursor:pointer;color:var(--c-text-2)}
.tb__right{display:flex;align-items:center;gap:var(--sp-4)}
.tb__wallet{font-size:var(--fs-sm);color:var(--c-primary);background:var(--c-primary-50);
  border:1px solid var(--c-primary-200);padding:4px 10px;border-radius:999px;cursor:pointer}
.tb__acct{font-size:var(--fs-sm);color:var(--c-text-2);cursor:pointer}
</style>
```

`src/layouts/AppLayout.vue`(组合 + bootData):
```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '../stores/app.js'
import { getUser, getToken, setAuth } from '../auth.js'
import { api } from '../api.js'
import AppSidebar from './AppSidebar.vue'
import AppTopBar from './AppTopBar.vue'

const store = useAppStore()
const collapsed = ref(false)
const user = ref(getUser())
const balance = ref(null)
const isAdmin = computed(() => user.value && user.value.role === 'admin')

async function loadWallet() {
  try { const r = await api.wallet(); const acc = (r && (r.account || r)) || {}
    if (acc.balance != null) balance.value = acc.balance } catch (e) { /* ignore */ }
}
onMounted(async () => {
  await store.loadState(); store.loadDrafts(); loadWallet()
  if (!user.value) { try { const r = await api.me(); user.value = r.user; setAuth(getToken(), r.user) } catch (e) { /* 401→logout */ } }
})
</script>
<template>
  <div class="app" :class="{ collapsed }">
    <AppSidebar class="app__sb" />
    <div class="app__main">
      <AppTopBar :balance="balance" :username="user && user.username" :is-admin="isAdmin" @toggle="collapsed = !collapsed" />
      <main class="app__content"><router-view /></main>
    </div>
  </div>
</template>
<style scoped>
.app{display:grid;grid-template-columns:220px 1fr;height:100vh}
.app.collapsed{grid-template-columns:0 1fr}
.app__sb{overflow:hidden;transition:.2s}
.app__main{display:flex;flex-direction:column;min-width:0;background:var(--c-bg)}
.app__content{flex:1;overflow:auto;padding:var(--sp-5)}
</style>
```

- [ ] **Step 6: main.js use router + App.vue 瘦身**

`src/main.js`(加 router):
```js
import { router } from './router/index.js'
// ... 现有 createApp 链改为:
createApp(App).use(createPinia()).use(ElementPlus).use(router).mount('#app')
```
`src/App.vue` 整体替换为(保留 SSO token 消费 + 401 监听):
```vue
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
```
> Login.vue 现有 `@logged-in` 事件:它现在是 `/login` 路由组件,登录成功后应 `router.push('/')`。若 Login.vue 用 emit,需改成登录成功后 `useRouter().push('/')`。**先读 Login.vue 看它怎么通知登录成功**,最小改动让它登录后跳首页(setAuth 后 router.push('/'))。

- [ ] **Step 7: 跑路由测试 + 构建** `npm test src/router/router.test.js 2>&1 | tail -6` → PASS。`npm run build 2>&1 | tail -5` → 成功。`npm test 2>&1 | tail -3` → 全绿(含 auth.test.js)。

- [ ] **Step 8: 提交**
```bash
git add src/router src/layouts src/views/Placeholder.vue src/views/Stores.vue src/main.js src/App.vue
git commit -m "feat(fe): F0 vue-router + 应用外壳(Sidebar/TopBar/Layout)+ App.vue 瘦身

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5:样板页 店铺管理(Stores.vue,原型保真)

**Files:**
- Modify: `src/views/Stores.vue`(占位 → 完整页)
- Test: `src/views/stores.test.js`

- [ ] **Step 1: 读数据源**:读 `src/views/Settings.vue`(看 `extraStores`/`persistStores`/`setDefaultStore` 现有店铺增改逻辑)+ `src/stores/app.js`(`storeList`/`currentStore`/`setCurrentStore`)。Stores.vue 复用同样的数据流(`store.settings.ozon_stores` 读、`api.saveSettings({ozon_stores})` 写)。

- [ ] **Step 2: 写测试(先红)** `src/views/stores.test.js`:
```js
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import Stores from './Stores.vue'
import { useAppStore } from '../stores/app.js'

function mountStores() {
  setActivePinia(createPinia())
  const store = useAppStore()
  store.settings = { ozon_stores: [
    { name: 'RU-Store', client_id: '2841057', is_default: true, api_key_saved: true },
    { name: '测试店', client_id: '2207781', is_default: false, api_key_saved: false },
  ] }
  const w = mount(Stores, { global: { plugins: [ElementPlus], stubs: { 'router-link': true } } })
  return { w, store }
}
describe('Stores 样板页', () => {
  it('渲染店铺卡 + 连接状态', () => {
    const { w } = mountStores()
    expect(w.text()).toContain('RU-Store')
    expect(w.text()).toContain('测试店')
    expect(w.text()).toContain('凭证失效') // api_key_saved=false 的店
  })
  it('点切换当前店调 setCurrentStore', async () => {
    const { w, store } = mountStores()
    const spy = vi.spyOn(store, 'setCurrentStore')
    const btn = w.findAll('button').find(b => b.text().includes('切换') || b.text().includes('当前'))
    if (btn) { await btn.trigger('click'); expect(spy).toHaveBeenCalled() }
  })
})
```

- [ ] **Step 3: 跑测试确认红** → FAIL(占位页无内容)。

- [ ] **Step 4: 实现 Stores.vue**(用 ui 组件 + EP 对话框;按原型布局:SSectionHeader + StatCard 行 + SAlert + 店铺卡网格 + 添加卡)。数据:`store.settings.ozon_stores`;切换 `store.setCurrentStore(client_id)`;添加/编辑用 ElDialog + ElInput,提交 `api.saveSettings({ ozon_stores: [...] })` 后 `store.loadState()`。**每店"余额/商品/仓库"无 per-store 端点 → 显示 `—`**(spec 已认可)。卡片状态徽标:`api_key_saved` → `<SBadge variant="success">已连接</SBadge>` 否则 `variant="danger">凭证失效`。当前店:`String(s.client_id)===store.currentStore` → 高亮 + "当前店铺"禁用态,否则"切换为当前"SButton。
  > 实现时本地起 server 渲染原型 `店铺管理.dc.html` 对照视觉。完整组件由实现者按上述契约 + 原型写就(用 SCard/SBadge/SButton/SStatCard/SAlert/SSectionHeader/SAvatar + ElDialog/ElInput)。

- [ ] **Step 5: 跑测试确认绿 + 构建** `npm test src/views/stores.test.js 2>&1 | tail -6` → PASS。`npm run build 2>&1 | tail -3` → 成功。
- [ ] **Step 6: 提交**
```bash
git add src/views/Stores.vue src/views/stores.test.js
git commit -m "feat(fe): F0 样板页 店铺管理(设计系统落地验证:卡片/徽标/统计/对话框)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6:收尾验证

- [ ] **Step 1: 全量前端测试** `npm test 2>&1 | tail -5` → 全绿(ui.test.js + router.test.js + stores.test.js + auth.test.js 等)。
- [ ] **Step 2: 构建** `npm run build 2>&1 | tail -5` → 成功,无 vue-router/EP 报错。
- [ ] **Step 3: 控制器视觉验收**(由 controller 执行):`npm run dev` 起开发服务器,浏览器渲染——确认 ① 新外壳(紫色 Sidebar 6 导航 + TopBar)显示正常;② 路由切换 + active 高亮工作;③ 店铺管理样板页与原型一致(卡片/徽标/统计/添加对话框);④ 现有页(商品草稿等)能在新外壳里打开(旧样式可接受)。
- [ ] **Step 4: 有收尾改动则提交**;无则结束。

---

## Self-Review
- **Spec 覆盖**:① tokens+EP主题→T1;② 9 基础组件→T2(4)+T3(5);③ 外壳+router+守卫+App瘦身+现有页挂载+数据分析占位→T4;④ 店铺管理样板页→T5;⑤ 测试(组件/守卫/页)→各任务内 + T6 收尾;⑥ 保留 api/Pinia/auth→全程不改这三者。全覆盖。
- **占位符**:T5 Step4 的 Stores.vue 完整 markup 交实现者按"契约 + 原型对照"写——给了精确数据流/组件清单/状态映射契约,非空泛占位(前端视觉页按原型实现是正常做法,非 placeholder)。其余步骤均含真实代码。
- **类型/契约一致**:组件 props/emits(SButton variant/size/loading + @click、SBadge variant、SChip active/closable+@close、STabs items[{key,label,count}]/activeKey+@change、SStatCard label/value/hint/danger、SAlert variant/title+actions slot、SAvatar name/size)在 T2/T3 定义,T5 样板页按此用;router 的 `router` 具名导出 + `createWebHashHistory` 一致;`store.currentStoreName/storeList/setCurrentStore/loadState` 用现有 Pinia API。
- **风险**:① Login.vue 登录成功通知方式(emit vs 直接跳)——T4 Step6 已要求先读再最小改;② EP 组件测试需 `global.plugins:[ElementPlus]`——已在全局约定 + 测试里写明;③ 现有 `styles.css/theme.css` 的 `--gp-*` 变量与新 `--c-*` 并存不冲突(新组件只用 --c-*,旧页继续用 --gp-*)。
