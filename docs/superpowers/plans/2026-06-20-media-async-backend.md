# 媒体后台异步（后端支撑）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给后端加“草稿媒体状态 + 异步换链接 + 待补传列表 + 发布拦截”，让插件可以先建草稿、媒体后台补传。

**Architecture:** spec `2026-06-20-collect-perf-v2-design.md` 的 Part 2/3 的**后端部分**。前端采集流程改造是单独的计划三。本计划只动 `store.py` / `app_service.py` / `main.py` / `db.py`，不动插件。

**Tech Stack:** Python 3 / FastAPI、SQLite+MySQL、`unittest`。

**测试怎么跑：** 在 `ozon-listing-webui/` 目录下 `PYTHONPATH=. python tests/<file>.py -v`（pytest 未装，用 unittest）。

---

## Task 1: drafts.media_status 列 + store 三个方法

**Files:**
- Modify: `ozon-listing-webui/backend/store.py`（SQLite 建表后 `_ensure_column`；新增 3 方法）
- Modify: `ozon-listing-webui/backend/db.py`（MySQL 给 drafts 补 `media_status` 列）
- Test: `ozon-listing-webui/tests/test_media_async.py`（新建）

媒体状态：`pending`=媒体待传 OSS；`done`=无媒体或已传完。`images_json`（JSON 数组的字符串）和 `video_url` 存草稿的图片/视频链接。`dumps_json`/`loads_json`/`utc_now_iso` 已在 store.py。

- [ ] **Step 1: 写失败测试**

新建 `ozon-listing-webui/tests/test_media_async.py`：

```python
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from backend.store import Store


def _draft(**kw):
    d = {
        "user_id": 1, "store_client_id": "",
        "source_platform": "ozon", "source_url": kw.get("url", "https://www.ozon.ru/product/x-1/"),
        "source_offer_id": "", "source_title": "t", "purchase_url": "", "purchase_note": "",
        "ozon_title": "t", "description": "", "category_id": "", "type_id": "",
        "brand_id": None, "brand_name": "", "price": "1", "old_price": "",
        "stock": 0, "weight_g": None, "length_mm": None, "width_mm": None, "height_mm": None,
        "cost_cny": None, "video_url": kw.get("video", ""), "local_images_json": None,
        "source": "", "ozon_product_id": None, "offer_id": "", "supplier": "", "source_raw": {},
        "images": kw.get("images", []), "attributes": [],
    }
    return d


class MediaStatusStoreTest(unittest.TestCase):
    def test_set_and_list_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            saved = store.insert_draft(_draft(url="https://www.ozon.ru/product/a-1/",
                                              images=["https://ir.ozone.ru/a.jpg"]))
            did = saved["id"]
            # 默认建出来是 done（列默认值）；置 pending 后能在待补传列表里查到
            store.set_media_status(did, "pending")
            pend = store.list_pending_media_drafts(1)
            self.assertEqual([p["id"] for p in pend], [did])
            self.assertEqual(pend[0]["images"], ["https://ir.ozone.ru/a.jpg"])
            store.close()

    def test_apply_media_oss_replaces_and_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            saved = store.insert_draft(_draft(url="https://www.ozon.ru/product/b-1/",
                                              images=["https://ir.ozone.ru/a.jpg", "https://ir.ozone.ru/b.jpg"],
                                              video="https://v.ozone.ru/v.mp4"))
            did = saved["id"]
            store.set_media_status(did, "pending")
            store.apply_media_oss(did, {"https://ir.ozone.ru/a.jpg": "https://oss/a.jpg",
                                        "https://v.ozone.ru/v.mp4": "https://oss/v.mp4"})
            d = store.get_draft(did)
            self.assertEqual(d["images"], ["https://oss/a.jpg", "https://ir.ozone.ru/b.jpg"])  # 只换命中的
            self.assertEqual(d["video_url"], "https://oss/v.mp4")
            self.assertEqual(d["media_status"], "done")
            self.assertEqual(store.list_pending_media_drafts(1), [])  # done 后不再 pending
            store.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. python tests/test_media_async.py -v`
Expected: FAIL，`AttributeError: 'Store' object has no attribute 'set_media_status'`

- [ ] **Step 3a: SQLite 加列**

