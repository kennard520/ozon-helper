# 素材库 / 图集(两池图片模型)— 设计

- 日期:2026-06-27
- 范围:**仅后端**(数据模型 + 仓储 + 语义 + API)。前端 UI 是独立子项目(F1 变体工作台的"图片"tab),本 spec 不含前端。
- 依赖关系:这是前端重建 F1 的"图片/图集"面板的后端依赖,先落。

## 背景与问题
当前 `draft_images` 把一个草稿的所有图(采集图 source='collected' + AI 出图 source='generated')放在同一张表,**发布时全部使用**(`draft["images"]` = 全部行,`listing_build.py:103` 直接用)。没有"备选素材"与"真正发布的图"之分。

业务需要两池:
- **素材库(materials)**:一个变体的**全部图**(原图采集 + AI 生成),作为备选池。
- **图集(gallery)**:**真正发布**的那套图(AI 出图自动进 + 用户从素材选入),按 Ozon 类型槽位组织(白底主图/整体展示/细节图/细节图2/场景图/尺寸图/卖点图/包装图)。

原型(`变体工作台.dc.html` 的"图片"tab)已完整画出:上方"图集(最终图)"按类型槽位排 + Ozon 合规校验条;下方"素材"区有"来自变体 [雾灰·600ml ▾]"下拉 + 缩略图 + "应用到图集"按钮 + "✨ AI 生成图片"。本设计与原型严丝合缝。

## 模型决策(已与用户确认)
**每变体各自一套素材+图集;跨变体"共享"用复制实现(不做组级归属)。**

- 图片仍按变体归属:`draft_images.draft_id`(FK→drafts CASCADE)**不变**。删一个变体只删它自己那份图(语义正确)。
- **不**加 `variant_group` 列、**不**改 FK。规避了"共享图被某变体删除级联误删"的孤儿问题。
- "跨变体复制图片"(原型的"来自变体"下拉 + 应用到图集)= 把源变体的图**复制**到目标变体(行复制,去重),不是真共享。代价:复制是快照非活链接(源改了要再复制),业务可接受。

> 备选 B(图片按 variant_group 组级归属 + 改 FK 级联)被否决:复杂度高、撞已验证的 M4d 外键、迁移重。一张表 + 复制更干净。

## 数据模型变更

### schema:`draft_images` 加一列
现有列:`id, draft_id(FK CASCADE), position(default 0), url, type(String32 default ""), source(String32 default "collected"), created_at`,索引 `idx_dimg_draft(draft_id, position)`。

新增:
```python
Column("in_gallery", Integer, nullable=False, server_default="1"),
```
- 含义:1=该图在图集(会发布);0=只在素材库(备选)。
- 默认 1 → **现有所有行迁移后自动进图集**,老草稿发布行为完全不变。
- SQLite 用 Integer(0/1);MySQL 同(prod 用 TINYINT/INT 皆可,Integer 映射兼容)。

### 池语义(每变体)
- **素材库 materials** = 该 draft 的**全部** `draft_images` 行。
- **图集 gallery** = 该 draft `in_gallery=1` 的子集,按 `position` 排。
- AI 出图 `in_gallery=1`(进图集);采集图 `in_gallery=0`(只进素材)。
- 图集成员的 `type` = Ozon 槽位类型(已有 `type` 列承载);`position` = 槽位/发布顺序。

## Alembic 迁移 `0006_in_gallery`
- `upgrade`:
  - `op.add_column("draft_images", sa.Column("in_gallery", sa.Integer(), nullable=False, server_default="1"))`。
  - 现有行因 server_default=1 自动回填为 1(全进图集,行为不变),无需数据转换。
  - (可选)MySQL 上保留 server_default 或 `alter` 去掉皆可;与现有迁移风格一致,dialect 无需分支(纯加列)。
- `downgrade`:`op.drop_column("draft_images", "in_gallery")`。
- 不需要数据迁移脚本(默认值即正确迁移)。

## 写入路径(新图按 A1 语义)
1. **采集建草稿**(`DraftRepo.insert_draft` → 现有 `_sync_draft_images` 批量插入采集图):新插入的采集图 `in_gallery=0`(只进素材)。这是一次性批量 INSERT,非反复 churn,保留。
2. **AI 出图**(`DraftImageRepo.add_draft_image(..., source="generated")`,调用方:`worker.py:255`、`app_service.py:2409`):`in_gallery=1`,`position` 接当前图集末尾。

## 细粒度操作(干掉"删全部+重插")
**核心改造**:现 `_sync_draft_images` 的"DELETE 全表行 → 按 images 数组重插"模式被废弃(它会 churn 表、自增 id 无限涨、且两池下会误删素材)。改成针对单行的细粒度操作:

| 操作 | DB 动作 | 仓储方法(新增/改) |
|---|---|---|
| 素材加入图集 | UPDATE `in_gallery=1`, `position`=图集末尾 | `DraftImageRepo.add_to_gallery(draft_id, image_ids)` |
| 移出图集(留素材) | UPDATE `in_gallery=0` | `DraftImageRepo.remove_from_gallery(draft_id, image_ids)` |
| 彻底删一张图 | DELETE 单行(按 id) | `DraftImageRepo.delete_image(draft_id, image_id)` |
| 图集排序 | UPDATE 仅图集行的 `position` | `DraftImageRepo.reorder_gallery(draft_id, ordered_image_ids)` |

