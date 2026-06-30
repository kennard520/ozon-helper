# F1d-3a 图片 tab（两池图片管理）设计

**日期**：2026-06-27　**分支**：feat/auto-listing-ai-pipeline　**模块文档**：[material-gallery.md](../../product/material-gallery.md) + [workbench.md](../../product/workbench.md)

## 目标
工作台 DetailTabs 的「图片」tab 第一期：把已完成的**素材库/图集两池后端**接出 UI。让用户看清两池、把素材精选进图集、排序图集、删图、从同组其它变体借图。**AI 出图（design-plan/槽位/候选）拆到 F1d-3b**，本期不做。

## 现状（复用既有后端，零后端改动）
- `getDraft().draft` 带：`images`（图集 url，发布用）、`materials`（全部图 `[{id,url,type,source,in_gallery,position}]`）、`local_images`（图集本地代理，并行 images，防 1688 防盗链）。
- 后端端点（已完成）：
  - `POST /api/drafts/{id}/gallery/add` `{image_ids:[]}` → 返回更新后整个 draft
  - `POST /api/drafts/{id}/gallery/remove` `{image_ids:[]}`（移出图集，留素材）
  - `POST /api/drafts/{id}/gallery/reorder` `{image_ids:[]}`（按序重排 position）
  - `DELETE /api/drafts/{id}/images/{image_id}`（彻底删一行）
  - `POST /api/drafts/{id}/copy-images-to` `{image_urls:[], target_draft_ids:[]}`（跨变体复制到目标图集，只复制确属源草稿的 url）
  - `POST /api/drafts/{id}/media`（上传，返回 `{url}`，**不落 draft_images**）
- api.js **缺** gallery 系列 + copyImagesTo（本期补）；已有 uploadMedia。
- workbench store `variants`：`[{id, spec, price, status, image, steps, done}]` → 借图下拉的同组兄弟来源（`spec` 作标签）。

## 范围外（F1d-3b / 后续）
- AI 出图：`designImagePlan` / `imagePlan` / `generatePlanSlot` / `applyCandidates` / `discardCandidates` + 候选区/槽位 UI。
- 拖拽排序（本期用 ↑↓ 按钮，可靠且可测；拖拽留作后续打磨）。

## 架构（沿用 useDraftForm/useAttributes 的 composable + 纯展示组件模式）
单一真相 = 后端返回的 draft（每个 mutation 端点都返回整 draft）。组件不维护本地图片副本，mutation 后 `emit('saved')` → DetailTabs `fm.load()` 重拉，刷新两池。

1. **api.js 新增**：`galleryAdd(id, image_ids)` / `galleryRemove(id, image_ids)` / `galleryReorder(id, image_ids)` / `deleteImage(id, image_id)` / `copyImagesTo(id, image_urls, target_draft_ids)`。
2. **`composables/useGallery.js`** — `useGallery(draftRef, { onChange })` →
   - 派生：`galleryItems`（`materials` 里 `in_gallery` 真，按 position 排）、`materialItems`（`in_gallery` 假）。
   - `localUrl(url)`：图集 url → 本地代理（zip `draft.images`↔`draft.local_images`，同 legacy）；素材/未命中回退原 url。
   - mutations（调 api → 成功 onChange()）：`addToGallery(ids)`、`removeFromGallery(ids)`、`reorder(ids)`、`moveUp(id)`/`moveDown(id)`（据 galleryItems 算新序调 reorder）、`removeImage(id)`(delete)、`copyFrom(siblingId, urls)`、`upload(file)`（uploadMedia→拿 url→`patchDraft({images:[...galleryUrls,url]})`→onChange，上传图进图集）。
   - 借图：`siblings`（wb.variants 去掉当前）、`fetchSiblingMaterials(siblingId)`（`api.getDraft` → 该兄弟 materials）。
3. **`components/workbench/ImageCard.vue`** — 纯展示。props：`url`、`localUrl`、`type`、`source`、`selected`、`badge`。显示缩略图 + 类型徽章 + 来源徽章（采集/生成）+ 选中态；动作走具名插槽 `#actions`。
4. **`components/workbench/tabs/ImagesTab.vue`** — 三段：
   - **图集（发布顺序）**：有序 ImageCard，每张 ↑↓ 调序、移出图集、删除；顶部「上传图片」。空图集提示。
   - **素材库**：ImageCard（in_gallery=0），每张「加入图集」「删除」；多选 + 「批量加入图集」。
   - **来自变体（借图）**：兄弟下拉（spec 标签），选中 → 拉该兄弟 materials 显示为卡，每张「借到图集」(copyFrom)。无兄弟则不显示该段。
   - 接入 DetailTabs 替换 images 占位，`@saved="fm.load"`。

## 交互
- 选变体 → tab 渲两池：图集（有序）+ 素材库。
- 素材「加入图集」→ galleryAdd → 该图进图集尾、从素材区消失（变 in_gallery=1）。批量同理。
- 图集「移出」→ galleryRemove → 回素材区。「↑↓」→ galleryReorder。「删除」→ deleteImage（两池都删，二次确认）。
- 借图：选兄弟 → 看其素材 → 「借到图集」→ copyImagesTo(源=兄弟, 目标=[当前]) → 刷新当前图集。
- 上传：选文件 → uploadMedia → 进图集 → 刷新。

## 数据形状
| 名 | 形状 | 来源 |
|---|---|---|
| galleryItem | `{id,url,type,source,in_gallery:1,position}` | draft.materials 过滤 |
| materialItem | `{...,in_gallery:0}` | draft.materials 过滤 |
| 借图请求 | `copyImagesTo(siblingId, [url...], [currentId])` | 兄弟 materials 选中 url |
| add/remove/reorder | `{image_ids:[int]}` | 卡片 id |

## 已知风险（验收时实证）
- **素材（in_gallery=0）显示**：采集 1688 图可能是防盗链原链，而 `local_images` 只并行图集。若素材原 url 显示不出，需小后端补丁（getDraft 给每个 material 加 `local_url`）。本期验收用真种子确认；若需补丁，单独小任务处理。

## 测试（Vitest + @vue/test-utils）
- useGallery：从 draft.materials 拆两池（in_gallery 真/假）、按 position 排；addToGallery/removeFromGallery/reorder/deleteImage/copyFrom 调对应 api 且参数对、成功后调 onChange；moveUp/moveDown 算出正确 id 序；localUrl 命中图集代理/回退原 url。
- ImageCard：渲缩略图（用 localUrl 优先）、类型/来源徽章、选中态、actions 插槽。
- ImagesTab：渲图集段（N 张有序）+ 素材段 + 借图下拉（有兄弟时）；「加入图集」触发 galleryAdd；「批量加入」聚合 ids；借图触发 copyImagesTo。
- gating：前端失败数 ≤32 基线不新增；新增用例全过。
