# Ozon Performance API 集成参考

> 来源：官方文档页 `https://docs.ozon.ru/api/performance/zh/`，当前内置浏览器访问会触发 Ozon antibot；本文件基于 Context7 对 Ozon 官方文档的最近索引、Ozon for dev 域名迁移公告，以及页面暴露的 Performance API 路径整理。后续如能直接拿到官方 `swagger.json`，应以 swagger 为准刷新接口表。

## 1. 基础约定

- **当前域名**：`https://api-performance.ozon.ru`
- **旧域名**：`https://performance.ozon.ru`，Ozon 公告要求切换到新域名。
- **认证方式**：Performance API 使用独立的广告 API 凭证，不是 Seller API 的 `Client-Id` + `Api-Key`。
- **通用 Header**：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

### 获取 access token

```http
POST /api/client/token
Host: api-performance.ozon.ru
Content-Type: application/json
Accept: application/json
```

```json
{
  "client_id": "<performance_client_id>",
  "client_secret": "<performance_client_secret>",
  "grant_type": "client_credentials"
}
```

返回里取 `access_token`，后续请求放到 `Authorization: Bearer ...`。代码实现时建议做 token 缓存和过期前刷新，避免每个 API 请求都重新换 token。

## 2. 路径说明

官方文档和索引里同时出现过两类路径：

- 当前推荐：`/api/client/...`
- 旧式或文档片段路径：`/campaign...`、`/statistics...`、`/limits...`、`/search_promo...`

项目实现时优先使用 `/api/client/...` 版本；如果官方 swagger 或实测发现某个新方法只有无前缀路径，再单独映射。

## 3. Campaign 广告活动

| 方法 | 路径 | 用途 | 项目优先级 |
|---|---|---|---|
| `GET` | `/api/client/campaign` | 查询广告活动列表，支持 `campaignIds`、`advObjectType`、`state` 等筛选 | 高 |
| `GET` | `/api/client/campaign/available` | 查询可创建的广告活动模式 | 中 |
| `POST` | `/api/client/campaign/cpc/v2/product` | 创建 CPC 商品广告活动 | 中 |
| `POST` | `/api/client/campaign/cpm/v2/product` | 创建 CPM 商品广告活动 | 低 |
| `PATCH` | `/api/client/campaign/{campaignId}` | 修改广告活动参数 | 中 |
| `POST` | `/api/client/campaign/{campaignId}/activate` | 启用广告活动 | 中 |
| `POST` | `/api/client/campaign/{campaignId}/deactivate` | 停用广告活动 | 中 |
| `POST` | `/api/client/campaign/{campaignId}/v2/activate` | v2 启用广告活动，文档片段中出现 | 低 |
| `POST` | `/api/client/campaign/{campaignId}/v2/deactivate` | v2 停用广告活动，文档片段中出现 | 低 |
| `PUT` | `/api/client/campaign/{campaignId}/period` | 修改投放周期 | 中 |
| `GET` | `/api/client/campaign/{campaignId}/objects` | 查询活动内推广对象，适用于 CPC、Banner、Video Banner | 高 |
| `POST` | `/api/client/campaign/{campaignId}/products` | 向活动添加商品 | 中 |
| `PUT` | `/api/client/campaign/{campaignId}/products` | 更新活动商品配置/出价 | 中 |
| `POST` | `/api/client/campaign/{campaignId}/products/delete` | 从活动移除商品 | 中 |
| `GET` | `/api/client/campaign/{campaignId}/v2/products` | 查询活动商品，响应包含 `topPosition` 等新字段 | 高 |
| `POST` | `/api/client/campaign/{campaignId}/group` | 分组相关操作，文档片段中出现 | 低 |

常用查询示例：

```http
GET /api/client/campaign?advObjectType=SKU&state=CAMPAIGN_STATE_RUNNING
Host: api-performance.ozon.ru
Authorization: Bearer <access_token>
```

对本项目来说，第一阶段建议只读：拉活动列表、活动商品、活动推广对象，用于把广告消耗/活动状态合并进现有 `Analytics` 页。

## 4. Statistics 报表与统计

