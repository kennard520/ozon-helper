# Ozon 商品同步与 SKU 单品导入设计

## 背景

系统已经具备 Ozon 全店商品拉取的后端雏形：`OzonSellerClient` 可按 `offer_id` 或 `product_id` 获取商品，`ozon_client_adapter.ozon_to_draft()` 可将商品详情和属性转换为本地草稿，`PublishMixin.pull_ozon_products()` 已实现全店列表拉取、描述补全和非破坏式合并。

本次在现有能力上补齐以下闭环：

- 输入 Ozon 数字 SKU，单独导入当前店铺中的一个商品。
- 将导入商品作为现有商品草稿编辑。
- 修改后使用原 `offer_id` 发布，更新 Ozon 上的原商品。
- 支持当前店铺全量或增量同步，并确保多店铺数据隔离。
- 重复同步时保留本地编辑，通过差异确认选择性采用远端内容。

## 目标与非目标

### 目标

1. 在商品草稿页提供按数字 SKU 导入入口。
2. 导入标题、描述、类目、类型、属性、价格、库存、重量、尺寸、图片和视频。
3. 同一用户、同一店铺、同一 Ozon 商品重复导入时保持幂等。
4. 已存在草稿不被同步静默覆盖；Ozon 身份信息可以安全刷新。
5. 发布时沿用原 `offer_id` 和 `product_id`，更新原商品。
6. SKU 属于变体组时默认只导入指定 SKU，并在发布前提示整组要求。
7. 修正现有全店拉取逻辑的店铺作用域。

### 非目标

- 本期不新增独立的“Ozon 商品库”表和管理页面。
- 本期不自动导入指定 SKU 的所有兄弟变体。
- 本期不绕过现有发布预检、媒体托管或必填属性校验。
- 本期不做定时后台同步；保留后续增加调度器的接口边界。

## 总体架构

### Ozon API 客户端

扩展 `OzonSellerClient.get_products_info()`，新增 `skus` 参数。调用 `/v3/product/info/list` 时，`offer_ids`、`product_ids`、`skus` 三种标识符只选一种构造请求体。

现有属性和描述接口继续按查询结果中的 `offer_id` 拉取，不创建第二套映射逻辑。

### 服务层

把 Ozon 拉取和草稿转换整理到独立 `OzonSyncMixin`，并复用以下现有能力：

- `list_ozon_products()`：全店商品列表。
- `get_ozon_info()`：批量详情。
- `get_ozon_attributes()`：完整属性。
- `get_ozon_descriptions()`：完整描述。
- `ozon_to_draft()`：Ozon 商品到本地草稿的字段转换。
- 现有发布链路：预检、媒体处理、提交、轮询和最终商品反查。

服务层提供两个入口：

- `import_ozon_product_by_sku(sku, store_client_id, selected_fields=None)`
- `sync_ozon_products(store_client_id, visibility="ALL")`

### HTTP API

- `POST /api/ozon-products/import-by-sku`
  - 请求：`sku`、`store_client_id`，可选 `selected_fields`。
  - 首次调用未传 `selected_fields` 时执行查询和差异预览；新商品可直接创建。
  - 已存在且有内容差异时返回差异，不覆盖本地可编辑字段。
  - 用户确认后携带 `selected_fields`，只应用选中的远端字段。
- `POST /api/ozon-products/sync`
  - 请求：`store_client_id`、`visibility`。
  - 返回新增、更新、保留、失败数量及逐商品错误。

现有 `/api/ozon/pull` 保留兼容，可委托新的同步服务实现。

### 数据持久化

第一版复用 `drafts` 表，不新增数据库迁移。

- `source_platform` / `source`：`ozon`。
- `source_offer_id`：保存数字 SKU 的字符串形式。
- `source_url`：使用稳定合成键 `ozon://product/<sku>`；数据库现有唯一索引已包含用户和店铺。
- `ozon_product_id`：保存 Ozon 商品 ID。
- `offer_id`：保存卖家货号，发布时保持不变。
- `source_raw.ozon_sync`：保存 SKU、最近同步时间、远端原始快照、远端字段摘要和变体提示。

查重必须包含当前用户和 `store_client_id`。查找优先级为 SKU 合成键，其次是同店铺 `product_id`，最后是同店铺 `offer_id`。不得使用当前无店铺作用域的全局 `find_by_offer_id()` 作为同步查重依据。

## 单品导入数据流

1. 前端读取当前店铺并提交数字 SKU。
2. 后端校验 SKU 为正整数，并解析当前用户在该店铺的 Seller API 凭证。
3. 调用 `/v3/product/info/list`，请求体使用 `sku` 数组。
4. 若没有返回商品，返回“SKU 不属于当前店铺或不存在”，不写数据库。
5. 从详情取得 `offer_id` 和 `product_id`。
6. 按 `offer_id` 拉取完整属性和描述。
7. 使用 `ozon_to_draft()` 转换字段，并补入 SKU、店铺和同步快照。
8. 在当前用户和店铺作用域内查找已有草稿。
9. 新商品直接插入；已有商品计算本地值与远端值的差异。
10. 无冲突的 Ozon 身份字段自动刷新；可编辑字段默认保留本地值。
11. 前端新商品直接打开草稿；已有商品展示差异供用户勾选应用。

