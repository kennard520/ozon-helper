# 采集后自动发布到 Ozon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加一个用户级开关 `auto_publish`，开启后采集生成草稿即自动后台发布到 Ozon（原样直发，发不出去的静默留草稿）。

**Architecture:** 复用现有 `settings` 表存开关（无 schema 变更）。采集流程 `ext_collect_parsed` 和媒体回调 `update_draft_media` 各调一个新方法 `_maybe_auto_publish`，它读设置 + 查草稿状态/媒体状态守卫后，派发后台线程跑现成的 `publish()`。后台线程复用 `contextvars.copy_context()` 带 `current_user_id`，整段 best-effort 吞异常。

**Tech Stack:** Python (FastAPI + 自研 Store)、Vue 3 + Element Plus、pytest、vitest。

> 工作目录：`ozon-listing-webui/`。后端测试命令在该目录下跑 `python -m pytest ...`；前端在 `ozon-listing-webui/frontend/` 下跑 `npx vitest run ...`。

---

## 文件结构

- `backend/models.py` — `SettingsIn` 加 `auto_publish` 字段（API 入参白名单）。
- `backend/app_service.py` —
  - `save_settings()` 加 `auto_publish` 持久化分支（存储白名单）；
  - `state()` 暴露字典加 `auto_publish`（回传前端做回填）；
  - 新增 `_maybe_auto_publish()` + `_dispatch_auto_publish()`；
  - `ext_collect_parsed()` 两个返回分支、`update_draft_media()` 各加一行调用。
- `backend/tests/test_auto_publish.py` — 新建，后端全部用例。
- `frontend/src/views/Settings.vue` — 加 `auto_publish` 表单项 + 回填 + 保存 + UI 开关。
- `frontend/tests/settings.spec.js` — 加一条开关读写用例。

---

## Task 1: 后端设置三处接通（入参/存储/回传）

**Files:**
- Modify: `backend/models.py:22`（`SettingsIn`，`ai_auto_apply` 旁）
- Modify: `backend/app_service.py:370`（`save_settings` 的 allowed，`ai_auto_apply` 分支旁）
- Modify: `backend/app_service.py:309`（`state()` 暴露字典，`ai_auto_apply` 旁）
- Test: `tests/test_auto_publish.py`

- [ ] **Step 1: 写失败测试（设置往返）**

新建 `tests/test_auto_publish.py`，先放这一段：

```python
from __future__ import annotations
import importlib
import tempfile
import unittest
from pathlib import Path


def _make_app(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import backend.app_service as svc
    importlib.reload(svc)
    app = svc.App()
    app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k"})
    return svc, app


class SettingsRoundTripTest(unittest.TestCase):
    def test_auto_publish_persists_and_exposed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                # 默认未设置 → state 暴露为 False
                self.assertFalse(app.state()["settings"]["auto_publish"])
                # 存 True → 持久化 + state 回传 True
                app.save_settings({"auto_publish": True})
                self.assertTrue(app.store.get_settings().get("auto_publish"))
                self.assertTrue(app.state()["settings"]["auto_publish"])
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_auto_publish.py::SettingsRoundTripTest -v`
Expected: FAIL（`state()["settings"]` 里没有 `auto_publish` 键 → KeyError）

- [ ] **Step 3: 加 `SettingsIn` 字段**

`backend/models.py`，在 `ai_auto_apply: bool | None = None`（第 22 行）下一行加：

```python
    auto_publish: bool | None = None
```

- [ ] **Step 4: 加 `save_settings` 持久化分支**

`backend/app_service.py`，在 `save_settings` 的 `ai_auto_apply` 分支（约 370-371 行）后紧接着加：

```python
        if payload.get("auto_publish") is not None:
            allowed["auto_publish"] = bool(payload["auto_publish"])
```

- [ ] **Step 5: `state()` 暴露字典加键**

`backend/app_service.py`，在 `state()` 的 `"ai_auto_apply": bool(settings.get("ai_auto_apply")),`（约第 309 行）后加一行：

```python
                # 采集后自动发布到 Ozon：true=采集即自动发 / false=只建草稿（默认）
                "auto_publish": bool(settings.get("auto_publish")),
```

- [ ] **Step 6: 跑测试确认通过**

