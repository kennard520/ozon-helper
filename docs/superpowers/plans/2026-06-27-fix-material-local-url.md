# 修复：素材行携带本地代理 local_url（采集图防盗链显示）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。逐任务 TDD。

**问题（验收实证）**：`materials` 行只有 `id/url/type/source/in_gallery/position`，无本地代理；`draft.local_images` 只并行图集。采集素材(原始 1688 防盗链)在素材库显示破图。`draft_images` 表无 local 列；reorder 会重排 position 故**不能**靠 position 索引 `local_images`。

**正解**：给 `draft_images` 加 `local_url` 列，采集落库时按原始下标从 `local_images` 取值随行存（不可变），getDraft 的 materials 返回它，前端优先用它显示。

**架构**：纯加列（nullable + server_default="")，对存量行无影响（local_url=""→前端回退原逻辑）。采集图 `_sync_draft_images(gallery=False)` 时 `images[i]↔local_images[i]` 平行，取 `local_images[i]`。生成图(gallery=True 新插)local_url=""(url 本就可显示)。

**Tech**：Python/SQLAlchemy Core、Alembic、pytest（`python -m uv run pytest`）；前端 Vitest。

---

### Task 1: 后端 —— draft_images 加 local_url 列 + 采集落库 + getDraft 返回

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/schema.py`（draft_images 加列）
- Create: `migrations/versions/0007_draft_image_local_url.py`
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py`（_sync_draft_images 收 local_images、insert/update 传入、_load_draft_images 选列、_row_to_draft material 返回）
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_image_repo.py`（add_draft_image 收 local_url；copy_images 带源 local_url）
- Test: `apps/webui/tests/`（新增或就近）

- [ ] **Step 1: 写失败测试**

新建 `apps/webui/tests/test_material_local_url.py`（**照搬 `test_copy_images_multi.py`/`test_gallery_endpoints.py` 的范式**：`store_mod.DEFAULT_DB = 临时库 + importlib.reload(svc) + reload(main)`，用 `app.store.insert_draft`，无需手建用户）:
```python
import importlib, tempfile, unittest
from pathlib import Path


class MaterialLocalUrlTest(unittest.TestCase):
    def _app(self, tmp):
        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "mat_local.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        return main_mod.app

    def test_collected_material_carries_local_url(self):
        from webui.drafts import create_draft_from_url  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            d = create_draft_from_url("https://detail.1688.com/offer/LU1.html")
            d["images"] = ["http://raw/a.jpg", "http://raw/b.jpg"]
            d["local_images"] = ["/media/a.jpg", "/media/b.jpg"]
            row = app.store.insert_draft(d)
            got = app.store.get_draft(row["id"])
            mats = {m["url"]: m for m in got["materials"]}
            self.assertEqual(mats["http://raw/a.jpg"]["local_url"], "/media/a.jpg")
            self.assertEqual(mats["http://raw/b.jpg"]["local_url"], "/media/b.jpg")
```
> **实现时先翻一眼 `test_gallery_endpoints.py` 确认 reload 范式细节一致**。核心断言不变：采集 materials 的 `local_url` == 对应 `local_images[i]`。create_draft_from_url 返回的 draft 已含全部必填字段，只需覆盖 images/local_images。

- [ ] **Step 2: 跑测试确认失败**

Run（仓库根）: `python -m uv run pytest apps/webui/tests/test_material_local_url.py -x -q`
Expected: FAIL（materials 无 local_url 键 / KeyError）

- [ ] **Step 3: schema 加列**

`packages/ozon_common/src/ozon_common/dal/schema.py` 的 `draft_images` 定义里，`in_gallery` 那列后加：
```python
    Column("local_url", String(1024), nullable=False, server_default=""),
