# 店铺数据分析（Analytics）工程化设计

**日期**：2026-06-27　**分支**：feat/auto-listing-ai-pipeline

## 目标
把旧脚本 `sku_dashboard.py`/`sku_keywords_report.py`/`sku_traffic_report.py`（在 `E:\personal\kuajing\tools\ozon-listing-webui\scripts`）工程化进 app：后端正式 service + router 拉 Ozon 店铺数据，前端「数据分析」页（现占位）渲染原型（诊断 banner + 转化漏斗 + KPI + 商品表现/流量趋势/搜索词洞察三 tab）。

## 数据源（Ozon API，已确认）
| 数据 | 端点 | 维度/要点 |
|---|---|---|
| 全 offer 列表 | `POST /v3/product/list` | last_id 翻页 limit 1000 |
| 商品信息(标题/价/划线价) | `POST /v3/product/info/list` | 按 offer_id 批 1000 |
| 活动价 | `POST /v5/product/info/prices` | cursor 翻页（marketing_seller_price） |
| 库存 | `POST /v4/product/info/stocks` | cursor 翻页（present 求和） |
| SKU 漏斗 | `POST /v1/analytics/data` dimension=[sku] | metrics: hits_view/session_view/hits_tocart/ordered_units/revenue；**每店每分钟限 1 次(429 等 60s)**；无 Premium 降级(403→只下单/收入) |
| SKU×日 流量 | `POST /v1/analytics/data` dimension=[sku,day] | 日级趋势 |
| 搜索词 | `POST /v1/analytics/product-queries/details` | page 翻页；**date_to ≤ 今天-3**；稀疏(隐私阈值) |

## 复用的现有基建
- `ozon_client_adapter.build_client(settings)` → `OzonSellerClient`；`client.request(path, payload)` 通用 POST（自动 Client-Id/Api-Key header、429 抛 OzonApiError）。
- 多店：`settings.ozon_stores=[{name,client_id,api_key,is_default}]`；`App._settings_for_store(store_client_id)` 取目标店 settings；`mirror_of/normalize_stores` 已有。
- 凭证脱敏 state() 已有，前端拿得到店铺列表(name/client_id/is_default)。

## 架构（不碰 App god-class）
1. **`ozon_client_adapter.py` 加 analytics 封装**（纯函数，收 `client`）：
   - `fetch_analytics_sku(client, date_from, date_to, *, premium=True)` → `{rows:[{sku,...}], degraded:bool}`（403 降级、429 重试）。
   - `fetch_analytics_traffic(client, date_from, date_to)` → SKU×day。
   - `fetch_product_queries(client, date_from, date_to)` → 搜索词。
   - （list/info/prices/stocks 已有或补：`list_ozon_products`/`get_ozon_info` 已有；prices(v5)/stocks(v4) 若无则补。）
2. **`services/analytics_service.py`（新建，纯函数）**：编排——拿 settings → build_client → 拉 offers/info/prices/stocks/analytics → `build_dashboard_rows()` 合并 + 算 `conv_cart_pct` + **诊断标签**（缺货/0曝光/转化失效）→ 返回 `{store, date_from, date_to, grand_total, rows, degraded}`。`traffic()`/`keywords()` 同理。多店经 `_settings_for_store`。
   - **轻量缓存**：进程内 `{(store,kind,date_from,date_to): (ts, data)}` TTL（漏斗/趋势 10min、搜索词 6h），避开 analytics 限速 + 快速翻页。无 Redis。
3. **`routers/analytics.py`（新建）**：
   - `POST /api/analytics/dashboard` body `{date_from, date_to, store_client_id?}` → service.dashboard。
   - `POST /api/analytics/traffic` `{date_from, date_to, store_client_id?}`。
   - `POST /api/analytics/keywords` `{date_from?, date_to?, store_client_id?}`（默认 30 天到今天-3）。
   - 用活属性 `app_instance.APP`（取 settings/_settings_for_store）。`main.py` include_router。
   - 缺凭证/未配店 → 友好 400「先在系统设置配 Ozon 店铺凭证」。
4. **前端**：`views/Analytics.vue` 替 `Placeholder`（router analytics 改指向）+ `components/analytics/` 子组件（DiagnosticBanner/ConversionFunnel/KpiCards/ProductTable/TrafficTrend/KeywordInsight）+ `composables/useAnalytics.js`（拉三接口、店铺/时间范围选择、CSV 导出）。api.js 加 `analyticsDashboard/analyticsTraffic/analyticsKeywords`。设计系统(tokens/S 组件)。

## 诊断逻辑（后端算，前端展示）
每 SKU 标签：`缺货`(stock=0 或 <阈值)、`0曝光`(exposure=0)、`高曝光0转化`(exposure>N 且 ordered=0)、`加购未转化`(cart>0 且 ordered=0)。banner = 全店最突出问题摘要。

## 交互
- 进页 → 拉 dashboard(默认近30天 + 默认店)。店铺下拉(多店)、时间范围(近7/30/自定义)。
- 三 tab：商品表现(表格+「仅看问题商品」筛选+点行跳草稿)、流量趋势(日柱状)、搜索词洞察(机会/污染/已覆盖 + 词表)。
- 导出 CSV(前端从已拉数据生成)。
- 无 Premium → 流量指标列显「需 Premium」、只展示下单/收入。

## 范围/降级
- 不引 Redis/Celery；进程内 TTL 缓存。后台定时预拉 = 可选后续。
- 搜索词数据滞后/稀疏属正常，UI 注明。
- 数据 T+1~2 滞后，页头注明。

## 测试
- 后端：`analytics_service.build_dashboard_rows` 合并+诊断纯函数单测（喂假 API 返回，验 conv/标签）；router mock client 验三端点形状 + 缺凭证 400。
- 前端：useAnalytics 拉数/范围切换/CSV；组件渲染漏斗/表格/标签。
- 真 Ozon 拉取需真凭证 → 验收时若无凭证，验「缺凭证 400 + 前端友好提示」即可，逻辑用 mock 单测覆盖。

## 落点不在本设计
- 系统设置页加「Ozon 店铺凭证」编辑(若 F2 设置页未覆盖)——并入 F2 设置页。