Run: `python -m pytest tests/test_auto_publish.py::SettingsRoundTripTest -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/models.py backend/app_service.py tests/test_auto_publish.py
git commit -m "feat(app): settings 加 auto_publish 开关（入参/存储/回传三处接通）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `_maybe_auto_publish` + `_dispatch_auto_publish` 守卫逻辑

**Files:**
- Modify: `backend/app_service.py`（新增两个方法，建议放在 `ext_collect_parsed` 上方、`update_draft_media` 附近）
- Test: `tests/test_auto_publish.py`

守卫逻辑：开关开 **且** 草稿存在 **且** `status != 'published'`（幂等防重发）**且** `media_status != 'pending'`（媒体未传完则等媒体回调再发）→ 才派发。`media_status` 这条守卫使同一方法在「采集时（有媒体则 pending）」和「媒体 done 回调」两个调用点都正确。

- [ ] **Step 1: 写失败测试（守卫四分支）**

在 `tests/test_auto_publish.py` 末尾（`if __name__` 之前）加：

```python
def _draft(**kw):
    from backend.drafts import utc_now_iso
    now = utc_now_iso()
    d = {
        "user_id": 1, "store_client_id": "",
        "source_platform": "ozon", "source_url": kw.get("url", "https://www.ozon.ru/product/g-1/"),
        "source_offer_id": "", "source_title": "t", "purchase_url": "", "purchase_note": "",
        "ozon_title": "t", "description": "", "category_id": "", "type_id": "",
        "brand_id": None, "brand_name": "", "price": "1", "old_price": "",
        "stock": 0, "weight_g": None, "length_mm": None, "width_mm": None, "height_mm": None,
        "cost_cny": None, "video_url": "", "local_images_json": None,
        "source": "", "ozon_product_id": None, "offer_id": "", "supplier": "", "source_raw": {},
        "images": kw.get("images", []), "attributes": [],
        "status": kw.get("status", "draft"), "validation_errors": [], "publish_response": None,
        "created_at": now, "updated_at": now,
    }
    return d


