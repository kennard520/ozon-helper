# 阶段1：图片一对多表（draft_images）— 设计

日期：2026-06-26
状态：待用户评审
所属大改造：AI出图 worker 化（阶段1=图片表 / 阶段2=队列+worker / 阶段3=前端）。本 spec 只覆盖**阶段1**。

## 目标

把图片从「草稿行里的 `images_json` 数组」改成**一对多表** `draft_images`（一个变体→多张图，每张一行），
为后续 worker 逐图独立落库（阶段2）打基础，并让图片增删改查走表、无整数组读改写竞争。

**核心原则：存储层换，调用层透明。** 全 app 现有读 `draft["images"]`（list）和
`draft["source_raw"]["image_types"]`（{url:type}）的地方**不改**——`_row_to_draft` 读草稿时从表
拼出这两样，发布/展示/下载/变体/OSS 等照旧。风险集中在 store 存储层一处，好测好回滚。

非目标（不在阶段1做）：队列、worker、前端、逐图进度、任务状态。`draft.images` 写入方式不变（仍走
`update_draft({"images":[...]})`），只是底层落到表。

## 表结构

`draft_images`：
- `id` 自增主键
- `draft_id` 外键（drafts.id），建索引 `idx_dimg_draft(draft_id, position)`
- `position` int，定序（0,1,2,…）
- `url` text，图片 URL（/media 本地 或 OSS 公网）
- `type` varchar，图集类型（白底/细节/场景/尺寸/卖点/包装/其他；来自 `_img_type_from_label`）
- `source` varchar，来源（collected/generated/whitened/… 供阶段2 worker 区分，阶段1 先填 collected/generated）
- `created_at` text

SQLite：`Store.init()` 的 SQLite 块 `CREATE TABLE IF NOT EXISTS` + 索引。
MySQL：`db.MYSQL_DDL` 加建表 + `db.init_mysql` 里 `_ensure_mysql_index`（与 variant_group 同款）。

## 读路径（`_row_to_draft`）

读草稿时一次性查该 draft 的所有 `draft_images`（按 position），拼出：
- `draft["images"]` = `[row.url for row in rows]`
- `draft["source_raw"]["image_types"]` = `{row.url: row.type for row in rows if row.type}`

**性能**：列表/分组分页里 `_row_to_draft` 只对当页 ~20 个代表调用（阶段已优化），每个多一次
`SELECT url,type FROM draft_images WHERE draft_id=? ORDER BY position`（走索引，快）。可接受。
（若实测慢，再批量 IN 查询一次取全部、Python 分组——留作优化点，不在阶段1强求。）

## 写路径（store 层同步表）

`insert_draft` / `update_draft` 收到含 `images` 的 payload 时，把数组**同步成表的行**（在同一事务/锁内）：
- 取旧行的 `{url: (type, source)}` 映射（保留已有类型/来源）；
- 按新 `images` 顺序：DELETE 该 draft 旧行 → 按序 INSERT 新行，`position=i`，
  `type` = payload 的 image_types[url]（若 update 带）或旧行 type（按 url 匹配）或 `_img_type_from_label` 兜底，
  `source` = 旧行 source 或默认 collected。
- `images_json` 列：**回填后不再写**（保留列、值停更，做兜底/回滚）。
- `image_types`：不再单独存 `source_raw.image_types`（写入时如带，转成行的 type 列）。

`_add_candidate`（阶段1已是「直接进 images」）：改成直接 INSERT 一行 `draft_images`
（url + type=_img_type_from_label(label) + source=generated + position=末尾），不再读改写整数组。

其它写图路径需逐个适配（都经 update_draft 即自动同步；直接改 images_json 的要改走 update_draft）：
- `ext_collect_parsed`（采集建草稿，走 insert_draft）✓
- OSS 媒体回调 `update_draft_media`（把命中原 URL 换成 OSS URL）→ 确认它经 update_draft；若直接改 images_json 需改为按 url 更新对应行
- `copy_draft_to_store`（克隆草稿的图）→ 经 insert_draft 同步
- `apply_candidates`/`discard_candidates`（阶段1已基本弃用）→ 同步或留空

## 迁移 / 回填

`Store.init()` 一次性回填（SQLite+MySQL 两路径都跑，自限）：
- 找 `draft_images` 里没有该 draft 任何行、但 `images_json` 非空的草稿 → 解析 `images_json` +
  `source_raw.image_types`，按序 INSERT 行。
- 自限：回填后该 draft 有行了，下次不再命中（`WHERE NOT EXISTS (SELECT 1 FROM draft_images WHERE draft_id=drafts.id) AND images_json<>'[]'`）。
- 失败不阻断启动（try/except + print），回退仍可用 images_json（读路径兜底：表为空时用 images_json）。

读路径兜底：某 draft 表里没有行（回填失败/新边界）→ `_row_to_draft` 回退用旧 `images_json`，保证不丢图。

## 测试

- 单测 `test_draft_images`：
  - insert_draft 带 images → 表里有对应行、position 正确、`get_draft()["images"]` 还原一致；
  - update_draft 改 images（增/删/换序）→ 表行同步、类型按 url 保留；
  - image_types 还原到 source_raw.image_types；
  - 回填：手动塞 images_json 无表行 → 重开 Store → 表被回填、images 一致；
  - 表为空+有 images_json → 读路径兜底返回 images。
- 回归：跑 test_drafts / test_pagination / test_publish_group / test_variant_publish / test_store / test_image_*，确认 `draft.images` 行为不变。
- 部署后线上核验：随机几条草稿 `get_draft().images` 与回填前一致；发布预览图片数不变。

## 风险 & 回滚

- 风险点全在 store 读写两处 + 回填。`images_json` 列保留不删 → 真出问题可改读路径回退用 images_json，或回滚镜像（`ozon-webui:rollback`）。
- MySQL 与 SQLite 双实现（adapter 翻译 `?`→`%s`），按既有 variant_group/offer_id 迁移同套路。

## 交付

阶段1 上线后：图片落表、对上层透明、行为不变。**阶段2（队列+worker）** 再单独 spec，那时 worker 逐图
INSERT `draft_images`（source=generated）+ 写 `gen_jobs` 状态。
