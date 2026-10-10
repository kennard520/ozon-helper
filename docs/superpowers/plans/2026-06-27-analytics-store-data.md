# 店铺数据分析（Analytics）工程化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。后端 port 真实脚本逻辑（TDD 覆盖纯函数 + router 形状），前端按 F 模式建页。

**Goal:** 把 `E:\personal\kuajing\tools\ozon-listing-webui\scripts` 的 `sku_dashboard.py`/`sku_traffic_report.py`/`sku_keywords_report.py` 工程化:后端 service+router 拉 Ozon 店铺数据,前端「数据分析」页(现占位)渲染原型(诊断/漏斗/KPI/商品表现·流量趋势·搜索词三 tab)。

**Architecture:** 见 spec `docs/superpowers/specs/2026-06-27-analytics-store-data-design.md`。**不碰 App god-class**:独立 `services/_analytics.py`(纯函数)+ `routers/analytics.py` + `ozon_client_adapter` 加 analytics 封装。多店复用 `_settings_for_store`。进程内 TTL 缓存,无 Redis。

**命令**:后端 `python -m uv run python -m pytest apps/webui/tests -q`(≥530 不降);前端 `npm run test`(≤32 基线,实为 5)。

---

### Task 1: 后端 —— analytics 封装 + service + router + api.js

**Files:**
- Modify: `apps/webui/src/webui/ozon_client_adapter.py`（加 analytics 拉取函数）
- Create: `apps/webui/src/webui/services/analytics_service.py`
- Create: `apps/webui/src/webui/routers/analytics.py`
- Modify: `apps/webui/src/webui/main.py`（include_router）
- Modify: `apps/webui/frontend/src/api.js`
- Test: `apps/webui/tests/test_analytics_service.py`

**先读真实脚本**（务必照搬其 Ozon API 调用细节：端点/payload/翻页/429重试/降级）：
`E:\personal\kuajing\tools\ozon-listing-webui\scripts\sku_dashboard.py`（主:list/info/prices/stocks/analytics 五接口 + build_rows 合并 + conv 计算）、`sku_traffic_report.py`（analytics dim=[sku,day]）、`sku_keywords_report.py`（product-queries/details）。参考目标 app 已有 `apps/webui/src/webui/analytics_report.py`(单店 analytics 拉取范例) + `ozon_client_adapter.py`(build_client/OzonSellerClient.request 范式)。

- [ ] **Step 1: ozon_client_adapter.py 加 analytics 拉取**（纯函数,收 `client`）：
  - `fetch_analytics_sku(client, date_from, date_to)` → `{rows:[{sku, exposure, sessions, cart, ordered_units, revenue}], degraded:bool}`：POST `/v1/analytics/data` dimension=[sku] metrics=[hits_view,session_view,hits_tocart,ordered_units,revenue]；403 降级(只下单/收入,degraded=True)；429 等 60s 重试(参 sku_dashboard.fetch_analytics)。
  - `fetch_analytics_traffic(client, date_from, date_to)` → `{rows:[{sku, day, hits_view, session_view, hits_tocart, ordered_units}]}`：dimension=[sku,day]。
  - `fetch_product_queries(client, date_from, date_to)` → `{by_sku:{sku:[{query, searches, ctr, position, orders, gmv}]}}`：POST `/v1/analytics/product-queries/details` page 翻页(参 sku_keywords_report)。
  - 商品 list/info/prices/stocks：复用已有 `list_ozon_products`/`get_ozon_info`；prices(v5)/stocks(v4) 若 adapter 无则补 `fetch_prices`/`fetch_stocks`(参脚本)。
  - 都用 `client.request(path, payload)`；分页/重试照脚本。