| 方法 | 路径 | 用途 | 备注 |
|---|---|---|---|
| `POST` | `/api/client/statistics` | 生成活动统计报表 | 返回 `UUID`，之后轮询/下载 |
| `POST` | `/api/client/statistics/json` | 生成 JSON 格式活动统计报表 | 适合服务端直接解析 |
| `GET` | `/api/client/statistics/{UUID}` | 根据 UUID 查询报表状态或结果 | 文档片段中出现 |
| `GET` | `/api/client/statistics/report?UUID=...` | 下载已生成报表 | 可能返回 CSV/ZIP/JSON |
| `GET` | `/api/client/statistics/list` | 查询报表任务列表 | 支持 `page`、`pageSize` |
| `GET` | `/api/client/statistics/externallist` | 查询外部统计报表列表 | 外部广告相关 |
| `GET` | `/api/client/statistics/daily` | 查询日维度统计 | 文档说明在 2026-01 有更新 |
| `GET` | `/api/client/statistics/expense` | 查询费用统计 | 文档说明在 2026-01 有更新 |
| `GET` | `/api/client/statistics/campaign/product` | 获取商品广告活动统计 | 支持 `dateFrom`、`dateTo`、多个 `campaignIds` |
| `GET` | `/api/client/statistics/campaign/media` | 获取媒体广告活动统计 | 用于 Banner/Video 等 |
| `POST` | `/api/client/statistics/products/sku` | 按 SKU 获取商品统计 | 适合商品维度分析 |
| `POST` | `/api/client/statistics/phrases` | 获取搜索词统计 | 可接入关键词洞察 |
| `POST` | `/api/client/statistics/video` | 获取视频广告展示统计 | 低优先级 |
| `GET` | `/api/client/statistics/all_sku_promo/orders/generate` | 生成“订单付款推广”订单报表 | 全商品推广 |
| `GET` | `/api/client/statistics/all_sku_promo/products/generate` | 生成“订单付款推广”商品报表 | 全商品推广 |
| `GET` | `/api/client/statistics/all_sku_promo/orders/generate/json` | 生成 JSON 订单报表 | 文档片段中出现 |

商品活动统计示例：

```http
GET /api/client/statistics/campaign/product?dateFrom=2024-08-01&dateTo=2024-08-07&campaignIds=11037395&campaignIds=11037396
Host: api-performance.ozon.ru
Authorization: Bearer <access_token>
```

典型指标字段包括：

- `campaignId`
- `sku`
- `views`
- `clicks`
- `ctr`
- `avgCpc`
- `moneySpent`
- `orders`
- `revenue`

落地建议：现有 `analytics_service.py` 已经有 Seller Analytics 的 TTL 缓存和多店并发模式，Performance 统计也应该走服务端缓存。报表生成接口可能异步，不能直接放到前端同步请求链里等到底。

## 5. Search Promo / Pay-per-Order

| 方法 | 路径 | 用途 | 备注 |
|---|---|---|---|
| `POST` | `/api/client/campaign/search_promo/v2/products` | 查询订单付款推广中的商品 | v2 当前优先 |
| `POST` | `/api/client/campaign/search_promo/v2/bids/set` | 设置搜索推广出价 | CPO/搜索推广 |
| `POST` | `/api/client/campaign/search_promo/v2/bids/delete` | 删除搜索推广出价 | 单次最多 1000 商品的限制在文档片段中出现 |
| `POST` | `/api/client/search_promo/bids/recommendation` | 获取推荐出价 | 出价优化 |
| `POST` | `/api/client/search_promo/get_cpo_min_bids` | 获取 CPO 最低出价 | 出价下限 |
| `POST` | `/api/client/search_promo/product/enable` | 启用商品订单付款推广 | 单品启用 |
| `POST` | `/api/client/search_promo/product/disable` | 停用商品订单付款推广 | 单品停用 |
| `GET` | `/api/client/campaign/all_sku_promo/activate` | 启用全商品订单付款推广 | 文档片段显示为 GET |
| `GET` | `/api/client/campaign/all_sku_promo/deactivate` | 停用全商品订单付款推广 | 文档片段显示为 GET |
| `GET` | `/api/client/campaign/all_sku_promo/set_bid` | 设置全商品推广出价 | 文档片段中出现 |
| `POST` | `/api/client/campaign/search_promo/carrots/enable` | 启用 Carrots 活动商品推广 | 低优先级 |
| `POST` | `/api/client/campaign/search_promo/carrots/disable` | 停用 Carrots 活动商品推广 | 低优先级 |

注意：`GET /api/client/campaign/{campaignId}/objects` 不适合 Pay-per-Order 活动，文档提示此类活动要用 `POST /api/client/campaign/search_promo/v2/products` 查询。

