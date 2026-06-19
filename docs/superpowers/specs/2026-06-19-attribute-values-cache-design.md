# 设计：类目属性字典值本地缓存 + 本地映射 + 并发兜底

- 日期：2026-06-19
- 状态：设计已确认，待写实现计划
- 影响范围：`ozon-listing-webui` 后端（`app_service` / `store`）+ `ozon_api/client`，部署在服务器（MySQL，Docker）

## 背景 / 问题

采集后"自动映射属性"（`auto_map_attributes` / `_auto_map_safe`）实测 **21.7 秒**（服务器日志 `[cp] auto_map 21.70s`），是采集卡顿（曾误报"连不上后端"）的真正主因。

根因：`app_service._resolve_values` 对**每个字典型属性**，拿采集到的俄文值，**逐个、串行**调 Ozon `/v1/description-category/attribute/values/search`（带关键词搜）解析出 `dictionary_value_id`。服务器在北京、Ozon API 在俄罗斯，**每次跨境往返约 0.5~1 秒**，几十个属性累加 20+ 秒，而且**完全没有缓存**，每次采集都重新问一遍。

对比：类目匹配（`auto_match`）走本地缓存只要 0.06s——属性映射慢就慢在"值"没有本地化。

## 目标

- 把属性映射从"每个值都跨境问 Ozon"改成"**本地匹配为主、极少数才问**"。
- 优化后把自动映射**放回采集流程**：首次采某新类目拉一次字典稍慢、之后该类目采集秒级。

## 非目标

- **不**预先全量拉取 Ozon 全部 7000+ 类目（数据量 GB+、绝大多数用不到）；只**按需**缓存实际采集到的类目。
- **不**改品牌处理：继续跳过品牌映射、统一填"无品牌"（现状）。
- **不**做主动定时刷新（字典值很少变；保留 `fetched_at` 字段作未来手动/定时刷新的扩展点，本期不实现）。

## 方案

### 采集时的数据流（`auto_map_attributes`）

```
定类目（已有 auto_match，~0.06s）
  └→ 拉该类目属性表（已有 category_attr_cache 缓存）
      └→ 对每个「字典型」属性（attr.dictionary_id 非空）：
          ├ 品牌(attr 85) → 跳过映射，填「无品牌」(现状不变)
          ├ 本地有该属性字典值缓存？
          │   ├ 有     → 直接本地 map（俄文精确匹配，0 次网络）
          │   └ 无     → 调 get_attribute_values 拉全量字典值存库，再本地 map
          │              └ 累计超 2000 条 → 标 oversized，不缓存
          └ 本地没 map 上 / oversized → 收集到「待兜底」列表
      └→ 「待兜底」的值 → 并发 search_attribute_values（线程池，限 5~8 并发）
```

本地 map 规则：沿用现有"精确匹配优先"（俄文 `strip().lower()` 相等优先，否则不命中→进兜底），与现 `_resolve_values` 行为一致。

### 数据模型：新缓存表 `category_attr_values_cache`

| 列 | 类型 | 说明 |
|---|---|---|
| `description_category_id` | INT | 联合主键 |
| `type_id` | INT | 联合主键 |
| `attribute_id` | INT | 联合主键 |
| `language` | VARCHAR | 联合主键，固定 `'RU'`（采集是俄文，按俄文 map） |
| `values_json` | LONGTEXT/TEXT | 全量字典值 `[{"id":int,"value":str}]`；oversized 时存 `[]` |
| `oversized` | INT/TINYINT | 1=字典太大、未缓存、走实时搜 |
| `fetched_at` | INT/TIMESTAMP | 拉取时间（留作未来刷新） |

迁移：MySQL `CREATE TABLE IF NOT EXISTS` + SQLite 对应建表（沿用现有 `catalog_cache` 的双方言模式）。

### 新增 Ozon client 方法

`ozon_api/client.py` 新增 `get_attribute_values(description_category_id, type_id, attribute_id, *, language="RU", page_limit=2000)`：
- 打 `POST /v1/description-category/attribute/values`；
- 用 `last_value_id` + `has_next` 分页循环拉取；
- 累计条数 **> page_limit（2000）** 即停止并返回 `oversized=True`（连同已拉到的部分一起返回，调用方据此决定不缓存）；
- 返回结构：`{"values": [{"id","value"}...], "oversized": bool}`。

### 改动点

- `ozon_api/client.py`：加 `get_attribute_values`（分页 + 阈值保护）。
- `store`（`db.py`/`store.py`）：加 `load_attr_values(cat,typ,attr_id,lang)` / `save_attr_values(cat,typ,attr_id,lang,values,oversized)`；新表建表逻辑。
- `app_service`：
  - 新增"确保某属性字典值在本地"的方法（缓存命中直接返回；未命中拉全量并存；oversized 标记）。
  - `_resolve_values` 重构为：**先本地 map（用缓存的全量值列表）→ 没命中/oversized 才进兜底**。
  - `auto_map_attributes`：把字典属性的解析改成"本地批量 map + 收集未命中 → 并发 search 兜底"。
- `app_service.ext_collect_parsed`：**恢复**两处 `_auto_map_safe(...)` 调用（采集后自动映射放回采集流程）。

### 并发

兜底的 `search_attribute_values` 用 `concurrent.futures.ThreadPoolExecutor`，并发数限 **5~8**（防 Ozon 限流）。只对"本地没 map 上"的少数值发起，正常情况下兜底很少甚至为 0。

### 回退 / 边界（全程 best-effort）

- 拉全量字典值失败（限流/网络/超时）→ 该属性回退实时 `search`，不阻断；
- 没配 Ozon key → 跳过映射（现状）；
- `_resolve_values` / `auto_map` 任何异常都不影响草稿建好（`_auto_map_safe` 本就是 try/except 包裹）。

## 测试

- 缓存命中：本地有字典值时，map 过程**不调** Ozon（mock client 断言 0 次 search/values 调用）。
- 缓存未命中：首次拉全量字典值并写入 `category_attr_values_cache`，第二次走本地。
- oversized：拉取超 2000 条 → 标 oversized、不缓存 → 该属性走实时 search。
- 并发兜底：本地没命中的值通过并发 search 解析（断言调用次数 = 未命中数）。
- 品牌：attr 85 跳过映射、`brand_name` 填"无品牌"（现状回归不破坏）。
- 拉取失败回退：`get_attribute_values` 抛错时退回实时 search，不抛给采集流程。
- 采集回归：`ext_collect_parsed` 恢复 auto_map 后仍返回 `{created:[...]}`，且耗时在有缓存时 < 1s。

## 部署 / 迁移

- 新表 `category_attr_values_cache` 启动时自动建（MySQL/SQLite 双方言）。
- 本地 `npm test`（前端无关）+ 后端单测通过 → 重建镜像 → 重启 `ozon-webui` 容器。
- 已迁移的旧数据无需处理；缓存表为空，首次采集各类目时自然填充。

## 预期效果

- 首次采某新类目：拉该类目各字典属性的全量值（可并发拉），约几秒；
- 之后采同类目：属性 map 全本地，采集总耗时 < 1s；
- 兜底 search 仅在本地没匹配上时触发，数量极少。