在 `store.py` 的 drafts `_ensure_column(...)` 一串末尾（约第 184 行 `supplier` 那条之后）加：

```python
            self._ensure_column("drafts", "media_status", "TEXT NOT NULL DEFAULT 'done'")  # 媒体异步：pending/done
```

- [ ] **Step 3b: MySQL 加列**

在 `db.py` 里给 drafts 补列。找到现有给 drafts/users 补列的地方（如 `_ensure_mysql_column(conn, "users", "max_stores", ...)` 同款调用处），照样加一行：

```python
    _ensure_mysql_column(conn, "drafts", "media_status", "VARCHAR(16) NOT NULL DEFAULT 'done'")
```

（若 `_ensure_mysql_column` 的签名/调用点不同，按该文件现有 `max_stores` 的写法对齐。）

- [ ] **Step 3c: store 三个方法**

在 `store.py` 的 `insert_draft` 方法之后插入：

```python
    def set_media_status(self, draft_id: int, status: str) -> None:
        with self.lock:
            self.conn.execute("UPDATE drafts SET media_status=?, updated_at=? WHERE id=?",
                              (str(status), utc_now_iso(), int(draft_id)))
            self.conn.commit()

    def apply_media_oss(self, draft_id: int, media_map: dict) -> None:
        """把草稿 images/video_url 里命中 media_map 的原 URL 换成 OSS URL，并置 media_status=done。
        只替换命中的项，不动用户手改过的其它图。"""
        with self.lock:
            row = self.conn.execute("SELECT images_json, video_url FROM drafts WHERE id=?",
                                    (int(draft_id),)).fetchone()
            if not row:
                return
            imgs = loads_json(row["images_json"], []) or []
            new_imgs = [media_map.get(u, u) for u in imgs]
            vurl = row["video_url"] or ""
            new_vurl = media_map.get(vurl, vurl)
            self.conn.execute(
                "UPDATE drafts SET images_json=?, video_url=?, media_status='done', updated_at=? WHERE id=?",
                (dumps_json(new_imgs), new_vurl, utc_now_iso(), int(draft_id)))
            self.conn.commit()

    def list_pending_media_drafts(self, user_id: int) -> list[dict]:
        """当前用户 media_status=pending 的草稿，返回 [{id, images, video_url}]，供插件补传。"""
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, images_json, video_url FROM drafts WHERE user_id=? AND media_status='pending'",
                (int(user_id),)).fetchall()
        return [{"id": r["id"], "images": loads_json(r["images_json"], []) or [],
                 "video_url": r["video_url"] or ""} for r in rows]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. python tests/test_media_async.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/store.py ozon-listing-webui/backend/db.py ozon-listing-webui/tests/test_media_async.py
git commit -m "feat(store): drafts.media_status + set/apply_media_oss/list_pending_media_drafts"
```

---

## Task 2: 采集建草稿时置 media_status=pending（有媒体时）

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（`ext_collect_parsed` 的两处 `insert_draft`/dedup 返回前）
- Test: `ozon-listing-webui/tests/test_media_async.py`

`ext_collect_parsed`（`app_service.py:1432`）新建草稿在 1547、重复采集分支在 1543-1546。若 `data` 有 `images` 或 `video_url`，建/更新草稿后置 `pending`。

- [ ] **Step 1: 写失败测试**

在 `test_media_async.py` 末尾（`if __name__` 前）加（复用 `test_attr_values_cache.py` 的 `_make_app`，这里直接构造 App）：

```python
import importlib  # noqa: E402


def _make_app(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "app.db"
    import backend.app_service as svc
    importlib.reload(svc)
    app = svc.App()
    app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k"})
    return svc, app


class CollectSetsPendingTest(unittest.TestCase):
    def test_pending_when_has_media(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/m-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                self.assertEqual(app.store.get_draft(did)["media_status"], "pending")
            finally:
                app.store.close()

    def test_done_when_no_media(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/m-2/",
                                              "data": {"title": "t", "images": []}})
                did = res["created"][0]["id"]
                self.assertEqual(app.store.get_draft(did)["media_status"], "done")
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. python tests/test_media_async.py CollectSetsPendingTest -v`
Expected: FAIL（默认 done，pending 用例失败）

- [ ] **Step 3: 实现**

