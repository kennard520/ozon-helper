# 后端 app_service/main 绞杀拆分设计（god-class 解构）

**日期**：2026-06-27　**分支**：feat/auto-listing-ai-pipeline

## 问题
`apps/webui/src/webui/app_service.py` = 3875 行、`class App` 152 个方法的 god-class（后端版 DraftDetail）；`main.py` = 980 行、所有 FastAPI 路由挤一个文件。改一处要翻 3875 行、领域耦合不可见、并发改冲突大、测试只能整类 mock。数据层（`packages/ozon_common` DAL）已规范，问题只在 webui 应用层。

## 目标
绞杀者模式（同前端删 god-component 的打法）：按领域把 `App` 拆成 **mixin**、把 `main.py` 拆成 **routers/**，**行为零变化、调用点零改、全程绿（714 passed 基线）**。一次一个领域、每搬一个跑全量回归。

## 关键架构决策

### 1. app_service：领域 mixin（不是 service 对象）
- `App` 现状：仅共享 `self.store`(Store)、`self.catalog`/`self.catalog_ru`(Catalog)、`self._cand_lock`(Lock)；152 方法间大量 `self.xxx()` 横调。
- **决策：拆成领域 mixin**，`App` 多继承组合：`class App(AuthMixin, CategoryMixin, DraftMixin, PublishMixin, AiCardMixin, AiImageMixin, AiVideoMixin, GalleryMixin, ExtMixin, GenJobMixin, PricingMixin, WarehouseMixin, SettingsMixin)`。
  - 同一实例，`self.` 横调与共享状态**全部照常工作** → 行为字节级不变、零调用点改动、现有测试不改即过。
  - 文件从 1×3875 → ~13×(150~500) 行，按领域可读、可独立持有上下文。
- **为何不用 service 对象**：App 横调密集（如 `ai_generate`→`understand_draft`/`_category_attrs`/`_autofill_from_understanding`），service 化要把所有跨域 `self.x` 改成 `self._app.svc.x` 或注入 context = 高风险大改、零行为收益。mixin 先解决可读性；**日后某领域（如 AiImage）确需真隔离，再单独演进成 service**（渐进，不是现在）。

### 2. 共享 helper 与状态
- 模块级纯函数（`_to_int/_parse_dims_mm/_parse_volume_ml/_parse_weight_g/_has_cjk/_attr_language/_models_url/_is_country_attr/_download_bytes/_img_type_from_label/_money_to_float` + `step_flags`）→ 移到 `webui/services/_helpers.py`，各 mixin `from webui.services._helpers import ...`。`step_flags` 是模块级公开函数（main/其它 import），保持可从原路径或新路径导入（在 `app_service.py` re-export 兼容）。
- 共享状态 `store/catalog/catalog_ru/_cand_lock` 留 `App.__init__`；mixin 经 `self.` 用（mixin 不写 `__init__`）。
- 常量（`NO_BRAND`/`BRAND_ATTR_ID`/`_ATTR_EXCL` 等）放 `_helpers.py` 或保留 app_service 顶部并被 mixin import。

### 3. main.py：routers/ 按领域
- `APP = App()` 单例抽到 `webui/app_instance.py`（避免 router↔main 循环 import）；`main.py` 与各 router 都 `from webui.app_instance import APP`。
- `webui/routers/{auth,settings,category,drafts,ai_text,ai_image,ai_video,publish,gallery,ext,pricing,warehouse}.py`，各建 `router = APIRouter()`、端点原样搬。
- `main.py` 退化为：建 FastAPI app + 中间件/异常处理 + `app.include_router(...)` 全装回 + 静态/SPA 挂载。路径与行为不变。
- Pydantic 模型（`models.py`）保持；router 各 import 所需模型。

## 领域边界（mixin 与 router 对应）
| 领域 | mixin | 代表方法/端点 |
|---|---|---|
| 鉴权/用户/钱包 | AuthMixin | login, user_from_token, admin_*, wallet_*, presign_media, publish_fee |
| 设置/状态 | SettingsMixin | state, save_settings, _migrate_ai_platforms, _settings_for_store, list_ai_models |
| 类目/属性 | CategoryMixin | search_category, category_tree, category_attributes, required_check, attribute_value_options, brand_search, recognize_category |
| 草稿 CRUD | DraftMixin | list_drafts, get_draft, update_draft, copy_draft_to_store, batch_update_drafts, delete, variant_group_siblings, regenerate_offer_id |
| 发布 | PublishMixin | publish, publish_preview/preflight, batch_publish, pull_ozon_products, publish_variant_group, _validate_and_build_item, fbs_label, _maybe_auto_publish |
| AI 文案 | AiCardMixin | ai_generate, ai_copy, ai_fill_attributes, auto_map_attributes, understand_draft, recommend, apply_ai_proposal, patch_ai_proposal, _card_chat, 物理量/固定属性 helper |
| AI 出图 | AiImageMixin | ai_generate_image, localize/regen/whiten/scene_image, make_infographic, make_rich_content, image_plan, design_image_plan, generate_plan_slot, _add_candidate, _edit_source_image, apply/discard_image_candidates, start_image_batch |
| AI 视频 | AiVideoMixin | start_ai_video, ai_video_status, stop_ai_video, _on_ai_video_done |
| 图集 | GalleryMixin | gallery_add/remove/reorder/delete, copy_images_to_draft |
| 插件/采集 | ExtMixin | ext_ping, ext_collect_parsed, ext_add_snapshot, update_draft_media, pending_media_drafts, _media_needs_upload |
| 生图任务(MQ) | GenJobMixin | submit_gen_job, submit_batch_gen_job, get_gen_job_status, batch_latest_gen_jobs |
| 定价/佣金/realFBS | PricingMixin | realfbs_routes, import/export, commission_*, get/save_commission_map |
| 仓库/履约 | WarehouseMixin | list_warehouses, sync_warehouses, pull_fbs, list_procurement, ship_posting, set_default_warehouse |

> 边界按"方法主要操作的实体/调用的下游"划；跨域私有 helper（如 `_resolve_values` 被 category+aicard 用）归其**主属领域**，他域经 `self.` 调（mixin 互通，无 import 问题）。落地时individual方法归属以"减少跨文件牵连"为准，可微调。

## 执行策略（绞杀者，always-green）
- **Phase A 先拆 main.py → routers/**（低风险：App 不动，router 只搬端点 + import APP）。每搬几个领域跑全量回归。
- **Phase B 再拆 app_service → mixins**（一次一个领域 mixin：建 `services/_<domain>.py`、剪切该域方法过去、App 加继承、跑全量 714 回归必须持平）。先抽 `_helpers.py`。
- 每个 Task = 一个领域，**TDD 不适用(纯搬迁)→ 用回归门**：`python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py'` 必须 ≥714 passed、0 新失败。`python -m uv` 不是 `uv`（PATH 没 uv）。
- 风险点：import 牵连（移方法漏带 import / 循环 import）→ 每 Task 后整跑 + `python -c "import webui.main"` 冒烟。

## 范围外
- 不动 `packages/ozon_common`（DAL 已规范）。
- 不重构方法内部逻辑、不改签名、不改 HTTP 路径/契约。
- service 对象化（mixin→真隔离 service）= 可选 Phase C，按领域按需，不在本次。
- `store.py`(574行 Store)收敛 = 另案（见 [[db-health-remediation]]）。

## 验证
- 每 Task：全量回归 ≥714 passed + `import webui.main` 冒烟 + `python -m uv run ozon-webui` 起得来。
- 全部后：起后端 curl 几个代表端点（drafts/category/gallery）确认契约不变；前端 `npm run build` 不受影响（仅后端内部重组）。
