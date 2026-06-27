# 后端 app_service/main 绞杀拆分 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。纯搬迁重构 → 不写新逻辑、**用回归门代替 TDD**：每 Task 后 `python -m uv run python -m pytest apps/webui/tests --ignore-glob='*_live.py'` 必须 **≥530 passed(apps/webui/tests)、0 新失败**，且 `python -c "import webui.main"` 冒烟过。`python -m uv`（PATH 无 uv）。

**Goal:** `app_service.App`(3875行) → 领域 mixin；`main.py`(980行) → routers/。行为零变化、调用点零改、全程绿。

**Architecture:** 见 spec `docs/superpowers/specs/2026-06-27-backend-app-service-decompose-design.md`。绞杀者、一次一个领域、每步全量回归。

**根目录基准**：`E:\personal\ozon-helper`，包 `apps/webui/src/webui/`。

---

## 通用搬迁规程（每个领域 Task 都照此做）

**搬 router（Phase A）**：
1. 在 `webui/routers/<domain>.py` 建 `from fastapi import APIRouter, ...`（按需）+ **`from webui import app_instance`**（⚠️**不要** `from webui.app_instance import APP`——import 时会把 APP 绑死成 None/旧实例，测试 reload 后路由指旧实例）+ 该域所需 models/依赖 import；`router = APIRouter()`。
2. 把 `main.py` 里该域的 `@app.xxx(...)` 端点函数**整体剪切**过去，装饰器 `@app.` → `@router.`。函数体里 `APP.xxx()` → **`app_instance.APP.xxx()`**（活属性，调用时查）。其余路径/参数/逻辑**一字不改**。
3. `main.py` 顶部 `from webui.routers import <domain> as <domain>_router` + 末尾（在 `_ai_mod.APP = APP` **之后**）`app.include_router(<domain>_router.router)`。
4. 跑回归门 + `python -m uv run python -c "import webui.main"` 冒烟。**特别盯 reload 类测试**（test_copy_images_multi/test_gallery_endpoints 等 reload main 后打端点）——它们验证活属性是否生效。

**搬 mixin（Phase B）**：
1. 在 `webui/services/_<domain>.py` 建 `class <Domain>Mixin:`，把 `App` 里该域方法**整体剪切**进来（含私有 `_xxx`）。方法体一字不改。
2. 文件顶部补该域方法体用到的 import（模块级 + 顶层 import 的；很多已是局部 `# noqa: PLC0415` 局部 import，无需搬）；helper 从 `webui.services._helpers import ...`；常量同理。
3. `app_service.py`：`from webui.services._<domain> import <Domain>Mixin` + `class App(... , <Domain>Mixin):` 加进继承列表。
4. 跑回归门 + 冒烟。
> mixin 互通：跨域 `self.xxx()` 调用**无需 import**（同实例）。只需补"模块级函数/常量/第三方/包"的 import。

---

### Task 1: 基础设施 —— app_instance.py + routers/services 包骨架 + _helpers 抽取

**Files:** 新建 `webui/app_instance.py`、`webui/routers/__init__.py`、`webui/services/__init__.py`、`webui/services/_helpers.py`；改 `main.py`、`app_service.py`。

- [ ] **Step 1**：建 `webui/app_instance.py`：
```python
"""全局 App 单例（抽出以避免 routers ↔ main 循环 import）。"""
from webui.app_service import App
APP = App()
```
- [ ] **Step 2**：`main.py` 把 `APP = App()` 改成 `from webui.app_instance import APP`（删原 `App()` 构造；保留其它 import）。跑 `python -c "import webui.main"` + 回归门，确认搬单例无回归。
- [ ] **Step 3**：建 `webui/services/__init__.py`(空)、`webui/services/_helpers.py`：把 `app_service.py` 的**模块级纯函数**（`_money_to_float,_to_int,_parse_dims_mm,_parse_volume_ml,_parse_weight_g,_has_cjk,_attr_language,_models_url,_is_country_attr,_download_bytes,_img_type_from_label,step_flags`）+ 它们用到的常量/import 移过去。`app_service.py` 顶部 `from webui.services._helpers import *`（或具名）**re-export**（`step_flags` 等被外部 import，路径兼容）。
- [ ] **Step 4**：建 `webui/routers/__init__.py`(空)。
- [ ] **Step 5**：回归门 ≥530 + 冒烟 + `grep -rn "from webui.app_service import step_flags\|app_service.step_flags" apps/webui` 确认外部引用仍可解析。
- [ ] **Step 6**：提交 `refactor(webui): 抽 app_instance 单例 + services/_helpers + routers/services 包骨架`。

---

### Task 2: Phase A 路由批 1 —— auth/settings/category/drafts