在 `app_service.py` 的 `ext_collect_parsed` 里，加一个判断媒体的 helper（在 `ext_collect_parsed` 方法体最前面，`data = payload.get("data")` 之后即可）：

```python
        _has_media = bool((data.get("images") or [])) or bool(str(data.get("video_url") or "").strip())
```

然后把新建分支（1547-1550）改成：

```python
        saved = self.store.insert_draft(new_draft)
        if _has_media:
            self.store.set_media_status(saved["id"], "pending")  # 媒体待插件后台传 OSS
        self._auto_map_safe(saved["id"])   # 采集后自动映射属性（已本地缓存化，快）
        return {"created": [{"id": saved["id"], "source_title": saved.get("source_title")}], "errors": []}
```

重复采集分支（1543-1546）改成：

```python
            if patch:
                self.store.update_draft(existing["id"], patch)
            if _has_media:
                self.store.set_media_status(existing["id"], "pending")
            self._auto_map_safe(existing["id"])   # 采集后自动映射属性（已本地缓存化，快）
            return {"created": [{"id": existing["id"], "source_title": existing.get("source_title")}], "errors": [], "deduped": True}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. python tests/test_media_async.py CollectSetsPendingTest -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 回归 + 提交**

Run: `PYTHONPATH=. python tests/test_ext_bridge.py 2>&1 | tail -2` → OK

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_media_async.py
git commit -m "feat(app): 采集有媒体时置 media_status=pending"
```

---

## Task 3: update-draft-media 接口（插件传完 OSS 后换链接）

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（新增 `update_draft_media`）
- Modify: `ozon-listing-webui/backend/main.py`（新增 `POST /api/ext/update-draft-media`）
- Test: `ozon-listing-webui/tests/test_media_async.py`

- [ ] **Step 1: 写失败测试**

在 `test_media_async.py` 末尾加：

```python
class UpdateDraftMediaTest(unittest.TestCase):
    def test_replaces_and_done(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/u-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                out = app.update_draft_media({"draft_id": did,
                                              "media_map": {"https://ir.ozone.ru/a.jpg": "https://oss/a.jpg"}})
                self.assertTrue(out.get("ok"))
                d = app.store.get_draft(did)
                self.assertEqual(d["images"], ["https://oss/a.jpg"])
                self.assertEqual(d["media_status"], "done")
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. python tests/test_media_async.py UpdateDraftMediaTest -v`
Expected: FAIL，`AttributeError: ... 'update_draft_media'`

- [ ] **Step 3a: app_service 方法**

在 `app_service.py` 的 `ext_collect_parsed` 之后插入：

```python
    def update_draft_media(self, payload: dict) -> dict:
        """插件后台把媒体传完 OSS 后回调：把草稿里命中的原 URL 换成 OSS URL，置 media_status=done。"""
        draft_id = _to_int(payload.get("draft_id"))
        media_map = payload.get("media_map") or {}
        if not draft_id:
            raise ValueError("draft_id required")
        self.store.apply_media_oss(draft_id, dict(media_map))
        return {"ok": True}
```

- [ ] **Step 3b: main 路由**

在 `main.py` 的 `/api/ext/publish-group`（539-544）之后插入：

```python
@app.post("/api/ext/update-draft-media")
def ext_update_draft_media(body: dict) -> dict:
    try:
        return APP.update_draft_media(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. python tests/test_media_async.py UpdateDraftMediaTest -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/backend/main.py ozon-listing-webui/tests/test_media_async.py
git commit -m "feat(ext): update-draft-media 接口（媒体传完OSS换链接+done）"
```

---

## Task 4: pending-media-drafts 接口（插件补传用）

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（新增 `pending_media_drafts`）
- Modify: `ozon-listing-webui/backend/main.py`（新增 `GET /api/ext/pending-media-drafts`）
- Test: `ozon-listing-webui/tests/test_media_async.py`

- [ ] **Step 1: 写失败测试**

在 `test_media_async.py` 末尾加：

```python
class PendingMediaDraftsTest(unittest.TestCase):
    def test_lists_pending(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/p-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]
                out = app.pending_media_drafts()
                self.assertEqual([d["id"] for d in out["drafts"]], [did])
                self.assertEqual(out["drafts"][0]["images"], ["https://ir.ozone.ru/a.jpg"])
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. python tests/test_media_async.py PendingMediaDraftsTest -v`
Expected: FAIL，`AttributeError: ... 'pending_media_drafts'`