- [ ] **Step 2: 写失败测试** `apps/webui/tests/test_analytics_service.py`（纯函数,mock client）:
```python
import unittest


class FakeClient:
    def __init__(self, responses): self.responses = responses; self.calls = []
    def request(self, path, payload):
        self.calls.append((path, payload))
        return self.responses.get(path, {})


class AnalyticsServiceTest(unittest.TestCase):
    def test_build_dashboard_rows_merges_and_diagnoses(self):
        from webui.services.analytics_service import build_dashboard_rows
        infos = {"OFF1": {"sku": 101, "title": "杯", "price": 100, "stock": 0}}   # 缺货
        funnel = {101: {"exposure": 500, "sessions": 0, "cart": 0, "ordered_units": 0, "revenue": 0}}  # 0访问
        rows = build_dashboard_rows(infos, funnel)
        r = rows[0]
        self.assertEqual(r["sku"], 101)
        self.assertIn("缺货", r["diagnostics"])           # stock=0
        self.assertEqual(r["conv_cart_pct"], 0)
        # 高曝光0下单 → 诊断标签
        self.assertTrue(any("曝光" in d or "转化" in d for d in r["diagnostics"]))

    def test_dashboard_degraded_flag(self):
        from webui.services.analytics_service import dashboard
        # mock build_client + fetch_*，验 degraded 透传 + grand_total 聚合（按实际实现写;
        # 若 dashboard 直接拉 API 难 mock,可只单测 build_dashboard_rows + grand_total 纯函数）
        pass
```
> 实现时按 `analytics_service` 的真实拆分调整测试（核心:`build_dashboard_rows(infos, funnel)` 纯函数——合并商品信息+漏斗、算 conv_cart_pct、打诊断标签[缺货/0曝光/高曝光0转化/加购未转化]；`grand_total` 聚合纯函数）。至少覆盖诊断逻辑 + conv 计算 + 聚合。

- [ ] **Step 3: 跑红** `python -m uv run python -m pytest apps/webui/tests/test_analytics_service.py -q` → FAIL

- [ ] **Step 4: 实现 `services/analytics_service.py`**（纯函数 + 编排,不进 App）：
  - `build_dashboard_rows(infos, funnel) -> list[dict]`:合并 + conv_cart_pct = cart/sessions*100(防 0) + `diagnostics` 标签:`stock<=0→"缺货"`、`exposure<=0→"0曝光"`、`exposure>200 and ordered==0→"高曝光0转化"`、`cart>0 and ordered==0→"加购未转化"`。
  - `grand_total(rows) -> dict`:汇总 exposure/sessions/cart/ordered/revenue + 整体 conv。
  - `dashboard(settings, date_from, date_to) -> dict`:build_client → list offers → get info/prices/stocks → fetch_analytics_sku → build_dashboard_rows + grand_total → `{store, date_from, date_to, grand_total, rows, degraded}`。
  - `traffic(settings, date_from, date_to)`、`keywords(settings, date_from, date_to)` 同理。
  - **进程内 TTL 缓存**:模块级 `_cache={}`,key=`(store_client_id, kind, date_from, date_to)`,dashboard/traffic 600s、keywords 21600s。`_now` 注入便于测试(或用传入时间戳)。
  - 缺凭证 → raise ValueError("未配置 Ozon 店铺凭证")。

- [ ] **Step 5: 实现 `routers/analytics.py`**：
```python
from fastapi import APIRouter, HTTPException
from webui import app_instance
from webui.services import analytics_service

router = APIRouter()

def _settings(store_client_id):
    APP = app_instance.APP
    return APP._settings_for_store(store_client_id) if store_client_id else APP.store.get_settings()

@router.post("/api/analytics/dashboard")
def analytics_dashboard(body: dict) -> dict:
    b = body or {}
    try:
        return analytics_service.dashboard(_settings(b.get("store_client_id")),
                                           b.get("date_from") or "", b.get("date_to") or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# 同式 /api/analytics/traffic、/api/analytics/keywords
```
  main.py 顶部 `from webui.routers import analytics as analytics_router` + `app.include_router(analytics_router.router)`（在其它 include 之后）。

- [ ] **Step 6: api.js 加方法**：
```js
  analyticsDashboard: (p) => req('POST', '/api/analytics/dashboard', p),
  analyticsTraffic: (p) => req('POST', '/api/analytics/traffic', p),
  analyticsKeywords: (p) => req('POST', '/api/analytics/keywords', p),
```

