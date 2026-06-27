# 前端重建 F0:设计系统 + 应用外壳 + 样板页(店铺管理)— 设计

- 日期:2026-06-27
- 范围:前端整体重建的第一阶段 **F0(地基)**。后续 F1(变体工作台,拆 god-component)、F2(其余页)各自独立 spec。
- 目标:在现有 `apps/webui/frontend/`(Vue3.5+Vite+Pinia+ElementPlus+Vitest)上,建立**设计令牌 + 基础组件库 + 应用外壳 + vue-router**,并用**一个原型保真的样板页(店铺管理)**验证这套地基。打法 = 增量重建(approach A)+ 混合 UI 库。
- 原型:`C:\Users\42918\Desktop\右侧变体卡片展示设计`(本地 `python -m http.server` 渲染)。品牌"上品助手 Pro",紫罗兰 SaaS 风。

## 为什么要样板页(店铺管理)
不在真空里造设计系统。店铺管理一页同时压中三个最该验证的点:① 最高复用的自建组件(Card/Badge/Button/StatCard/Alert,每页都用);② 混合 UI 库最大风险(EP 对话框/表单能否干净对齐紫色板);③ 自包含(接现有 `settings.ozon_stores` API,不碰新后端)。验过它,F1 才敢放心拆 god-component。

## 保留(不动)
- `src/api.js`(集中式 fetch 封装,几十端点已对接,401 自动登出,store_client_id 后缀)。
- `src/stores/`(Pinia,含 `app.js`:settings/status/currentStore/storeList/setCurrentStore/loadState/loadDrafts/...)。
- `src/auth.js`(+ `auth.test.js`):isLoggedIn/getUser/getToken/setAuth/clearAuth、SSO token 消费。
- 现有 6 个 view 文件(F0 阶段原样挂进路由,旧样式,F1/F2 再重绘)。

## 目录结构(新增)
```
src/
  styles/
    tokens.css        # 设计令牌(CSS 变量)— 唯一真相源
    element-theme.css # 用 tokens 覆写 Element Plus CSS 变量
  ui/                 # 自建基础组件(消费 tokens)
    SCard.vue SBadge.vue SChip.vue SButton.vue STabs.vue
    SStatCard.vue SAlert.vue SSectionHeader.vue SAvatar.vue
    index.js          # 统一导出(可选全局注册)
  layouts/
    AppLayout.vue AppSidebar.vue AppTopBar.vue
  router/
    index.js
  views/
    Stores.vue        # ★ 新样板页(店铺管理)
```
`main.js` 增 `import './styles/tokens.css'`、`createRouter`、`app.use(router)`;`App.vue` 瘦身为挂 `<router-view>` + 全局 provide(去掉手搓 activeView 视图切换)。

## ① 设计令牌(`tokens.css`,CSS 变量,从原型提取)
- **品牌**:`--c-primary:#7c3aed`;`--c-primary-hover:#8b5cf6`;`--c-primary-50:#f5f3ff`;`--c-primary-100:#ede9fe`;`--c-primary-200:#c4b5fd`;`--c-indigo:#6366f1`。
- **中性**:文字 `--c-text:#1f2733` / `--c-text-2:#5b6675` / `--c-text-3:#8a94a3` / `--c-text-4:#b8c0cc`;边框 `--c-border:#e5e8ef`;底 `--c-bg:#f7f9fc` / `--c-bg-2:#fafbfc` / 卡片白 `#fff`。
- **状态**:`--c-success:#10b981` `--c-danger:#ef4444` `--c-info:#3b82f6` `--c-warn:#b45309`(各配一个浅底变体)。
- **尺度**:间距 `--sp-1..6` = 4/8/12/16/24/32;圆角 `--r-sm:8px --r-md:12px --r-lg:16px`;阴影 `--sh-card:0 1px 3px rgba(20,20,40,.06)` / `--sh-pop:0 8px 24px rgba(20,20,40,.12)`;字号 `--fs-xs:12 --fs-sm:13 --fs-md:14 --fs-lg:16 --fs-xl:20 --fs-2xl:24`(px)。
- `element-theme.css`:用上面变量映射 EP 的 `--el-color-primary` 等,使 EP 控件主题色对齐。