class MaybeAutoPublishGuardTest(unittest.TestCase):
    def _setup(self, tmp, *, auto, status="draft", media="done", images=None):
        svc, app = _make_app(tmp)
        app.save_settings({"auto_publish": auto})
        saved = app.store.insert_draft(_draft(status=status, images=images or []))
        if media != "done":
            app.store.set_media_status(saved["id"], media)
        calls = []
        app._dispatch_auto_publish = lambda did: calls.append(did)
        return app, saved["id"], calls

    def test_on_and_ready_dispatches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=True)
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [did])
            finally:
                app.store.close()

    def test_off_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=False)
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_media_pending_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=True, media="pending",
                                          images=["https://ir.ozone.ru/a.jpg"])
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_already_published_does_not_dispatch(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, calls = self._setup(tmp, auto=True, status="published")
            try:
                app._maybe_auto_publish(did)
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_dispatch_raise_is_swallowed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, did, _ = self._setup(tmp, auto=True)
            try:
                def _boom(_did):
                    raise RuntimeError("boom")
                app._dispatch_auto_publish = _boom
                app._maybe_auto_publish(did)  # 不抛错即通过
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_auto_publish.py::MaybeAutoPublishGuardTest -v`
Expected: FAIL（`App` 无 `_maybe_auto_publish` 属性 → AttributeError）

- [ ] **Step 3: 实现两个方法**

`backend/app_service.py`，在 `ext_collect_parsed` 方法定义上方加：

```python
    def _maybe_auto_publish(self, draft_id: int) -> None:
        """采集/媒体就绪后，若用户开了 auto_publish 且草稿可发，则后台发布到 Ozon。
        守卫：开关开 + 草稿存在 + status!=published（幂等）+ media_status!=pending（等媒体）。
        best-effort：整段吞异常，发不出去的草稿原样留 webui 等人工。"""
        try:
            if not bool((self.store.get_settings() or {}).get("auto_publish")):
                return
            draft = self.store.get_draft(draft_id)
            if draft is None:
                return
            if str(draft.get("status") or "") == "published":
                return
            if str(draft.get("media_status") or "done") == "pending":
                return
            self._dispatch_auto_publish(draft_id)
        except Exception:  # noqa: BLE001
            pass

    def _dispatch_auto_publish(self, draft_id: int) -> None:
        """派发后台线程跑 publish()，不阻塞采集（publish 会轮询 Ozon ~20s）。
        复制父线程 context 把 current_user_id 带进子线程（否则用错 Ozon 凭证）。
        抽成单独方法：测试 monkeypatch 本方法即可同步断言、不起真线程。"""
        import contextvars  # noqa: PLC0415
        import threading  # noqa: PLC0415
        ctx = contextvars.copy_context()

        def _run() -> None:
            try:
                ctx.run(self.publish, draft_id)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_auto_publish.py::MaybeAutoPublishGuardTest -v`
Expected: PASS（5 个用例全过）

- [ ] **Step 5: 提交**

```bash
git add backend/app_service.py tests/test_auto_publish.py
git commit -m "feat(app): _maybe_auto_publish 守卫 + _dispatch_auto_publish 后台线程

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 接入采集流程与媒体回调

**Files:**
- Modify: `backend/app_service.py:1550`（`ext_collect_parsed` dedup 分支 return 前）
- Modify: `backend/app_service.py:1555`（`ext_collect_parsed` insert 分支 return 前）
- Modify: `backend/app_service.py:1564`（`update_draft_media` return 前）
- Test: `tests/test_auto_publish.py`

- [ ] **Step 1: 写失败测试（端到端接入）**

在 `tests/test_auto_publish.py` 末尾（`if __name__` 之前）加：

```python
class CollectAutoPublishWiringTest(unittest.TestCase):
    def _app(self, tmp, auto):
        svc, app = _make_app(tmp)
        app._auto_match_category = lambda scraped: None
        app._auto_map_safe = lambda did: None
        app.save_settings({"auto_publish": auto})
        calls = []
        app._dispatch_auto_publish = lambda did: calls.append(did)
        return app, calls

    def test_no_media_dispatches_on_collect(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp, auto=True)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-1/",
                                              "data": {"title": "t", "images": []}})
                did = res["created"][0]["id"]
                self.assertEqual(calls, [did])  # 无媒体 → 采集即派发
            finally:
                app.store.close()

    def test_has_media_defers_to_update_draft_media(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp, auto=True)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-2/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                self.assertEqual(calls, [])  # 有媒体（pending）→ 采集时不派发
                app.update_draft_media({"draft_id": did,
                                        "media_map": {"https://ir.ozone.ru/a.jpg": "https://oss/a.jpg"}})
                self.assertEqual(calls, [did])  # 媒体 done 后才派发
            finally:
                app.store.close()

    def test_off_never_dispatches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, calls = self._app(tmp, auto=False)
            try:
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-3/",
                                              "data": {"title": "t", "images": []}})
                did = res["created"][0]["id"]
                app.update_draft_media({"draft_id": did, "media_map": {}})
                self.assertEqual(calls, [])
            finally:
                app.store.close()

    def test_collect_survives_dispatch_failure(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app, _ = self._app(tmp, auto=True)
            try:
                def _boom(_did):
                    raise RuntimeError("boom")
                app._dispatch_auto_publish = _boom
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/ap-4/",
                                              "data": {"title": "t", "images": []}})
                self.assertTrue(res["created"])  # 采集照常返回，best-effort 吞掉
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_auto_publish.py::CollectAutoPublishWiringTest -v`
Expected: FAIL（`calls` 为空 / 未在采集后派发——调用点还没接）

- [ ] **Step 3: 接入三个调用点**

`backend/app_service.py`，`ext_collect_parsed` dedup 分支，把：

```python
            self._auto_map_safe(existing["id"])   # 采集后自动映射属性（已本地缓存化，快）
            return {"created": [{"id": existing["id"], "source_title": existing.get("source_title")}], "errors": [], "deduped": True}
```

改成：

```python
            self._auto_map_safe(existing["id"])   # 采集后自动映射属性（已本地缓存化，快）
            self._maybe_auto_publish(existing["id"])   # 开了 auto_publish 则后台发布
            return {"created": [{"id": existing["id"], "source_title": existing.get("source_title")}], "errors": [], "deduped": True}
```

同方法 insert 分支，把：

```python
        self._auto_map_safe(saved["id"])   # 采集后自动映射属性（已本地缓存化，快）
        return {"created": [{"id": saved["id"], "source_title": saved.get("source_title")}], "errors": []}
```

改成：

```python
        self._auto_map_safe(saved["id"])   # 采集后自动映射属性（已本地缓存化，快）
        self._maybe_auto_publish(saved["id"])   # 开了 auto_publish 则后台发布
        return {"created": [{"id": saved["id"], "source_title": saved.get("source_title")}], "errors": []}
```

`update_draft_media`，把：

```python
        self.store.apply_media_oss(draft_id, dict(media_map))
        return {"ok": True}
```

改成：

```python
        self.store.apply_media_oss(draft_id, dict(media_map))
        self._maybe_auto_publish(draft_id)   # 媒体传完 → 开了 auto_publish 则后台发布
        return {"ok": True}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_auto_publish.py -v`
Expected: PASS（全文件 3 个类全过）

- [ ] **Step 5: 提交**

```bash
git add backend/app_service.py tests/test_auto_publish.py
git commit -m "feat(app): 采集/媒体回调接入 auto_publish（无媒体即发，有媒体待传完再发）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 前端设置页开关

**Files:**
- Modify: `frontend/src/views/Settings.vue`（`form`、`backfill`、`save`、模板）
- Test: `frontend/tests/settings.spec.js`

- [ ] **Step 1: 写失败测试**

`frontend/tests/settings.spec.js`，在 `describe('Settings.vue', ...)` 内加一条（仿 `ai_auto_apply` 用例）：

```javascript
  it('保存时带 auto_publish', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    w.vm.form.auto_publish = true
    await w.vm.save()
    expect(spy.mock.calls[0][0].auto_publish).toBe(true)
  })

  it('回填 auto_publish', async () => {
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = { auto_publish: true, contract_currency: 'CNY' }
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await w.vm.$nextTick()
    expect(w.vm.form.auto_publish).toBe(true)
  })
