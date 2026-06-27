# 数据分析（Analytics）

> 店铺经营数据看板:把 Ozon 店铺的 SKU 漏斗/流量趋势/搜索词工程化进 app。前端「数据分析」页(`/analytics`,`views/Analytics.vue`)。源自旧脚本 `sku_dashboard/traffic/keywords` 工程化。

## 1. 交互
页头:**店铺下拉**(多店,来自 `settings.ozon_stores`)+ **时间范围**(近7/30/自定义)+ **导出**(CSV)。
- **诊断 banner**(`DiagnosticBanner`):全店最突出问题 / degraded(无 Premium)提示。
- **转化漏斗**(`ConversionFunnel`):曝光 → 访问 → 加购 → 下单 四段。
- **KPI cards**(`KpiCards`):总曝光 / 总访问 / 加购转化 / GMV(SStatCard)。
- **三 tab**(STabs):
  - **商品表现**(`ProductTable`):SKU 表(价/库存/曝光/访问/加购/下单/收入)+ 诊断标签(SBadge)+「仅看问题商品」筛选 + 点行 `open-draft`(跳工作台)。
  - **流量趋势**(`TrafficTrend`):按 day 的曝光/访问/加购柱状(纯 CSS)。
  - **搜索词洞察**(`KeywordInsight`):机会/污染/已覆盖三卡 + 搜索词表。
- 缺凭证 / degraded → `SAlert` 友好提示「请先在系统设置配置 Ozon 店铺凭证」。

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
- 多店:`store_client_id` → `_settings_for_store`(复用 `settings.ozon_stores`)。

## 3. 规则
- **诊断标签**(后端算):`缺货`(stock≤0)、`0曝光`(exposure≤0)、`高曝光0转化`(exposure>200 且 ordered=0)、`加购未转化`(cart>0 且 ordered=0)。`conv_cart_pct`=cart/sessions×100(防零)。
- **降级**:无 Premium → `/v1/analytics/data` 403 → 只取 ordered_units/revenue,`degraded=True`,前端流量列标降级。
- **限速**:analytics 每店每分钟 1 次 → 429 等 ~60s 重试。
- **进程内 TTL 缓存**(`analytics_service._cache`):dashboard/traffic 600s、keywords 21600s(避开限速+快速翻页)。无 Redis。
- **滞后**:数据 T+1~2;搜索词 date_to ≤ 今天-3 且稀疏(隐私阈值)。页头/UI 注明。
- **缺凭证** → 400「未配置 Ozon 店铺凭证」(不 500)。

## 4. 测试与验收
- 后端 33 单测(build_dashboard_rows 诊断/conv、grand_total 聚合、adapter mock 解析/降级/分页、缓存 TTL、router 缺凭证 400);前端 26 用例(useAnalytics 拉数/懒拉/范围/导出 + 6 组件渲染)。
- 端到端:三端点缺凭证均 400「未配置 Ozon 店铺凭证」✓;前端 build 出 Analytics chunk ✓。**真 Ozon 数据拉取需真凭证,由用户真环境验**。

## 变更历史
- 2026-06-28 工程化落地(spec/plan 同名 docs/superpowers):后端 analytics service+router+adapter、前端 Analytics 页替占位。**前端最后一个占位页填上,店铺数据获取闭环。**
