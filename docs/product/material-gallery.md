# 素材库 / 图集（两池图片模型）

> 一张商品有两类图片：**素材库**（1688 采集的全部原图，混在一起）和**图集**（精选进 Ozon 类型槽位、用于发布的图）。
> 后端已完成；前端图片 tab（ImagesTab）F1d-3 对接。前端工作台总览见 [workbench.md](workbench.md)。

## 1. 模型（数据）

一张表 `draft_images` + `in_gallery` 标记位（**不加 variant_group 列、不改 FK**）：
- **素材 materials** = 该 draft 的全部图（`draft_images` 所有行）。
- **图集 gallery** = `in_gallery=1` 的子集，按 `position` 排序对应 Ozon 类型槽位。
- 单行字段：`{id, url, type(image_types 槽位), source, in_gallery(0/1), position}`。

写入落池规则：
- 采集图 → `in_gallery=0`（进素材库）。
- AI 出图 → `in_gallery=1`（直接进图集）。

`get_draft` 返回：
- `images` = **图集**（发布用，`in_gallery=1`）。
- `materials` = **全部图** `[{id,url,type,source,in_gallery,position}]`。

## 2. 规则（写入保护）

- `_sync_draft_images` 改成**图集感知**：UPDATE 标记/position + 只 INSERT 真新图，**绝不删全表**（保护素材库）。`gallery=False` 仅用于采集初次插入（落素材）。
- **坑（已修）**：`apply_media_oss`（OSS rehost）原走 `_sync(gallery=True)` 会把采集素材全升进图集 → 改成按行 UPDATE url 保 `in_gallery`。曾被 3 处 media 测试断言成「正确」掩盖。
- 跨变体复制（`copy-images-to`）：**只复制确属源草稿的 url**（防注入）、按 url 去重、同变体组校验、落目标图集。

## 3. 接口（细粒度操作，`DraftImageRepo`）

| 操作 | HTTP |
|---|---|
| 加入图集 | `POST /api/drafts/{id}/gallery/add` |
| 移出图集 | `POST /api/drafts/{id}/gallery/remove` |
| 重排图集 | `POST /api/drafts/{id}/gallery/reorder` |
| 删除图片（素材+图集都删） | `DELETE /api/drafts/{id}/images/{image_id}` |
| 跨变体复制 | `copy-images-to`（多目标 `target_draft_ids`，兼容旧 `target_draft_id`） |

repo 方法均按 `image_id`，用 `draft_id + id` 双条件防越权。

### 删除语义（已定）
图片同时在素材与图集时，用户在素材库删除 → 整行删（图集里也消失）。「移出图集」只清 `in_gallery=0`，图仍留素材库。

## 4. 前端图片 tab（ImagesTab）

### F1d-3a 两池管理 —— ✅ 已完成（2026-06-27）
工作台 DetailTabs「图片」tab，三段（`components/workbench/tabs/ImagesTab.vue`）：
- **图集（发布顺序）**：有序 ImageCard，每张 ↑↓ 调序(galleryReorder)、移出图集(galleryRemove)、删除(deleteImage 二次确认)；顶部「上传图片」(uploadMedia→patchDraft images 进图集)。
- **素材库**：in_gallery=0 的图，每张「加入图集」(galleryAdd)、删除；多选 +「批量加入图集」。
- **来自变体（借图）**：同组兄弟下拉(`wb.variants` 去当前，spec 标签)→ 拉该兄弟 materials → 选图「借到图集」(copyImagesTo 源=兄弟/目标=[当前])。

**架构**：`composables/useGallery.js`（单一真相=后端 draft；派生 `galleryItems`(in_gallery 真按 position)/`materialItems`(假)；mutation 调 api 成功后 `onChange()`→DetailTabs `fm.load` 重拉）+ `components/workbench/ImageCard.vue`（纯展示:localUrl 优先/类型来源徽章/选中/actions 插槽）。`localUrl` 走 `draft.images`↔`draft.local_images` zip（图集本地代理防 1688 防盗链），素材回退原 url。
**api.js 新增**：`galleryAdd/galleryRemove/galleryReorder(id,image_ids)` + `deleteImage(id,image_id)` + `copyImagesTo(id,image_urls,target_draft_ids)`。

### F1d-3b AI 出图 —— 📋 待建
design-image-plan（AI 设计图集槽位）→ image-plan（拉计划+槽状态）→ generate-plan-slot（按槽生成进候选区）→ apply-candidates/discard-candidates（应用/丢弃候选）。候选区 + 槽位 UI 待建。

### ✅ 已修复（2026-06-27）
素材（in_gallery=0 采集图）防盗链显示问题已彻底修复：
- **后端**：`draft_images` 加 `local_url` 列（String(1024), nullable=False, server_default=""）；迁移 0007（MySQL 存量库加列）；采集落库 `_sync_draft_images(gallery=False)` 时按 `images[i] ↔ local_images[i]` 平行取值随行存；`getDraft` 的 `materials` 每项返回 `local_url`。
- **前端**：`useGallery.js` 新增并导出 `localUrlOf(item)` = `(item.local_url) || localUrl(item.url)`；`ImagesTab.vue` 三段 ImageCard（图集、素材库、借图）的 `:local-url` 均改用 `g.localUrlOf(it/m)`，优先 `local_url`，无则回退图集 zip 代理。

## 5. 遗留 Minor（可跟进，非阻塞）
- `list_pending_media_drafts` 返回字段名 `images` 实含全部图（语义模糊，插件用）。
- `_sync(gallery=False)` 跳过已存在 url 时 position 有 gap（reorder 会重置，无害）。
- **MySQL 全新部署**：`create_all` 已含 `in_gallery`（SQLite 已验，0006 迁移含 MySQL 分支加列；真 MySQL 全新验证待跑）。

## 变更历史
- 2026-06-27 后端两池模型完成（提交链 `3a854d2`→`e016e8c`+`6001b5c`，673 passed）。建文档基线。
- 2026-06-27 draft_images 加 local_url 列（迁移 0007）+ 前端 localUrlOf 优先用，素材防盗链显示已修复。