按"搬 router 规程"把这 4 域端点搬到 `webui/routers/{auth,settings,category,drafts}.py`。
- 端点归属看 `main.py` 现有 `@app.` 装饰器路径：`/api/login`,`/api/users*`,`/api/wallet*`→auth；`/api/state`,`/api/settings`→settings；`/api/category*`,`/api/attribute*`→category；`/api/drafts`(CRUD/list/get/update/copy/batch-update/delete/variant-group)→drafts。
- 回归门 + 冒烟。提交 `refactor(webui): main.py 拆 routers 批1(auth/settings/category/drafts)`。

---

### Task 3: Phase A 路由批 2 —— publish/ai/gallery/ext/pricing/warehouse

把剩余端点搬到 `webui/routers/{publish,ai_text,ai_image,ai_video,gallery,ext,pricing,warehouse}.py`（ai 相关按文案/出图/视频分文件）。
- publish/batch-publish/preflight/pull-products/variant-group-publish/fbs→publish；ai-generate/ai-copy/ai-fill-attributes/ai-proposal*→ai_text；ai-image/design-image-plan/image-plan/generate-plan-slot/candidates/whiten/scene/regen/localize/infographic/rich→ai_image；ai-video→ai_video；gallery/add|remove|reorder、images/{id} DELETE、copy-images-to→gallery；ext/*、media、snapshot→ext；realfbs-routes/commission*/commission-map→pricing；warehouses/pull-fbs/procurement/ship→warehouse。
- `main.py` 最终只剩：建 app、中间件/异常、`include_router` 全装、SPA/静态挂载、`if __name__`。
- 回归门 + 冒烟 + 起 `python -m uv run ozon-webui <port>` 确认能起。提交 `refactor(webui): main.py 拆 routers 批2 + main 瘦身成装配层`。

---

### Task 4-9: Phase B 领域 mixin（每 Task 一组，按"搬 mixin 规程"）

每个 Task 建 `webui/services/_<domain>.py` 的 Mixin、搬方法、`App` 加继承、跑回归门。**一组搬完整跑 ≥530 再下一组**：

- [ ] **Task 4**：`AuthMixin`(_auth) + `SettingsMixin`(_settings)。提交 `refactor(webui): App 拆 Auth/Settings mixin`。
- [ ] **Task 5**：`CategoryMixin`(_category) + `DraftMixin`(_drafts)。提交同式。
- [ ] **Task 6**：`PublishMixin`(_publish)。（发布最纠缠，单独一组）
- [ ] **Task 7**：`AiCardMixin`(_ai_card)。（含 ai_generate/ai_copy/proposal/understand/物理量）
- [ ] **Task 8**：`AiImageMixin`(_ai_image) + `AiVideoMixin`(_ai_video)。（含候选/计划/批量）
- [ ] **Task 9**：`GalleryMixin`(_gallery) + `ExtMixin`(_ext) + `GenJobMixin`(_genjobs) + `PricingMixin`(_pricing) + `WarehouseMixin`(_warehouse)。（剩余较独立的域）
- 每 Task：搬完 `App(...)` 继承列表加上、`from webui.services._<d> import <D>Mixin`、回归门 ≥530 + `python -c "import webui.app_service; webui.app_service.App"` 冒烟。
- 收尾：`app_service.py` 只剩 `class App(全部Mixin): __init__`(store/catalog/catalog_ru/_cand_lock/_ensure_auth_bootstrap) + 顶部 import + helper re-export。

---

### Task 10: 收尾验证 + 文档

- [ ] **Step 1**：全量回归 ≥530(webui)/714(含packages) + `python -m uv run ozon-webui` 起后端，curl 代表端点（`GET /api/state` 需登录略；`GET /api/category/tree`、种一草稿 `GET /api/drafts/{id}`、`POST /api/drafts/{id}/gallery/add`）确认契约不变。前端 `npm run build` 不受影响。
- [ ] **Step 2**：建 `docs/product/backend-architecture.md`（新模块文档）：webui 应用层结构（app_instance/services 各 mixin/routers 各域/main 装配层）、领域边界表、"App=facade 组合 mixin、router 只调 APP"的约定。
- [ ] **Step 3**：提交 `docs(product): 后端 webui 应用层架构(mixin/routers)文档 + 收尾验证`。

---

## Controller 复核（每 Task 后 + 全部后）
- 每 Task：读 diff（确认是**纯剪切**、无逻辑改/签名改/路径改）、自己重跑回归门（≥714、0 新失败）、`import webui.main` 冒烟。
- 全部后：起后端 curl 代表端点契约不变 + 前端 build 不受影响。
- ⚠️ 任一 Task 回归掉到 <714 或冒烟失败 → 多半是 import 漏带/循环 import，**当 Task 内修到绿**，不带病进下一域。
