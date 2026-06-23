# 仓库配送方式同步 + 展开查看 — 设计

日期：2026-06-21
状态：已确认，待实现

## 背景

「功能4 仓库」目前只同步仓库列表（`/v2/warehouse/list` → `warehouses` 表 → 仓库页表格 + 设默认仓）。
需要补上「仓库配置的配送方式」：从 `/v2/delivery-method/list` 拉取每个仓库下配置的配送方式（承运商/截单时间/状态等），
落库并在仓库页展开查看。

> Ozon 已将 `/v1/delivery-method/list` 标记废弃（2026-04-07 停用），强制迁 `/v2`。

本期范围：**只同步落库 + 仓库页展开展示**。不接入定价（PricingDialog 的 deliveryMethod）。

## 配送方式字段（Ozon 标准形状）

每条 delivery method：`id` / `name` / `status` / `warehouse_id` / `provider_id` / `cutoff`(截单时间) /
`sla_cut_in` / `template_id` / `created_at` / `updated_at`。每条都带 `warehouse_id`，按仓库分组。

## 请求/分页（v2 实测确认）

`POST /v2/delivery-method/list`，body（filter 各字段均为**数组**，warehouse_ids 等为**字符串**）：
```json
{
  "cursor": "string",
  "filter": {
    "delivery_method_ids": ["string"],
    "provider_ids": ["string"],
    "status": ["NEW"],
    "warehouse_ids": ["string"]
  },
  "limit": 1,
  "sort_dir": "ASC"
}
```
响应：`{ "result": [ ...delivery methods... ], "has_next": bool, "cursor": "..." }`，**cursor 游标翻页**（同 warehouse/list v2）。

## 同步流程

复用现有「从 Ozon 同步仓库」按钮（配送方式本就是仓库配置，不另加按钮）：
1. 先同步仓库（现状不变）。
2. 把本店所有仓库 ID 一次性放进 `filter.warehouse_ids`（转字符串），cursor 翻一遍即可——
   v2 filter 收数组，无需逐仓多次调用。每条返回带自身 `warehouse_id`，本地按它分组。
3. 按店**全量替换**配送方式（DELETE store_client_id 再 INSERT），Ozon 上被删/停用的本地随之消失。

## 数据模型

新表 `delivery_methods`（按店隔离 `store_client_id`）：

| 列 | 类型 | 说明 |
|---|---|---|
| delivery_method_id | INTEGER PK | Ozon `id` |
| warehouse_id | INTEGER | 所属仓库 |
| name | TEXT | 配送方式名 |
| status | TEXT | 状态 |
| provider_id | INTEGER | 承运商 |
| cutoff | TEXT | 截单时间 |
| sla_cut_in | INTEGER | |
| template_id | INTEGER | |
| tpl_integration_type | TEXT | 如 aggregator |
| is_express | INTEGER | 0/1，列表返回转 bool |
| dropoff_name | TEXT | 自提点(PUDO)名称 |
| dropoff_code | TEXT | 自提点编码 |
| dropoff_address | TEXT | **自提点地址（用户最关心）** |
| dropoff_lat / dropoff_lng | REAL | 自提点坐标 |
| created_at | TEXT | Ozon 侧 |
| updated_at | TEXT | Ozon 侧 |
| fetched_at | TEXT | 本地同步时间 |
| store_client_id | TEXT | 店隔离 |
| raw_json | TEXT | 原始 payload（前向兼容） |

- store.py（SQLite）`init()` 加 CREATE TABLE；db.py（MySQL）`MYSQL_DDL` 加对应建表。
- 删店清理：接进现有 `("warehouses","postings","procurement","offer_snapshots")` 列表。
- 旧行回填：新表无历史行，`_migrate_store_scoped_aux` 可选加入（幂等，无害）。

## 后端改动

- `ozon_api/client.py`：`list_delivery_methods(self, *, warehouse_ids=None, provider_ids=None, delivery_method_ids=None, status=None, cursor="", limit=100, sort_dir="ASC")` → POST `/v2/delivery-method/list`，filter 只放非空字段（数组、字符串化）。
- `backend/ozon_client_adapter.py`：`fetch_delivery_methods(settings, warehouse_ids)` → 一次传全部 warehouse_ids + cursor 翻页 + 归一成 store 入参形状。
- `backend/store.py`：`replace_delivery_methods(items, store_client_id)`、`list_delivery_methods(store_client_id)`；建表 + 清理列表接入。
- `backend/app_service.py`：`sync_warehouses` 末尾追加拉配送方式并替换；`list_warehouses` 给每个仓库挂 `delivery_methods: [...]`（本地按 warehouse_id 分组）。返回的 sync 摘要补 `delivery_methods` 计数。

> 不新增 HTTP 路由：同步并入 `/api/warehouses/sync`，展示并入 `/api/warehouses`。

## 前端改动

`frontend/src/views/Warehouses.vue`：
- el-table 加可展开行（`type="expand"`），展开显示该仓库 `delivery_methods` 子表：名称 / 承运商(provider_id) / 状态 / cutoff。
- 同步成功提示改为「N 个仓库 / M 个配送方式」。

## 测试

- `ozon_api/tests/test_seller_client.py`：加 `list_delivery_methods` 端点/body 断言。
- `ozon-listing-webui/tests/test_warehouses_api.py`：
  - 假 client 返回配送方式 → `fetch_delivery_methods` 翻页/遍历正确。
  - `replace_delivery_methods` / `list_delivery_methods` 按店隔离 + 全量替换（旧行被清）。
  - `/api/warehouses/sync` 后 `/api/warehouses` 每个仓库挂上正确分组的 `delivery_methods`。
- `ozon-listing-webui/tests/smoke_delivery_methods_live.py`：对真实 v2 接口验证字段与翻页（需真实凭证，手动跑）。
