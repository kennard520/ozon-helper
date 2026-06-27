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

## 4. 前端图片 tab（ImagesTab，F1d-3 — 待建）
规划：图集区（Ozon 类型槽位）+ 素材库区（「来自变体」下拉 = 跨变体借图）+ 应用到图集 + AI 出图。详细交互在 F1d-3 落地时补。

## 5. 遗留 Minor（可跟进，非阻塞）
- `list_pending_media_drafts` 返回字段名 `images` 实含全部图（语义模糊，插件用）。
- `_sync(gallery=False)` 跳过已存在 url 时 position 有 gap（reorder 会重置，无害）。
- **MySQL 全新部署**：`create_all` 已含 `in_gallery`（SQLite 已验，0006 迁移含 MySQL 分支加列；真 MySQL 全新验证待跑）。

## 变更历史
- 2026-06-27 后端两池模型完成（提交链 `3a854d2`→`e016e8c`+`6001b5c`，673 passed）。建文档基线。