- 所有操作按 `image_id`(稳定),id 不再 churn。
- `reorder_gallery` 只更新 `in_gallery=1` 的少数行(图集 ~10 张),非删重插。
- `_sync_draft_images` 的"全删重插":采集批量插入仍可用其插入逻辑;但"编辑已有图集 = 发整个 images 数组重建"的旧路径**退役**,改走上面的细粒度方法。需盘清调用方(见"迁移与兼容")。

## `get_draft` 返回 dict 形状
- `draft["images"]` = **图集**(`in_gallery=1`,按 position)——发布/展示/现有消费方继续用,语义随 dict 改为"只发图集"。老草稿(全部 in_gallery=1)= 全部,不变。
- 新增 `draft["materials"]` = **全部图**,每条:`{"id", "url", "type", "source", "in_gallery", "position"}`。给素材库视图用。
- `image_types`(现有按 url→type 映射)继续从图集集合产出,保持兼容。

> 影响:`_row_to_draft` 与 `_load_draft_images_batch`(M5 批量化)需:① 读取时带 `in_gallery`、`id`;② `images` 只取 `in_gallery=1`;③ 额外产出 `materials`(全部)。批量路径(列表页)同样只需 materials/gallery 的一次批量查(N+1 不回退)。

## 发布语义
- `listing_build.py` 等走 `draft["images"]`(现已=图集),**自动变成"只发图集"**,无需改 publish 代码。
- 校验:现有发布前置校验(图片数量等)基于 `images`,自动对图集生效。

## 跨变体复制(改造 `copy-images-to`)
现状 `app_service.py:copy_images_to_draft`(`main.py:898` 端点):把源草稿选中的 url 合并去重后,**用 `update_draft({"images": existing})` 触发 `_sync` 全删重插**写入目标——既是删重插坏模式,又只支持单目标。

改造:
- 走**细粒度 INSERT**:对每个要复制的源图,在目标变体 INSERT 一行(`url/type/source` 复制;**`in_gallery=1`** 落入目标图集——对应原型"应用到图集"),按 url 去重(目标已有同 url 跳过)。
- 支持**多目标 / 组内全部变体**:body 接 `target_draft_ids: list[int]`(兼容旧 `target_draft_id` 单值)。
- 同组校验保留(variant_group 一致)。
- 返回每个目标新增数量。

## 仓储方法清单(`DraftImageRepo` / `DraftRepo`)
- `add_to_gallery(draft_id, image_ids)` / `remove_from_gallery(draft_id, image_ids)` / `delete_image(draft_id, image_id)` / `reorder_gallery(draft_id, ordered_image_ids)`。
- `add_draft_image(...)` 增 `in_gallery`(默认按 source:generated=1,其它=0,或显式入参)。
- `copy_images(src_draft_id, image_ids, target_draft_ids)`(供 app_service 调)。
- `_load_draft_images_batch` / `_row_to_draft`:带 `id`/`in_gallery`,产出 gallery + materials。
- 采集插入路径:采集图 `in_gallery=0`。

## HTTP API(端点形状,前端原型来后可微调)
- `POST /api/drafts/{id}/gallery/add` `{image_ids:[...]}` → add_to_gallery。
- `POST /api/drafts/{id}/gallery/remove` `{image_ids:[...]}` → remove_from_gallery。
- `POST /api/drafts/{id}/gallery/reorder` `{image_ids:[...]}` → reorder_gallery(按数组设 position)。
- `DELETE /api/drafts/{id}/images/{image_id}` → delete_image。
- 改造 `POST /api/drafts/{id}/copy-images-to`:body 支持 `target_draft_ids`(数组)+ 兼容 `target_draft_id`;复制落目标图集。
- `GET /api/drafts/{id}` 已带 `images`(图集)+ `materials`(全部),素材库无需新端点。

## 迁移与兼容(必须盘清)
- 盘清现有往 `update_draft({"images": ...})` 写图 / 触发 `_sync_draft_images` 的调用方(前端发整 images 数组、copy、OSS rehost `update_draft_media` 等),逐一迁到细粒度方法或确认其语义(rehost 改 url 不应动 in_gallery/position)。
- 现有 35x 测试里凡造 draft_images / 断言 images 全集的,需按"images=图集"新语义核对。

## 测试
- 迁移:全新 SQLite/MySQL `create_all` + `0006` 加列;现有行 `in_gallery=1`。
- 语义:采集→materials 全含、gallery 空(in_gallery=0);AI 出图→进 gallery;`images`=gallery、`materials`=全部。
- 细粒度:add/remove/delete/reorder 各自只动应动的行,id 稳定(无删重插),素材不被图集编辑误删。
- 复制:copy 到多目标,目标图集新增、去重、同组校验;源不变。
- 发布:只发 `in_gallery=1`。
- N+1 不回退(列表页 materials/gallery 仍批量一次查)。
- 全量回归 ≥ 660 不下降。

## 非目标
- 不做前端 UI(F1 子项目)。
- 不做图片按 variant_group 组级归属 / FK 重构。
- 不做素材的软删除 / 版本历史(YAGNI)。
- 不改 OSS/出图本身逻辑,只接其 `in_gallery` 落点。