- [ ] **Step 7: 跑绿 + 回归 + 提交**
  - `python -m uv run python -m pytest apps/webui/tests/test_analytics_service.py -q` PASS。
  - `python -m uv run python -m pytest apps/webui/tests -q` ≥530 不降；`python -c "import webui.main"` 冒烟。
  - commit `feat(analytics): 后端 analytics service+router(SKU漏斗/流量/搜索词,多店,TTL缓存)+ adapter拉取 + api.js`。

---

### Task 2: 前端 —— Analytics.vue + 子组件 + composable 替占位

**Files:**
- Create: `apps/webui/frontend/src/views/Analytics.vue`
- Create: `apps/webui/frontend/src/composables/useAnalytics.js`
- Create: `apps/webui/frontend/src/components/analytics/{DiagnosticBanner,ConversionFunnel,KpiCards,ProductTable,TrafficTrend,KeywordInsight}.vue`
- Modify: `apps/webui/frontend/src/router/index.js`（analytics 指向 Analytics.vue）
- Test: `apps/webui/frontend/src/composables/useAnalytics.test.js` + 关键组件 test

参考原型 `C:\Users\42918\Desktop\右侧变体卡片展示设计\数据分析.dc.html`（诊断banner+转化漏斗+KPI cards+三tab[商品表现/流量趋势/搜索词洞察]）。用设计系统(tokens/S 组件)。

- [ ] **Step 1: `useAnalytics.js`**（TDD）:`useAnalytics()` → `{loading, store, dateRange, dashboard, traffic, keywords, load(), setRange(), exportCsv()}`;`load` 调三 api(dashboard 必拉,traffic/keywords tab 切换时懒拉);store 列表从 `appStore.settings.ozon_stores`。测试 mock api 验 load 调 analyticsDashboard、range 切换重拉、exportCsv 生成 CSV 字符串。
- [ ] **Step 2: 子组件**（轻量,纯展示 props）:ConversionFunnel(4段漏斗)、KpiCards(总曝光/访问/加购转化/GMV)、ProductTable(SKU表+诊断标签+「仅看问题商品」筛选+点行 emit 跳草稿)、TrafficTrend(日柱状)、KeywordInsight(机会/污染/已覆盖+词表)、DiagnosticBanner。各配 1-2 个渲染 test。
- [ ] **Step 3: `Analytics.vue`**:页头(店铺下拉+时间范围+导出)+ DiagnosticBanner + ConversionFunnel + KpiCards + STabs(商品表现/流量趋势/搜索词)+ 对应内容区。wires useAnalytics。无 Premium/缺凭证 → 友好提示(从后端 degraded/400)。
- [ ] **Step 4: 路由替占位**:`router/index.js` 把 `analytics` 的 `component: () => import('../views/Placeholder.vue')` 改成 `import('../views/Analytics.vue')`。
- [ ] **Step 5: 全量 + 提交**:`npm run test`(≤32 基线不增)+ `npm run build`。commit `feat(analytics): 数据分析页(Analytics.vue+子组件+useAnalytics)替占位,接后端三接口`。

---

### Task 3: 文档 + 收尾验收

- [ ] **Step 1**：建 `docs/product/analytics.md`(模块文档:交互[页头/诊断/漏斗/KPI/三tab/导出]、数据[三接口形状+Ozon来源+多店+TTL缓存+诊断规则]、规则[降级/限速/T+1滞后/缺凭证400])。`docs/product/workbench.md` 不涉及;若有总导航文档加链接。
- [ ] **Step 2**：端到端验收:起后端(无真 Ozon 凭证)→ curl `/api/analytics/dashboard` 应返 **400「未配置 Ozon 店铺凭证」**(验缺凭证路径 + 不 500);前端 `npm run build` + 浏览器看 Analytics 页渲染骨架 + 缺凭证友好提示。真凭证下的真数据拉取由用户在真环境验(注明)。
- [ ] **Step 3**：提交 `docs(product): analytics 模块文档 + 收尾验收`。

---

## Controller 复核
- Task1 后:读 diff(adapter 拉取照脚本、service 纯函数+缓存、router 用活属性 APP)、跑 analytics 单测 + 530 回归不降 + import 冒烟。
- Task2 后:`npm run test` ≤32 + build。
- 全部后:起后端 curl 缺凭证 400 + 前端 build + 浏览器骨架。真 Ozon 数据需真凭证,注明由用户真环境验。