## 字段映射与合并

### 自动刷新字段

以下字段属于 Ozon 身份或同步元数据，可在每次同步时自动刷新：

- `ozon_product_id`
- `source`、`source_platform`、`source_offer_id`
- `source_raw.ozon_sync` 中的远端快照和同步时间
- 远端商品可见性、归档状态等仅展示元数据

### 受保护的本地可编辑字段

以下字段存在本地非空值时不自动覆盖：

- `ozon_title`
- `description`
- `category_id`、`type_id`
- `attributes`
- `price`、`old_price`、`stock`
- `images`、`video_url`
- `weight_g`、`length_mm`、`width_mm`、`height_mm`
- `supplier`、`purchase_url`、`purchase_note`、`cost_cny`

若本地字段为空，可由同步结果补齐。若本地和远端均非空且不同，返回差异；只有用户明确选中的字段才采用远端值。

### 发布身份

导入草稿必须保留原 `offer_id`。编辑后发布继续使用 `/v3/product/import` 的更新语义和现有发布轮询，不重新生成货号。发布完成后继续按 `offer_id` 反查 Ozon 最终状态，避免把 `skipped + product_id=0` 误判为最终失败。

## 变体处理

单品导入只创建指定 SKU 对应的草稿。若 Ozon 返回的属性或元数据表明商品属于变体组，则把变体提示写入同步快照并显示在编辑页。

发布前执行以下判断：

- 普通商品：允许单品发布。
- 变体商品且现有发布链路允许单品更新：继续单品发布。
- 需要整组提交：停止单品发布并提示用户补拉同组 SKU 后使用整组发布。

不得静默导入或发布用户未选择的兄弟变体。

## 前端交互

商品草稿页顶部增加“从 Ozon 导入”按钮。

弹窗内容：

- 当前店铺，只读展示或允许从用户已有店铺中选择。
- 数字 SKU 输入框。
- 导入按钮和分阶段加载状态：查询商品、拉取属性、拉取描述、保存草稿。
- 部分成功警告。
- 已存在草稿时的字段差异列表，每项显示本地值和 Ozon 值，默认选择“保留本地”。

新建成功或确认合并成功后，关闭弹窗并在 Workbench 中打开对应草稿。

全店同步按钮可放在同一入口中作为次级操作。同步结果展示新增、更新、保留和失败数量，不因单个商品失败而停止整个批次。

## 错误处理与幂等

- SKU 为空、非数字或非正整数：返回 422，不调用 Ozon。
- 店铺不存在、无权限或未配置凭证：返回明确的 400/403 错误。
- SKU 不存在或不属于当前店铺：返回 404，不创建空草稿。
- 基础详情失败：整体失败，不写数据库。
- 属性或描述拉取失败：允许保存基础草稿，并返回 `warnings` 和缺失项。
- 同一 SKU 重复导入：返回同一草稿 ID。
- 并发导入同一 SKU：依靠现有 `(user_id, store_client_id, source_url)` 唯一索引兜底；捕获唯一冲突后重新读取并返回已有草稿。
- 批量同步单品失败：记录失败列表并继续后续商品。
- 所有异常消息不得包含 API Key 或完整凭证。

## 测试策略

### API 客户端

- 按 SKU 查询生成正确的 `{"sku": [...]}` 请求体。
- `offer_id`、`product_id` 和 `sku` 参数选择规则明确。

### 服务与数据层

- 新 SKU 完整创建草稿。
- 重复导入返回同一草稿。
- 相同 SKU 或 `offer_id` 在不同店铺严格隔离。
- 远端身份字段刷新，本地编辑字段不被静默覆盖。
- 只应用用户选择的远端字段。
- SKU 不存在时不写库。
- 属性、描述部分失败时保存基础草稿并返回警告。
- 变体提示写入并影响发布前检查。
- 现有全店拉取测试和发布测试保持通过。

### 路由

- 请求校验、店铺传递、404 和部分成功响应结构。
- 兼容旧 `/api/ozon/pull`。

### 前端

- 按钮和弹窗展示。
- SKU 输入校验。
- 当前店铺 ID 随请求发送。
- 分阶段加载状态和错误提示。
- 导入成功后打开目标草稿。
- 差异列表默认保留本地，并只提交勾选字段。

## 验收标准

1. 在已配置 Seller API 凭证的店铺中输入一个真实数字 SKU。
2. 系统创建或定位唯一的本地草稿，完整显示可获取的 Ozon 商品字段。
3. 修改俄语标题或描述后发布。
4. Ozon 上原 `offer_id` 商品被更新，没有创建重复商品。
5. 再次导入同一 SKU 不新增草稿，也不会覆盖未确认的本地修改。
6. 切换到另一店铺后，相同货号不会命中上一店铺的草稿。