```

- [ ] **Step 2: 跑测试确认失败**

Run（在 `frontend/` 目录）：`npx vitest run tests/settings.spec.js`
Expected: FAIL（`payload.auto_publish` 为 undefined；回填用例 `form.auto_publish` 为 undefined）

- [ ] **Step 3: `form` 加字段**

`frontend/src/views/Settings.vue`，`form` reactive（第 9-13 行）加 `auto_publish: false`：

```javascript
const form = reactive({
  rub_cny: 0,
  contract_currency: 'CNY',
  ai_auto_apply: false,
  auto_publish: false,
})
```

- [ ] **Step 4: `backfill` 回填**

同文件 `backfill` 函数（第 18-24 行），在 `ai_auto_apply` 回填行后加：

```javascript
  if (s.auto_publish != null) form.auto_publish = s.auto_publish
```

- [ ] **Step 5: `save` 发送**

同文件 `save` 函数，在 `payload.ai_auto_apply = form.ai_auto_apply`（第 54 行）后加：

```javascript
  payload.auto_publish = form.auto_publish
```

- [ ] **Step 6: 模板加开关**

同文件模板，在「AI 卡片应用」`el-form-item`（第 167-175 行）后加：

```html
      <el-form-item label="采集后自动发布">
        <el-radio-group v-model="form.auto_publish">
          <el-radio :value="false">只建草稿</el-radio>
          <el-radio :value="true">自动发布到 Ozon</el-radio>
        </el-radio-group>
        <div style="font-size:12px;color:var(--c-text-3);margin-top:4px">
          开启后采集会直接发到 Ozon（原样直发，到 Ozon 后台再改）；发不出去的留草稿等你手动补。
        </div>
      </el-form-item>
```

- [ ] **Step 7: 跑测试确认通过**

Run（在 `frontend/` 目录）：`npx vitest run tests/settings.spec.js`
Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add frontend/src/views/Settings.vue frontend/tests/settings.spec.js
git commit -m "feat(ui): 设置页加「采集后自动发布」开关

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 全量回归

**Files:** 无（只跑测试）

- [ ] **Step 1: 后端全量**

Run（在 `ozon-listing-webui/` 目录）：`python -m pytest tests/ -q`
Expected: 全绿（重点确认 `test_ext_bridge`、`test_media_async`、`test_settings_api`、`test_batch_publish`、`test_oss_publish` 不破）

- [ ] **Step 2: 前端全量**

Run（在 `ozon-listing-webui/frontend/` 目录）：`npx vitest run`
Expected: 全绿

- [ ] **Step 3: 如有回归失败**

按 superpowers:systematic-debugging 定位修复；修完重跑直到全绿。无失败则跳过。

---

## 自查（写计划后回看 spec）

- **Spec 覆盖**：配置项→Task 1；触发点（无媒体/有媒体两条）→Task 3；执行模型（后台线程/best-effort/幂等守卫）→Task 2；前端→Task 4；测试矩阵→Task 1-4；回归→Task 5。全覆盖。
- **占位符**：无 TBD/TODO，每步含完整代码与命令。
- **类型/命名一致**：`auto_publish`（设置键）、`_maybe_auto_publish` / `_dispatch_auto_publish`（方法名）跨 Task 一致；`_make_app` / `_draft` 测试辅助与 `test_media_async.py` 同形。