## 6. Limits / 出价边界 / 商品辅助接口

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/client/limits/list` | 查询出价限制，响应里的 `objectType`、`placement` 有过描述更新 |
| `POST` | `/api/client/min/sku` | 按 SKU 获取最低出价 |
| `GET` | `/api/client/products_with_bonuses` | 查询可参与奖金/优惠的商品 |

这些接口适合给“是否值得开广告”“当前出价是否过低/过高”做辅助判断，不建议第一版直接做自动调价。

## 7. 外部广告 / ORD / Vendor 相关

这组更偏外部广告素材、合同、平台、统计登记。项目当前如果只做 Ozon 店铺经营分析，可以先不接；如果后续做外部投放归因或广告合规，再补。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/client/organisation/vendor_tag?orgId=...` | 获取组织的 `UTM_CAMPAIGN` 标签前缀 |
| `POST` | `/api/client/vendors/statistics` | 生成/提交外部流量统计 |
| `POST` | `/external/api/dynamic_budget` | 计算或创建动态预算，含 `createCampaign` / `updateCampaign` 字段 |
| `POST` | `/api/external/v5/external_cid` | 注册外部 CID |
| `POST` | `/api/external/v5/external_cid/list` | 查询外部 CID 列表 |
| `POST` | `/api/external/creative` | 创建外部创意 |
| `GET` | `/api/external/creative/{externalCreativeId}` | 查询外部创意 |
| `POST` | `/api/external/contract` | 创建外部合同 |
| `GET` | `/api/external/v6/contract/{externalContractId}` | 查询外部合同 |
| `POST` | `/api/external/contract/{externalContractId}/creative` | 给合同绑定/创建创意 |
| `POST` | `/api/external/contract/{externalContractId}/invoice` | 给合同创建发票 |
| `GET` | `/api/external/v2/invoice/{externalInvoiceId}` | 查询外部发票 |
| `GET` | `/api/external/v6/organisation/{externalOrganisationId}` | 查询组织信息 |
| `GET` | `/api/external/v6/platform/{externalPlatformId}` | 查询投放平台 |
| `POST` | `/api/external/v6/statistic` | 添加外部统计 |
| `GET` | `/api/external/v6/statistic/{externalStatisticId}` | 查询外部统计 |
| `POST` | `/api/external/v4/statistic` | v4 外部统计提交 |
| `GET` | `/api/external/v4/statistic/{externalStatisticId}` | v4 外部统计查询 |

## 8. 和本项目的落地切法

### 第一阶段：只读分析

新增 `packages/ozon_api/src/ozon_api/performance_client.py` 或放入现有 client 包：

- `PerformanceClient.token()`
- `PerformanceClient.list_campaigns(...)`
- `PerformanceClient.campaign_products(campaign_id)`
- `PerformanceClient.campaign_product_stats(date_from, date_to, campaign_ids)`
- `PerformanceClient.search_phrases(...)`

后端服务层建议：

- 独立 `apps/webui/src/webui/services/performance_service.py`
- 复用 analytics 的日期范围、店铺选择和 TTL 缓存思路
- Performance 凭证单独配置，不混入 Seller API key
- 多店并发仍然用 bounded thread pool，但注意 Performance API 可能更严格限流

前端第一版可以在 Analytics 页面增加广告维度：

- 活动数、启用活动数、花费、广告 GMV、广告订单
- `ACOS = 花费 / 广告 GMV`
- `ROAS = 广告 GMV / 花费`
- 商品表增加广告花费、广告订单、广告 GMV、ACOS

### 第二阶段：辅助出价

接入：

- `/api/client/limits/list`
- `/api/client/search_promo/bids/recommendation`
- `/api/client/search_promo/get_cpo_min_bids`

只给建议，不自动提交 `bids/set`。

### 第三阶段：自动操作

在 UI 明确确认后才允许：

- activate / deactivate
- products add / delete
- bids set / delete
- all_sku_promo activate / deactivate

这些接口会改变广告投放状态和花费，必须有二次确认、审计日志和 dry-run 预览。

## 9. 实现风险

- **域名风险**：旧域名可能仍能查到博客示例，但项目必须用 `api-performance.ozon.ru`。
- **异步报表**：`/statistics` 类接口可能先返回 UUID，再下载报表；不要假设一次请求直接拿明细。
- **字段漂移**：`autopilot.skuAddMode`、`productAutopilotStrategy`、`topPosition`、`autoIncrease` 等字段在文档更新记录里出现过变化。
- **路径漂移**：部分片段显示无 `/api/client` 前缀。实现前对每个写操作必须用真实凭证在测试店铺小范围验证。
- **限流**：广告报表生成通常比 Seller Analytics 更重，服务端需要 TTL 缓存、队列或后台任务。
- **花费风险**：所有写接口默认禁用，只有用户在 UI 显式确认后才调用。
