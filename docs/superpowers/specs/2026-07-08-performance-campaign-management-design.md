# Ozon Performance 广告活动管理设计

## 背景

项目需要一个独立的“广告活动”一级页面，用来查看 Ozon Performance 广告活动下有哪些商品，并支持两类批量写操作：普通广告活动批量添加/移除商品，Search Promo/订单付款推广批量启用/停用商品推广。

该功能不放在“数据分析”下，不复用 Analytics 的页面 Tab。它可以复用多店选择、设置读取、服务端缓存和前端 API 调用风格。

## 目标

- 新增一级导航入口 `广告活动`。
- 支持按店铺查看 Performance 活动列表。
- 选中活动后查看该活动参与商品。
- 支持商品搜索：SKU、offer_id、商品名。
- 支持批量添加商品。
- 支持批量取消：
  - 普通广告活动：从活动中移除商品。
  - Search Promo/订单付款推广：停用商品推广。
- 所有写操作必须先预览，再确认提交。
- 返回逐 SKU/offer_id 的成功失败结果，允许部分失败。

## 非目标

- 不做整活动启用/停用。
- 不做自动调价。
- 不做自动创建广告活动。
- 不把功能塞进“数据分析”页面。
- 不在前端保存 Performance secret。

## 配置

系统设置新增：

- `performance_client_id`
- `performance_client_secret`

`GET /api/state` 只返回：

- `performance_client_id`
- `performance_client_secret_saved`

`POST /api/settings` 支持保存 secret；前端 secret 输入为空时保留已有值。

## 后端架构

新增 Performance API client，独立于 Seller API client：

- Base URL: `https://api-performance.ozon.ru`
- Token endpoint: `POST /api/client/token`
- 业务请求使用 `Authorization: Bearer <token>`
- token 在 client 实例内缓存到过期前刷新。

新增服务层 `performance_service.py`：

- `campaigns(settings) -> dict`
- `campaign_products(settings, campaign_id, campaign_type) -> dict`
- `operation_preview(settings, payload) -> dict`
- `operation_commit(settings, payload) -> dict`

新增 router `performance.py`：

- `GET /api/performance/campaigns`
- `GET /api/performance/campaigns/{campaign_id}/products`
- `POST /api/performance/operations/preview`
- `POST /api/performance/operations/commit`

多店逻辑复用现有 `_settings_for_store(store_client_id)` 模式，店铺通过 query `store_client_id` 传入。

## API 映射

普通广告活动：

- 列表：`GET /api/client/campaign`
- 商品：`GET /api/client/campaign/{campaignId}/v2/products`
- 添加商品：`POST /api/client/campaign/{campaignId}/products`
- 移除商品：`POST /api/client/campaign/{campaignId}/products/delete`

Search Promo / 订单付款推广：

- 商品：`POST /api/client/campaign/search_promo/v2/products`
- 启用：`POST /api/client/search_promo/product/enable`
- 停用：`POST /api/client/search_promo/product/disable`

如果官方响应字段和文档片段不一致，后端适配层必须保留原始 `raw` 字段，并尽量归一出前端稳定字段。

## 数据形状

活动：

```json
{
  "id": "11037395",
  "title": "Search CPC",
  "state": "CAMPAIGN_STATE_RUNNING",
  "adv_object_type": "SKU",
  "payment_type": "CPC",
  "is_search_promo": false,
  "products_count": 12,
  "raw": {}
}
```

商品：

```json
{
  "sku": "123456789",
  "offer_id": "ABC-001",
  "title": "Product title",
  "status": "active",
  "bid": "35",
  "raw": {}
}
```

操作：

```json
{
  "operation": "add_products",
  "campaign_id": "11037395",
  "items": [
    {"sku": "123456789", "offer_id": "ABC-001"}
  ]
}
```

允许的 `operation`：

- `add_products`
- `remove_products`
- `enable_search_promo`
- `disable_search_promo`

预览返回：

```json
{
  "operation": "remove_products",
  "campaign_id": "11037395",
  "campaign_title": "Search CPC",
  "count": 2,
  "items": [{"sku": "1"}, {"sku": "2"}],
  "warnings": []
}
```

提交返回：

```json
{
  "operation": "remove_products",
  "campaign_id": "11037395",
  "results": [
    {"sku": "1", "offer_id": "", "ok": true, "message": ""},
    {"sku": "2", "offer_id": "", "ok": false, "message": "not found"}
  ]
}
```

## 前端设计

新增 `views/PerformanceCampaigns.vue`。

页面布局：

- 顶部工具栏：店铺选择、刷新、搜索。
- 左侧/上方活动列表：活动名、状态、类型、商品数。
- 右侧/下方商品表：SKU、offer_id、商品名、状态、出价、多选框。
- 批量操作区：
  - 普通活动：添加商品、移除选中商品。
  - Search Promo：启用商品推广、停用选中商品推广。

批量添加入口：

- 弹窗 textarea，支持一行一个 SKU 或 offer_id。
- 前端按空白、逗号、换行切分，提交给 preview。
- preview 通过后，用户确认，再 commit。

## 安全与错误处理

- 写操作必须经过 preview。
- commit 请求里必须带 `preview_token` 或完整预览摘要；第一版用服务端重新校验 payload，避免复杂状态。
- 前端确认框显示活动名、操作、数量、前 10 个商品。
- 后端不允许未知 operation。
- 后端发现缺少 Performance 凭证时返回 400。
- 单个商品失败不导致整个批次失败；返回逐项结果。
- 网络/API 级失败返回 502/500，并在前端显示错误。

## 测试

后端：

- Performance client token 缓存、header、GET/POST 请求。
- service preview 校验 operation 和 items。
- service commit 将普通活动 remove 映射到 products/delete。
- service commit 将 search promo disable 映射到 product/disable。
- router 缺凭证返回 400。

前端：

- router 有 `广告活动` 路由和导航入口。
- 页面加载活动列表。
- 选择活动后加载商品。
- 搜索过滤商品。
- 批量操作先调用 preview，确认后调用 commit。

## 验收

- 访问 `#/campaigns` 能看到独立广告活动页面。
- 无 Performance 凭证时页面给出明确提示。
- 有 mock 数据时能加载活动和商品。
- 普通活动能批量添加/移除商品。
- Search Promo 能批量启用/停用商品推广。
- 所有写操作都有确认和逐项结果。