```
（用 String 不用 Text——有 server_default 的列在 MySQL 上不能是 Text，沿用 in_gallery 同类处理。）

- [ ] **Step 4: 迁移 0007**

新建 `migrations/versions/0007_draft_image_local_url.py`，照搬 `0006_in_gallery.py` 的结构（down_revision 指向 0006；SQLite 走 create_all 已含列故 `if bind.dialect.name != "mysql": return` 跳过，仅 MySQL `op.add_column`）：
```python
"""draft_images.local_url

Revision ID: 0007_draft_image_local_url
Revises: 0006_in_gallery
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_draft_image_local_url"
down_revision = "0006_in_gallery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.add_column("draft_images", sa.Column("local_url", sa.String(1024),
                  nullable=False, server_default=""))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.drop_column("draft_images", "local_url")
```
> 实现时**核对 0006 文件实际的 revision id/写法**，与之对齐（id 字符串、import 风格、是否有 branch_labels）。

- [ ] **Step 5: 落库 + 读取携带 local_url**

`draft_repo.py`：
1. `_sync_draft_images` 签名加 `local_images: list[str] | None = None`。gallery=False 分支 INSERT 时加 `local_url=(local_images[i] if local_images and i < len(local_images) else "")`。gallery=True 新插（generated）`local_url=""`。
2. `insert_draft` 调用处传 `local_images=draft.get("local_images")`。
3. `update_draft` 调用 `_sync_draft_images` 处传 `local_images=updated.get("local_images")`。
4. `_load_draft_images`（和批量版 `_load_draft_images_batch` 若有）的 `select(...)` 加选 `DI.c.local_url`，构造的 dict 里带 `local_url`。
5. `_row_to_draft` 的 `materials` 每项加 `"local_url": r.get("local_url", "")`。

`draft_image_repo.py`：
6. `add_draft_image(...)` 签名加 `local_url: str = ""`，INSERT 带上。
7. `copy_images`：源行 select 也取 `local_url`，复制时 `add_draft_image(..., local_url=sr.local_url)`（让借来的图也带代理）。对应 select 加列。

- [ ] **Step 6: 跑测试确认通过 + 回归**

Run: `python -m uv run pytest apps/webui/tests/test_material_local_url.py -x -q`
Expected: PASS

Run 回归: `python -m uv run pytest -q`
Expected: 全绿（既有 media/draft_repo/image 测试不回归；若有断言 materials 形状的测试需补 local_url 键，照实改）。

- [ ] **Step 7: 提交**

```bash
git add packages/ozon_common/src/ozon_common/dal/schema.py migrations/versions/0007_draft_image_local_url.py packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py packages/ozon_common/src/ozon_common/dal/repositories/draft_image_repo.py apps/webui/tests/test_material_local_url.py
git commit -m "fix(images): draft_images 加 local_url 列——采集素材随行存本地代理(防盗链显示),迁移0007 + getDraft materials 返回"
```

---

### Task 2: 前端 —— useGallery/ImagesTab 用 local_url + 文档

**Files:**
- Modify: `apps/webui/frontend/src/composables/useGallery.js`
- Modify: `apps/webui/frontend/src/composables/useGallery.test.js`
- Modify: `apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue`
- Modify: `docs/product/material-gallery.md`

- [ ] **Step 1: 改测试（先红）**

在 `useGallery.test.js` 的 mkDraft 给一个素材加 `local_url`，加断言：`localUrl(item)` 优先 item.local_url。把 `localUrl` 改成接受 item（或 url+localUrl）。新增用例：
```js
it('localUrl 优先 item.local_url', () => {
  const g = useGallery(mkDraft(), { onChange: vi.fn() })
  // 给 materialItems[0] 注入 local_url 后断言
  expect(g.localUrlOf({ url: 'http://m/3.jpg', local_url: '/media/3.jpg' })).toBe('/media/3.jpg')
  expect(g.localUrlOf({ url: 'http://g/1.jpg', local_url: '' })).toBe('/media/1.jpg') // 回退图集 zip
})
```
> 保留原 `localUrl(url)`（图集 zip 回退）；新增 `localUrlOf(item)` = `item.local_url || localUrl(item.url)`。原有用例不破坏。

- [ ] **Step 2: 跑红** `npm run test -- useGallery` → FAIL

- [ ] **Step 3: 实现**

`useGallery.js` 加导出：
```js
function localUrlOf(item) { return (item && item.local_url) || localUrl(item && item.url) }
```
return 里加 `localUrlOf`。

- [ ] **Step 4: 跑绿** `npm run test -- useGallery` → PASS

- [ ] **Step 5: ImagesTab 用 localUrlOf**

`ImagesTab.vue` 把三段 ImageCard 的 `:local-url` 改用 `g.localUrlOf(it)` / `g.localUrlOf(m)`（借图段 borrowMats 也用 `g.localUrlOf(m)`，这样借来预览也走代理）。

- [ ] **Step 6: 全量 + 提交**

Run: `npm run test`（≤32 基线不新增）
```bash
git add apps/webui/frontend/src/composables/useGallery.js apps/webui/frontend/src/composables/useGallery.test.js apps/webui/frontend/src/components/workbench/tabs/ImagesTab.vue
git commit -m "fix(images): 前端素材/借图预览优先 local_url(localUrlOf) 显示防盗链采集图"
```

- [ ] **Step 7: 文档**

`docs/product/material-gallery.md` 的「已知风险」段改为「已修复」：draft_images 加 local_url 列（迁移 0007），采集随行存、getDraft materials 返回、前端 localUrlOf 优先用。变更历史加一行。
```bash
git add docs/product/material-gallery.md
git commit -m "docs(product): material local_url 已修复(防盗链显示)"
```

---

## Controller 复核
- T1 后：读 diff，确认列/迁移/落库/读取一致；`python -m uv run pytest -q` 全绿；**端到端**起后端种采集草稿（带 local_images），curl getDraft 确认 materials 带 local_url。
- T2 后：`npm run test` ≤32 基线；起后端 + 前端浏览器看素材区是否用 /media 代理显示。
- ⚠️ MySQL 全新部署：create_all 已含 local_url；0007 迁移给存量 MySQL 库加列——上线前在真 MySQL 验证（并入 dal-m4 验证清单）。
