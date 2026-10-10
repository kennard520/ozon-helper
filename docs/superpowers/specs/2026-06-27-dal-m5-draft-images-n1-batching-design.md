# 数据访问层 M5：草稿列表 N+1 批量化 — 设计

- 日期：2026-06-27
- 所属:数据访问层重构 · 子项目1 的最后一个里程碑。M1-M4 ✓。
- 范围:**只做 N+1 批量化,不做 keyset 分页**(此规模 OFFSET 够用;keyset 改契约+前端,YAGNI)。纯 `DraftRepo` 内部优化,无 schema/契约变更。

## 问题
`DraftRepo._row_to_draft(row)` 每行单独查一次 `draft_images`(`SELECT ... WHERE draft_id=?`)。`list_drafts` / `list_drafts_page`(两分支,一页最多 200 行)/ `list_drafts_by_variant_group` 逐行调它 → 列表 = **1 + N 次查询**(最多 201)。这是原 DB 体检的列表 N+1。

## 方案
1. **批量取图** `_load_draft_images_batch(draft_ids: list[int]) -> dict[int, list[dict]]`:一条
   `SELECT draft_id, url, type, source FROM draft_images WHERE draft_id IN (:ids) ORDER BY draft_id, position`,
   Python 按 draft_id 分组成 `{draft_id: [{url,type,source}, ...]}`。空 ids 直接返回 `{}`。
2. **`_row_to_draft(row, images)`**:签名改为接预加载的图列表(`images: list[dict]`),装配逻辑(images=[url…]、source_raw.image_types、各 JSON 列还原)**完全不变**。
3. **列表方法走批量**:`list_drafts` / `list_drafts_page`(普通分支 + group 分支的当页代表) / `list_drafts_by_variant_group`:取出当页 rows → 收集 `[r.id for r in rows]` → `_load_draft_images_batch(ids)` → `[_row_to_draft(r, by_id.get(r.id, [])) for r in rows]`。**一页降到 2 次查询**(1 drafts + 1 images)。
4. **单行路径**(`get_draft` / `find_by_source_url` / `find_by_offer_id`):每次 1 条图查询即可,改为 `_row_to_draft(row, self._load_draft_images(row.id))`(适配新签名)。`_load_draft_images(draft_id)`(单行)保留或基于 batch 实现皆可。
5. **draft_image_repo.py 的 worker `_row_to_draft`/`get_draft` 不动**(单行,无列表 N+1)。

## 行为与 parity
- 返回的 draft dict **逐字段不变**(只是图来自预加载而非逐行查),`list_drafts_page` 的分页/分组/排序口径不变。
- 659 全量回归兜底 parity。
- 新增 1 个测试:`list_drafts_page` 返回 N 个草稿(各带图)时,**draft_images 查询只发 1 次**(用 SQLAlchemy event 计 `draft_images` 的 SELECT 次数,或 mock/计数器),断言批量生效(N+1 消除)。

## 非目标
- 不做 keyset/cursor 分页(契约变更,YAGNI)。
- 不改 schema、不改 HTTP 契约、不动其它仓储。
- 不做"素材库/图集分两池"功能(那是后续独立 feature,见 [[dal-refactor-progress]] 备注)。