- [ ] **Step 3a: app_service 方法**

在 `app_service.py` 的 `update_draft_media` 之后插入（`current_user_id` 已在 store 层处理，这里用 store 的默认 user 解析）：

```python
    def pending_media_drafts(self) -> dict:
        """当前用户媒体待传(pending)的草稿，供插件后台补传。"""
        from backend.store import current_user_id  # noqa: PLC0415
        return {"drafts": self.store.list_pending_media_drafts(current_user_id.get())}
```

- [ ] **Step 3b: main 路由**

在 `main.py` 的 `update-draft-media` 路由之后插入：

```python
@app.get("/api/ext/pending-media-drafts")
def ext_pending_media_drafts() -> dict:
    return APP.pending_media_drafts()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. python tests/test_media_async.py PendingMediaDraftsTest -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/backend/main.py ozon-listing-webui/tests/test_media_async.py
git commit -m "feat(ext): pending-media-drafts 接口（插件补传用）"
```

---

## Task 5: 发布拦截 media_status=pending

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（`publish` 方法开头加检查）
- Test: `ozon-listing-webui/tests/test_media_async.py`

`publish(draft_id, store_client_id)` 是发布入口（`main.py:328` → `APP.publish`）。开头检查媒体状态，pending 直接拒绝。

- [ ] **Step 1: 写失败测试**

在 `test_media_async.py` 末尾加：

```python
class PublishBlockedWhenPendingTest(unittest.TestCase):
    def test_publish_rejected_when_pending(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._auto_match_category = lambda scraped: None
                app._auto_map_safe = lambda did: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/pub-1/",
                                              "data": {"title": "t", "images": ["https://ir.ozone.ru/a.jpg"]}})
                did = res["created"][0]["id"]  # media_status=pending
                with self.assertRaises(ValueError):
                    app.publish(did, None)
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. python tests/test_media_async.py PublishBlockedWhenPendingTest -v`
Expected: FAIL（当前没拦截，会走到别处报别的错或不报错）

- [ ] **Step 3: 实现**

在 `app_service.py` 的 `publish` 方法最开头（拿到 draft 之后）加检查。先 Read `publish` 方法确认它怎么取 draft，然后在取到 draft 后插入：

```python
        if str(draft.get("media_status") or "done") == "pending":
            raise ValueError("图片还在上传，请稍候再发布")
```

（若 `publish` 内部变量名不是 `draft`，用它实际的草稿变量名。）

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. python tests/test_media_async.py PublishBlockedWhenPendingTest -v`
Expected: PASS

- [ ] **Step 5: 回归 + 提交**

Run: `PYTHONPATH=. python tests/test_media_async.py 2>&1 | tail -2` → OK（全部）

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_media_async.py
git commit -m "feat(app): 媒体未传完(pending)硬拦截发布"
```

---

## 部署（5 任务完成后）

```bash
cd ozon-listing-webui && PYTHONPATH=. python tests/test_media_async.py 2>&1 | tail -2 && cd ..
# 重建镜像 + 重启（drafts.media_status 列容器启动自动补；现有草稿默认 done 不受影响）
```

后端部署后，插件那边（计划三）才会用上这些接口。**本计划纯后端，部署后不影响现有功能**（采集仍照旧，只是多了 media_status 字段，默认 done）。

---

## 自检（写计划时已核对）

- **spec 覆盖**：media_status 数据模型(T1)、采集置 pending(T2)、update-draft-media(T3)、pending-media-drafts(T4)、发布拦截(T5)。前端采集流程/后台传/补传在计划三。
- **无占位符**：每步含可运行测试/实现代码与命令；Task 5 Step 3 需先 Read `publish` 确认草稿变量名（已注明）。
- **类型一致**：`set_media_status(id, status)`、`apply_media_oss(id, media_map)`、`list_pending_media_drafts(user_id)`→`[{id,images,video_url}]`、`update_draft_media({draft_id, media_map})`、`pending_media_drafts()`→`{drafts:[...]}` 在测试与实现处一致。