## ② 基础组件库(自建 9 个,消费 tokens)
每个单一职责、props 明确、scoped 样式只用 tokens 变量(零硬编码色值):
- **SButton** — `variant: primary|ghost|danger|subtle`,`size: sm|md`,`loading`,`disabled`;slot 内容 + 可选前置图标 slot。
- **SBadge** — 状态徽标,`variant: success|danger|info|warn|neutral|primary`;小圆角药丸。
- **SChip** — 可选中标签(变体卡颜色芯片那种),`active`,`closable`,`@close`。
- **SCard** — 容器卡(白底/圆角/`--sh-card`/可选 padding/header slot/footer slot)。
- **SStatCard** — KPI 卡(label + 大数字 value + 可选副文/危险态)。
- **SAlert** — 横幅(`variant`,icon,标题 + 描述 slot + 右侧操作 slot)。
- **SSectionHeader** — 区块标题(左竖条 + 标题 + 右侧操作 slot)。
- **STabs** — 标签页头(items + activeKey + `@change`;只管 tab 头,内容由父控制)。
- **SAvatar** — 圆形头像(文字首字母 or 图,尺寸,背景色)。
- **重控件继续用 Element Plus(改主题)**:ElSelect/ElDialog/ElInput/ElUpload/ElPagination/ElMessage/ElSwitch/ElSlider。

## ③ 应用外壳 + 路由
- **AppSidebar**:品牌"上品助手 Pro" + 当前店标识(`currentStoreName`,绿点)+ 6 导航(`<router-link>`:商品草稿`/`、数据分析`/analytics`、店铺管理`/stores`、仓库管理`/warehouses`、备货发货`/fulfillment`、系统设置`/settings`,active 高亮)+ 版本页脚("Version 2026.06 · 本地数据·凭证不出本机")。可折叠(状态在 layout)。
- **AppTopBar**:折叠钮 + 右侧余额(`store.walletBalance`,₽)+ SAvatar 头像菜单(用户名/退出,沿用 onLogout)。
- **AppLayout**:Sidebar + TopBar + `<router-view>`;`onMounted` 跑 `bootData()`(loadState→loadDrafts→loadWallet,从现 App.vue 迁来)。
- **router/index.js**:7 路由(6 业务页 + `/login`)。**全局前置守卫**:`isLoggedIn()` 假→ 重定向 `/login`(login 路由 meta.public);登录成功(`onLoggedIn`)后 router.push 首页。SSO token 消费(`consumeUrlToken`)在 router 创建前或守卫里执行一次。
- 现有 6 view **原样挂**(Collect→`/`、Settings→`/settings`、Warehouses→`/warehouses`、Fulfillment→`/fulfillment`;数据分析 F0 暂用占位/或挂现有最近页;Users/Wallet 作为次级路由或菜单项保留)。**只有店铺管理换成新 `Stores.vue`**。

> 数据分析页 F0 无现成 view → 路由先挂一个"建设中"占位组件(F2 实现),不阻塞外壳。

## ④ 样板页:店铺管理(`Stores.vue`,原型保真)
数据源(已存在,无新后端):`store.settings.ozon_stores`(`[{name, client_id, is_default, api_key_saved}]`)、`store.currentStore`/`setCurrentStore`、增改走 `api.saveSettings({ozon_stores:[...]})`(沿用 Settings.vue 现有 persist 逻辑)。
- 布局(按原型):SSectionHeader("店铺管理" + "添加店铺" SButton)→ 一行 SStatCard(已连接 N/M、商品总数、需处理)→ SAlert(若有 `api_key_saved=false` 的店:"凭证失效")→ 店铺卡网格(每店一张 SCard:SAvatar + 名 + Client-Id + 连接状态 SBadge(`api_key_saved`→已连接/凭证失效)+ 余额/商品/仓库三栏 + API-Key 脱敏 + 接入日期 + 操作 SButton:当前店切换(`setCurrentStore`)/编辑凭证/同步/移除)+ 末尾"添加 Ozon 店铺"虚线卡。
- 添加/编辑:EP 对话框(ElDialog + ElInput,名/Client-Id/API-Key)→ `api.saveSettings`。
- **已知缺口(F0 可接受)**:每店"余额/商品数/仓库数/连接健康"原型有但当前无 per-store 统计端点 → 渲染为 `—` 或用已有的全局值;真 per-store 统计列为后续后端增强,不阻塞 F0(样板页的职责是验证设计系统,不是补后端)。

## ⑤ 测试
- Vitest + @vue/test-utils:9 个基础组件各测渲染 + 关键 prop 变体 + 交互事件(如 SButton click/loading 禁用、SChip @close、STabs @change、SBadge variant class)。
- 外壳:路由守卫(未登录→/login)、Sidebar 导航 active、TopBar 余额/退出。
- 样板页:store 列表渲染、切换当前店调 `setCurrentStore`、添加对话框打开。
- 现有 `auth.test.js` 等不破;`npm test`(vitest run)全绿。

## 非目标
- 不重绘 F1 变体工作台 / F2 其余页(F0 只接店铺管理这一页 + 其余原样挂)。
- 不引入新状态库/新框架(保留 Pinia + 现有 api.js)。
- 不做 per-store 统计后端、不做图标体系大改(用现有/emoji 或轻量 SVG,够用即可)。
- 不动后端(纯前端阶段)。
- 不做暗色模式(YAGNI)。
