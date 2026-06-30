# 数据分析（Analytics）

> 店铺经营数据看板:把 Ozon 店铺的 SKU 漏斗/流量趋势/搜索词工程化进 app。前端「数据分析」页(`/analytics`,`views/Analytics.vue`)。源自旧脚本 `sku_dashboard/traffic/keywords` 工程化。

## 1. 交互
页头:**店铺下拉**(多店,来自 `settings.ozon_stores`;含「全部店铺」选项 value='')+ **快捷时间预设**(今天/昨天/近7天/近30天,默认近30天)+ **导出**(CSV)。
- **快捷时间预设**(`RANGE_OPTS`,`Analytics.vue`):四个按钮——**今天**(value `'today'`,from=to=今天)、**昨天**(`'yesterday'`,from=to=昨天 `daysAgoStr(1)`)、**近7天**(`'7'`,from=`daysAgoStr(7)`/to=今天)、**近30天**(`'30'`,from=`daysAgoStr(30)`/to=今天)。`dateRange.preset` 存这四个 value,模板 `is-active` 据此高亮当前预设。`useAnalytics.setRange(preset)` 切预设时清空 traffic/keywords 并重拉 dashboard。
- **诊断 banner**(`DiagnosticBanner`):**核心诊断卡**(🚨 图标 + 核心问题标题 + 正文内嵌曝光/访问/会话率/加购/下单**具体数字** + 排查清单「价格/主图/详情/评价/运费」+ 指向「搜索词洞察」tab 的 CTA;红底卡 `.db`)。degraded(无 Premium)仍单独 `SAlert` 提示。仅在存在突出问题时渲染核心卡。
- **转化漏斗**(`ConversionFunnel`):曝光 → 访问 → 加购 → 下单 四段;**每级柱高按量缩放**(10~100%),每级带诊断备注(入口流量 / 会话率健康 / 转化健康 / ⚠断点在此 / ⚠无成交),**断点级红色高亮**(柱+卡边框 danger);区块副标题「找到断点」。
- **KPI cards**(`KpiCards`,SStatCard):总曝光 / **总访问/会话**(sub 显示会话率% = 访问/曝光)/ **加购转化**(sub「N 次加购」,值 0 或 <1% 时危险色)/ **GMV/下单**(`₽` 卢布,sub「N 单」,收入 0 或无成交时危险色)。
- **三 tab**(STabs):
  - **商品表现**(`ProductTable`):SKU 表;**库存/曝光/访问/加购/下单列表头可点击排序**(带 ↓/↑ 箭头,点击 desc↔asc 循环,默认曝光降序);**价格双行**(现价绿色 + 划线原价灰删除线,`₽`);收入 `₽`;**诊断标签文案带操作建议**(缺货·补库存 / 0曝光·优化标题/广告 / 页面0转化·查价/主图/评价 / 加购未转化·查运费 / 正常);**「仅看问题商品(N)」可切换按钮**(激活紫底,label 含问题商品计数);提示「点任意行 → 打开该商品草稿编辑」;点行 `open-draft`(跳工作台)。
  - **流量趋势**(`TrafficTrend`):区块标题「流量趋势」+ 解读副标题;按 day 的曝光/访问/加购柱状(纯 CSS),**三色配色 曝光紫(--c-primary)/访问浅紫(--c-primary-hover)/加购橙(#f59e0b)**。
  - **搜索词洞察**(`KeywordInsight`):区块标题 + 副标题;机会/污染/已覆盖三卡 + 搜索词表;**每行末尾判定标签**(机会词蓝 / 污染词橙 / 已覆盖绿 药丸,SBadge info/warn/success;优先级 已覆盖>污染词>机会词);GMV 列 `₽` 卢布。
- 缺凭证 / degraded → `SAlert` 友好提示「请先在系统设置配置 Ozon 店铺凭证」。

> **货币口径**:本页 GMV / 收入 / 搜索词 GMV 均为俄罗斯店**卢布 `₽`**(KpiCards、ProductTable、KeywordInsight 统一);仅成本类(若确为人民币)才用 `¥`。

## 2. 数据
前端 `composables/useAnalytics.js`(`{loading,error,store,storeList,dateRange,dashboard,traffic,keywords,activeTab,load,loadTab,setRange,exportCsv}`):dashboard 必拉、traffic/keywords 切 tab 懒拉、exportCsv 从 dashboard.rows 生成 CSV(utf-8 BOM)。

| 接口 | api.js | 后端 | 返回 |
|---|---|---|---|
| SKU 漏斗 | `analyticsDashboard({date_from,date_to,store_client_id?})` | `POST /api/analytics/dashboard` | `{store,date_from,date_to,grand_total,rows:[{sku,offer_id,title,price,stock,exposure,sessions,cart,conv_cart_pct,ordered_units,revenue,diagnostics:[]}],degraded}` |
| 流量趋势 | `analyticsTraffic(...)` | `POST /api/analytics/traffic` | `{rows:[{sku,day,hits_view,session_view,hits_tocart,ordered_units}]}` |
| 搜索词 | `analyticsKeywords(...)` | `POST /api/analytics/keywords` | `{by_sku:{sku:[{query,searches,ctr,position,orders,gmv}]}}` |

**后端**(`services/analytics_service.py` 纯函数 + 编排,**不进 App god-class**;`routers/analytics.py` 用活属性 `app_instance.APP._settings_for_store`):
- `dashboard` 编排:build_client → `/v3/product/list`(全 offer)→ `/v3/product/info/list`(标题/价)+ `/v5/product/info/prices`(活动价)+ `/v4/product/info/stocks`(库存)+ `/v1/analytics/data` dim=[sku](漏斗)→ `build_dashboard_rows` 合并+诊断 → `grand_total` 聚合。
- `traffic`:`/v1/analytics/data` dim=[sku,day]。`keywords`:`/v1/analytics/product-queries/details` 分页。
- adapter 拉取函数在 `ozon_client_adapter.py`(`fetch_analytics_sku/traffic`、`fetch_product_queries`、`fetch_prices/stocks`)。
- 多店:`store_client_id` 非空 → `_settings_for_store`(复用 `settings.ozon_stores`)单店路径。
- **全部店铺并发聚合**:`store_client_id` 为空且配置了 **≥2 个店** → router 用 `_all_store_settings()` 对每个 store 的 `client_id` 调 `_settings_for_store(cid)` 构造各店 settings 列表(构造时缺凭证的店跳过),调 service 的 `dashboard_all/traffic_all/keywords_all`。这三个 `_all` 函数用 `ThreadPoolExecutor`(worker=`min(8, 店数)`)并发跑各店对应单店函数(`dashboard()/traffic()/keywords()`,均 I/O 密集调 Ozon API,线程并发有效),再合并:
  - `dashboard_all`:rows 拼接(每行加 `store`=来源店 cid)、`grand_total` 用合并后 rows 重算、`store='all'`、`degraded`=任一店 degraded。
  - `traffic_all`:rows 拼接(每行带 `store`)、`store='all'`。
  - `keywords_all`:合并 `by_sku`,跨店同 sku 用 `<store_cid>:<sku>` 前缀作 key 避免覆盖、`store='all'`。
  - 每店 best-effort:某店缺凭证(ValueError)/异常则跳过该店;**全部失败才 raise ValueError**(→ 400)。
  - 单店缓存照常生效(`_all` 复用单店函数,各店各自命中 `_cache`)。

## 3. 规则
- **诊断标签**(后端算):`缺货`(stock≤0)、`0曝光`(exposure≤0)、`高曝光0转化`(exposure>200 且 ordered=0)、`加购未转化`(cart>0 且 ordered=0)。`conv_cart_pct`=cart/sessions×100(防零)。
- **降级**:无 Premium → `/v1/analytics/data` 403 → 只取 ordered_units/revenue,`degraded=True`,前端流量列标降级。
- **限速**:analytics 每店每分钟 1 次 → 429 等 ~60s 重试。
- **进程内 TTL 缓存**(`analytics_service._cache`):dashboard/traffic 600s、keywords 21600s(避开限速+快速翻页)。无 Redis。
- **滞后**:数据 T+1~2;搜索词 date_to ≤ 今天-3 且稀疏(隐私阈值)。页头/UI 注明。
- **缺凭证** → 400「未配置 Ozon 店铺凭证」(不 500)。

## 4. 测试与验收
- 后端 33 单测(build_dashboard_rows 诊断/conv、grand_total 聚合、adapter mock 解析/降级/分页、缓存 TTL、router 缺凭证 400);前端组件用例(`components/analytics/analytics.test.js` 25 用例:KPI ₽/危险态、ProductTable 排序+问题切换、漏斗断点高亮、KeywordInsight 判定标签/₽、DiagnosticBanner 核心卡数字+清单 等)。
- 端到端:三端点缺凭证均 400「未配置 Ozon 店铺凭证」✓;前端 build 出 Analytics chunk ✓。**真 Ozon 数据拉取需真凭证,由用户真环境验**。

## 变更历史
- 2026-06-28 **快捷时间预设 + 全部店铺并发聚合**:①前端 `RANGE_OPTS` 改 4 个预设(今天/昨天/近7天/近30天),`useAnalytics.setRange` 支持 `today`/`yesterday`(from=to=今天/昨天)+ `7`/`30`;②后端选「全部店铺」(store_client_id 空 + ≥2 店)→ `ThreadPoolExecutor` 并发聚合各店 dashboard/traffic/keywords(`dashboard_all/traffic_all/keywords_all`),缺凭证店跳过、全缺才 400。保留真连 API/TTL 缓存/CSV/单店切换。后端 +5 单测(753 passed),前端 +2 单测(setRange today/yesterday)。
- 2026-06-28 工程化落地(spec/plan 同名 docs/superpowers):后端 analytics service+router+adapter、前端 Analytics 页替占位。**前端最后一个占位页填上,店铺数据获取闭环。**
- 2026-06-28 对原型补真缺口(纯展示层,后端阈值/口径不动,保留真连 API/TTL 缓存/CSV 导出/多店切换):①货币 ¥→`₽`(KPI GMV、ProductTable 价格/收入、KeywordInsight GMV);②KpiCards 加购转化/GMV 危险态 + sub 文案(会话率%、N 次加购、N 单)+「总访问/会话」标签;③ProductTable 列排序(↓/↑,desc↔asc)、价格双行、问题切换按钮(计数+紫底)、行提示、诊断文案带操作建议;④DiagnosticBanner 改核心诊断卡(🚨+数字+排查清单+CTA);⑤ConversionFunnel 柱高缩放+每级备注+断点红高亮+「找到断点」副标题;⑥TrafficTrend 标题/副标题 + 紫/浅紫/橙三色;⑦KeywordInsight 行末判定标签 + 区块标题。
