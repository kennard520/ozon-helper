# Admin 用户管理 + 店铺配额 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭开放注册，改为仅 admin 在网页管理用户（列出/创建/改最大店铺数/重置密码/禁用启用），并对每用户的 Ozon 店铺数做后端强制配额。

**Architecture:** 后端在 `users` 表加 `max_stores` 列；新增 `require_admin` 依赖 + `/api/admin/users` 系列接口；删除公开注册；保存设置时按 `max_stores` 校验店铺数。前端在 Settings 页加 admin-only 的用户管理卡片，去掉登录页注册入口。权限全在后端强制，前端隐藏只是 UX。

**Tech Stack:** FastAPI + pydantic + 自研 PyMySQL 适配层/SQLite；Vue 3 + Element Plus + Pinia；pytest/unittest + vitest。

**测试约定：** 后端逻辑用 SQLite 临时库测（沿用 `tests/` 的 unittest + `TestClient` 模式，见 `tests/test_api_multiuser.py` 的 `_client(tmp)`）。MySQL 专属 DDL（加列）无法本地跑，放到 Task 8 部署时验证。每个任务跑：`cd ozon-listing-webui && python -m pytest tests/<file> -v`（若无 pytest 用 `python -m unittest`）。

---

### Task 1: `users` 表加 `max_stores` 列 + `create_user` 支持配额

**Files:**
- Modify: `ozon-listing-webui/backend/store.py`（`init()` users 段、`create_user`）
- Modify: `ozon-listing-webui/backend/db.py`（MySQL users DDL + 新增 ensure-column）
- Test: `ozon-listing-webui/tests/test_admin_users.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `ozon-listing-webui/tests/test_admin_users.py`：

```python
import importlib
import tempfile
import unittest
from pathlib import Path


def fresh_store(tmp):
    import backend.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "t.db"
    importlib.reload(store_mod)
    return store_mod.Store()


class StoreUserTest(unittest.TestCase):
    def test_create_user_with_max_stores(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = fresh_store(tmp)
            try:
                u = s.create_user("alice", "h", role="user", max_stores=3)
                self.assertEqual(u["max_stores"], 3)
                got = s.get_user_by_id(u["id"])
                self.assertEqual(got["max_stores"], 3)
            finally:
                s.close()

    def test_create_user_default_max_stores_is_1(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = fresh_store(tmp)
            try:
                u = s.create_user("bob", "h")
                self.assertEqual(u["max_stores"], 1)
            finally:
                s.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py -v`
Expected: FAIL（`create_user()` 不接受 `max_stores` / 返回无该字段）

- [ ] **Step 3: 改 SQLite 建表与迁移（store.py）**

在 `store.py` 的 `init()` 里，users 建表块（`CREATE TABLE IF NOT EXISTS users (...)`）之后、`accounts` 建表之前，加一行确保旧库补列：

```python
            self._ensure_column("users", "max_stores", "INTEGER NOT NULL DEFAULT 1")
```

（`_ensure_column` 已存在，走 `PRAGMA table_info`，仅 SQLite 分支。MySQL 分支在 `init()` 开头已 `return`，不会执行到这里。）

- [ ] **Step 4: 改 `create_user`（store.py）**

把 `create_user` 改成接受 `max_stores`：

```python
    def create_user(self, username: str, password_hash: str, role: str = "user",
                    max_stores: int = 1) -> dict[str, Any]:
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO users(username, password_hash, role, status, created_at, max_stores) "
                "VALUES(?, ?, ?, 'active', ?, ?)",
                (username, password_hash, role, utc_now_iso(), int(max_stores)),
            )
            self.conn.commit()
            uid = cur.lastrowid
        return self.get_user_by_id(uid)
```

- [ ] **Step 5: 改 MySQL DDL 与加列探测（db.py）**

在 `db.py` 的 `MYSQL_DDL` 里 users 表定义中加列（`status` 之后）：

```sql
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        max_stores INT NOT NULL DEFAULT 1,
        created_at VARCHAR(40) NOT NULL
```

并在 `init_mysql()` 里、`for ddl in MYSQL_DDL: ...` 之后加"确保列存在"（MySQL `CREATE TABLE IF NOT EXISTS` 不会给已有表加列）：

```python
def _ensure_mysql_column(conn, table, column, ddl):
    cur = conn.execute(
        "SELECT COUNT(*) c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=? AND COLUMN_NAME=?",
        (table, column),
    )
    if cur.fetchone()["c"] == 0:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_mysql(conn: MySQLConn) -> None:
    for ddl in MYSQL_DDL:
        conn.execute(ddl)
    _ensure_mysql_column(conn, "users", "max_stores", "INT NOT NULL DEFAULT 1")
    conn.commit()
```

（`?` 占位符会被适配层翻成 `%s`；`information_schema` 查询里的字符串 `users`/`max_stores` 作为参数传入，安全。）

- [ ] **Step 6: 跑测试确认通过**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-webui/backend/store.py ozon-listing-webui/backend/db.py ozon-listing-webui/tests/test_admin_users.py
git commit -m "feat(users): max_stores 列 + create_user 配额参数（SQLite/MySQL）"
```

---

### Task 2: store 层用户管理方法

**Files:**
- Modify: `ozon-listing-webui/backend/store.py`
- Test: `ozon-listing-webui/tests/test_admin_users.py`

- [ ] **Step 1: 加失败测试**

在 `test_admin_users.py` 的 `StoreUserTest` 里加：

```python
    def test_list_and_mutate_users(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = fresh_store(tmp)
            try:
                a = s.create_user("alice", "h1", max_stores=2)
                s.create_user("bob", "h2", max_stores=5)
                rows = s.list_users()
                names = {r["username"] for r in rows}
                self.assertEqual(names, {"alice", "bob"})
                self.assertTrue(all("password_hash" not in r for r in rows))  # 不外泄哈希

                s.set_max_stores(a["id"], 9)
                self.assertEqual(s.get_user_by_id(a["id"])["max_stores"], 9)

                s.set_status(a["id"], "disabled")
                self.assertEqual(s.get_user_by_id(a["id"])["status"], "disabled")

                s.set_password_hash(a["id"], "newhash")
                self.assertEqual(s.get_user_by_id(a["id"])["password_hash"], "newhash")
            finally:
                s.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py::StoreUserTest::test_list_and_mutate_users -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现方法（store.py）**

在 `store.py` 的 `count_users` 之后加：

```python
    def list_users(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, username, role, status, max_stores, created_at "
                "FROM users ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def set_max_stores(self, user_id: int, max_stores: int) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE users SET max_stores=? WHERE id=?", (int(max_stores), int(user_id))
            )
            self.conn.commit()

    def set_status(self, user_id: int, status: str) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE users SET status=? WHERE id=?", (str(status), int(user_id))
            )
            self.conn.commit()

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?", (str(password_hash), int(user_id))
            )
            self.conn.commit()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/store.py ozon-listing-webui/tests/test_admin_users.py
git commit -m "feat(users): store 层 list_users/set_max_stores/set_status/set_password_hash"
```

---

### Task 3: 关闭公开注册 + 登录禁用校验 + models + 修旧测试

**Files:**
- Modify: `ozon-listing-webui/backend/main.py`（删 register 路由）
- Modify: `ozon-listing-webui/backend/app_service.py`（删 `register`、`login` 加 status 校验）
- Modify: `ozon-listing-webui/backend/models.py`（加 admin 入参模型）
- Modify: 现有用 `register` 的测试（见 Step 5）
- Test: `ozon-listing-webui/tests/test_admin_users.py`

- [ ] **Step 1: 加失败测试（登录禁用 + 注册关闭）**

在 `test_admin_users.py` 加一个 API 测试类：

```python
class AdminApiTest(unittest.TestCase):
    def _client(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "api.db"
        import backend.app_service as svc
        importlib.reload(svc)
        import backend.main as main_mod
        importlib.reload(main_mod)
        from fastapi.testclient import TestClient
        self._main = main_mod
        return TestClient(main_mod.app)

    def _admin_token(self, client):
        # 首启自动建 admin/admin
        return client.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()["token"]

    def test_public_register_removed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                r = client.post("/api/auth/register", json={"username": "x", "password": "secret1"})
                self.assertEqual(r.status_code, 404)
            finally:
                self._main.APP.store.close()

    def test_disabled_user_cannot_login(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                u = self._main.APP.store.create_user("carol", __import__("backend.auth", fromlist=["hash_password"]).hash_password("secret1"))
                self._main.APP.store.set_status(u["id"], "disabled")
                r = client.post("/api/auth/login", json={"username": "carol", "password": "secret1"})
                self.assertEqual(r.status_code, 400)
            finally:
                self._main.APP.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py::AdminApiTest -v`
Expected: FAIL（register 仍返回 200；禁用用户仍能登录）

- [ ] **Step 3: 删注册路由（main.py）**

删除 `main.py` 中这段：

```python
@app.post("/api/auth/register")
def auth_register(body: AuthIn) -> dict:
    try:
        return APP.register(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 4: 删 `register` 方法 + `login` 加禁用校验（app_service.py）**

删除 `App.register` 方法（约 98-109 行）。在 `login` 里，`verify_password` 校验之后加禁用判断：

```python
    def login(self, username: str, password: str) -> dict:
        from backend.auth import verify_password, make_token  # noqa: PLC0415
        user = self.store.get_user_by_username(username)
        if not user or not verify_password(password or "", user["password_hash"]):
            raise ValueError("用户名或密码错误")
        if (user.get("status") or "active") != "active":
            raise ValueError("账号已被禁用，请联系管理员")
        token = make_token(user["id"], self.auth_secret())
        return {"token": token, "user": self._public_user(user)}
```

（保持原 `login` 其它逻辑不变；上面是完整替换后的方法体。）

- [ ] **Step 5: 加 models（models.py）**

在 `models.py` 末尾加：

```python
class AdminCreateUserIn(BaseModel):
    username: str
    password: str
    max_stores: int = 1


class AdminUpdateUserIn(BaseModel):
    max_stores: int | None = None
    status: str | None = None   # active / disabled
    password: str | None = None
```

- [ ] **Step 6: 修复引用 `register` 的旧测试**

找出旧测试里用 `/api/auth/register` 的地方并改成直接建用户：

Run: `cd ozon-listing-webui && grep -rln "auth/register\|\.register(" tests`

对每个命中（如 `tests/test_api_multiuser.py`、`tests/test_auth.py`、`tests/test_api.py`），把
`client.post("/api/auth/register", json={"username": U, "password": P}).json()`
替换为先建用户再登录的辅助：

```python
def _make(client, main_mod, username, password):
    from backend.auth import hash_password
    u = main_mod.APP.store.create_user(username, hash_password(password))
    tok = client.post("/api/auth/login", json={"username": username, "password": password}).json()["token"]
    return {"user": u, "token": tok}
```

（在各测试文件内联此辅助或就地替换；保证原断言含义不变——拿到 `user.id` 与 `token`。）

- [ ] **Step 7: 跑全部后端测试确认通过**

Run: `cd ozon-listing-webui && python -m pytest tests -v`
Expected: PASS（含新 AdminApiTest 与改过的旧测试）

- [ ] **Step 8: 提交**

```bash
git add ozon-listing-webui/backend/main.py ozon-listing-webui/backend/app_service.py ozon-listing-webui/backend/models.py ozon-listing-webui/tests
git commit -m "feat(auth): 关闭公开注册 + 登录校验禁用状态；修旧测试"
```

---

### Task 4: `require_admin` + admin 用户管理接口

**Files:**
- Modify: `ozon-listing-webui/backend/main.py`（依赖 + 3 个路由）
- Modify: `ozon-listing-webui/backend/app_service.py`（3 个方法 + 防自锁）
- Test: `ozon-listing-webui/tests/test_admin_users.py`

- [ ] **Step 1: 加失败测试**

在 `AdminApiTest` 里加：

```python
    def test_admin_endpoints_require_admin(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                # 无 token → 401/403
                self.assertIn(client.get("/api/admin/users").status_code, (401, 403))
                # 普通用户 token → 403
                from backend.auth import hash_password
                u = self._main.APP.store.create_user("dave", hash_password("secret1"))
                t = client.post("/api/auth/login", json={"username": "dave", "password": "secret1"}).json()["token"]
                r = client.get("/api/admin/users", headers={"Authorization": "Bearer " + t})
                self.assertEqual(r.status_code, 403)
            finally:
                self._main.APP.store.close()

    def test_admin_crud_user(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                at = self._admin_token(client)
                H = {"Authorization": "Bearer " + at}
                # 创建
                r = client.post("/api/admin/users", headers=H,
                                json={"username": "erin", "password": "secret1", "max_stores": 4})
                self.assertEqual(r.status_code, 200)
                uid = r.json()["id"]
                self.assertEqual(r.json()["max_stores"], 4)
                # 列出含 store_count
                rows = client.get("/api/admin/users", headers=H).json()["users"]
                erin = [x for x in rows if x["id"] == uid][0]
                self.assertEqual(erin["max_stores"], 4)
                self.assertIn("store_count", erin)
                # 改上限
                client.patch(f"/api/admin/users/{uid}", headers=H, json={"max_stores": 7})
                rows = client.get("/api/admin/users", headers=H).json()["users"]
                self.assertEqual([x for x in rows if x["id"] == uid][0]["max_stores"], 7)
                # 重置密码 → 新密码可登录
                client.patch(f"/api/admin/users/{uid}", headers=H, json={"password": "newpass1"})
                self.assertEqual(client.post("/api/auth/login",
                                 json={"username": "erin", "password": "newpass1"}).status_code, 200)
                # 禁用 → 登录失败
                client.patch(f"/api/admin/users/{uid}", headers=H, json={"status": "disabled"})
                self.assertEqual(client.post("/api/auth/login",
                                 json={"username": "erin", "password": "newpass1"}).status_code, 400)

    def test_admin_cannot_disable_self(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                at = self._admin_token(client)
                H = {"Authorization": "Bearer " + at}
                me = client.get("/api/auth/me", headers=H).json()
                r = client.patch(f"/api/admin/users/{me['id']}", headers=H, json={"status": "disabled"})
                self.assertEqual(r.status_code, 400)
            finally:
                self._main.APP.store.close()
```

（注意：`test_admin_crud_user` 的 finally 关库——补 `finally: self._main.APP.store.close()`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py::AdminApiTest -v`
Expected: FAIL（路由不存在）

- [ ] **Step 3: app_service 方法 + 防自锁**

在 `app_service.py` 加（放在 `login`/`me` 附近）：

```python
    def admin_list_users(self) -> dict:
        out = []
        for u in self.store.list_users():
            cnt = len(self.store.get_settings(u["id"]).get("ozon_stores") or [])
            out.append({**u, "store_count": cnt})
        return {"users": out}

    def admin_create_user(self, username: str, password: str, max_stores: int = 1) -> dict:
        username = (username or "").strip()
        if len(username) < 3:
            raise ValueError("用户名至少 3 个字符")
        if len(password or "") < 6:
            raise ValueError("密码至少 6 位")
        if self.store.get_user_by_username(username):
            raise ValueError("用户名已存在")
        from backend.auth import hash_password  # noqa: PLC0415
        u = self.store.create_user(username, hash_password(password),
                                   role="user", max_stores=max(1, int(max_stores)))
        return {**self._public_user(u), "max_stores": u["max_stores"], "store_count": 0}

    def admin_update_user(self, actor: dict, user_id: int,
                          max_stores: int | None = None,
                          status: str | None = None,
                          password: str | None = None) -> dict:
        target = self.store.get_user_by_id(int(user_id))
        if not target:
            raise ValueError("用户不存在")
        if status is not None:
            status = str(status).strip()
            if status not in ("active", "disabled"):
                raise ValueError("status 只能是 active/disabled")
            if status == "disabled":
                if int(actor["id"]) == int(user_id):
                    raise ValueError("不能禁用自己")
                if (target.get("role") == "admin"):
                    active_admins = [u for u in self.store.list_users()
                                     if u.get("role") == "admin" and (u.get("status") or "active") == "active"]
                    if len(active_admins) <= 1:
                        raise ValueError("不能禁用最后一个管理员")
            self.store.set_status(user_id, status)
        if max_stores is not None:
            self.store.set_max_stores(user_id, max(1, int(max_stores)))
        if password is not None:
            if len(password) < 6:
                raise ValueError("密码至少 6 位")
            from backend.auth import hash_password  # noqa: PLC0415
            self.store.set_password_hash(user_id, hash_password(password))
        u = self.store.get_user_by_id(int(user_id))
        cnt = len(self.store.get_settings(u["id"]).get("ozon_stores") or [])
        return {**self._public_user(u), "max_stores": u["max_stores"],
                "status": u["status"], "store_count": cnt}
```

- [ ] **Step 4: main.py 依赖 + 路由**

在 `main.py` 的 `get_current_user` 定义之后加：

```python
def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
```

在 `/api/auth/me` 路由附近加（确保 import 了 `AdminCreateUserIn, AdminUpdateUserIn`，在文件顶部 models 导入块补上这两个名字）：

```python
@app.get("/api/admin/users")
def admin_users_list(user: dict = Depends(require_admin)) -> dict:
    return APP.admin_list_users()


@app.post("/api/admin/users")
def admin_users_create(body: AdminCreateUserIn, user: dict = Depends(require_admin)) -> dict:
    try:
        return APP.admin_create_user(body.username, body.password, body.max_stores)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.patch("/api/admin/users/{user_id}")
def admin_users_update(user_id: int, body: AdminUpdateUserIn,
                       user: dict = Depends(require_admin)) -> dict:
    try:
        return APP.admin_update_user(user, user_id, body.max_stores, body.status, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-webui/backend/main.py ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_admin_users.py
git commit -m "feat(admin): require_admin + /api/admin/users 列出/创建/更新（含防自锁）"
```

---

### Task 5: 店铺配额后端强制

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（保存设置处理 ozon_stores 段）
- Test: `ozon-listing-webui/tests/test_admin_users.py`

- [ ] **Step 1: 加失败测试**

在 `AdminApiTest` 加：

```python
    def test_store_quota_enforced(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                at = self._admin_token(client)
                H = {"Authorization": "Bearer " + at}
                # 建 max_stores=1 的普通用户并登录
                client.post("/api/admin/users", headers=H,
                            json={"username": "frank", "password": "secret1", "max_stores": 1})
                ft = client.post("/api/auth/login", json={"username": "frank", "password": "secret1"}).json()["token"]
                FH = {"Authorization": "Bearer " + ft}
                two = [{"name": "s1", "client_id": "111", "api_key": "k1", "is_default": True},
                       {"name": "s2", "client_id": "222", "api_key": "k2"}]
                r = client.post("/api/settings", headers=FH, json={"ozon_stores": two})
                self.assertEqual(r.status_code, 400)
                # admin 不受限
                r2 = client.post("/api/settings", headers=H, json={"ozon_stores": two})
                self.assertEqual(r2.status_code, 200)
            finally:
                self._main.APP.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py::AdminApiTest::test_store_quota_enforced -v`
Expected: FAIL（普通用户存 2 店返回 200）

- [ ] **Step 3: 加配额校验（app_service.py）**

在保存设置处理 `ozon_stores` 的块里（`stores = normalize_stores({"ozon_stores": incoming})` 之后、`allowed["ozon_stores"] = stores` 之前）插入：

```python
            stores = normalize_stores({"ozon_stores": incoming})
            from backend.store import current_user_id  # noqa: PLC0415
            actor = self.store.get_user_by_id(current_user_id.get())
            if actor and actor.get("role") != "admin":
                limit = int(actor.get("max_stores") or 1)
                if len(stores) > limit:
                    raise ValueError(f"最多 {limit} 个店铺，请联系管理员调整上限")
            allowed["ozon_stores"] = stores
```

确认 `/api/settings` 路由把 `ValueError` 转成 400（与现有 settings 路由一致）。若该路由当前未捕获 `ValueError`，加：

Run: `grep -n "api/settings" ozon-listing-webui/backend/main.py` 找到路由，确保是：

```python
@app.post("/api/settings")
def save_settings(body: SettingsIn, user: dict = Depends(get_current_user)) -> dict:
    try:
        return APP.update_settings(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

（方法名 `update_settings` 以实际为准；只需保证 `ValueError → 400`。其余逻辑不动。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd ozon-listing-webui && python -m pytest tests/test_admin_users.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/backend/main.py ozon-listing-webui/tests/test_admin_users.py
git commit -m "feat(quota): 保存设置时按 max_stores 后端强制店铺数（admin 豁免）"
```

---

### Task 6: 前端 api.js + 去掉登录页注册入口

**Files:**
- Modify: `ozon-listing-webui/frontend/src/api.js`
- Modify: `ozon-listing-webui/frontend/src/views/Login.vue`

- [ ] **Step 1: 改 api.js**

把 `register: (...)` 那行删掉，换成 admin 接口：

```javascript
  // 鉴权 + 钱包
  login: (username, password) => req('POST', '/api/auth/login', { username, password }),
  me: () => req('GET', '/api/auth/me'),
  adminListUsers: () => req('GET', '/api/admin/users'),
  adminCreateUser: (username, password, max_stores) => req('POST', '/api/admin/users', { username, password, max_stores }),
  adminUpdateUser: (id, patch) => req('PATCH', `/api/admin/users/${id}`, patch),
  wallet: () => req('GET', '/api/wallet'),
```

- [ ] **Step 2: 去掉 Login.vue 的注册模式**

`Login.vue` 改成只登录：把 `const mode = ref('login')` 相关注册分支去掉——`submit` 固定用 `api.login`；删掉底部"去注册/去登录"的 `el-link`（line 48-49 那段）；按钮文案固定"登录"。具体：
- `const fn = mode.value === 'login' ? api.login : api.register` → `const fn = api.login`
- 成功提示固定 `ElMessage.success('登录成功')`
- 模板里删掉切换注册的 `<el-link>` 块，按钮文案写死"登录"。

- [ ] **Step 3: 构建确认无引用错误**

Run: `cd ozon-listing-webui/frontend && npm run build`
Expected: 构建成功，无 "api.register is not a function" / 未用变量报错（如 `mode` 删干净）。

- [ ] **Step 4: 提交**

```bash
git add ozon-listing-webui/frontend/src/api.js ozon-listing-webui/frontend/src/views/Login.vue
git commit -m "feat(web): api 加 admin 用户接口；登录页去掉注册入口"
```

---

### Task 7: 前端 Settings.vue 用户管理卡片（仅 admin）

**Files:**
- Modify: `ozon-listing-webui/frontend/src/views/Settings.vue`

- [ ] **Step 1: script 里加用户管理逻辑**

在 `Settings.vue` 的 `<script setup>` 顶部 import 区加：

```javascript
import { getUser } from '../auth.js'
```

在 script 内（任意函数定义区）加：

```javascript
const isAdmin = computed(() => (getUser() || {}).role === 'admin')
const users = ref([])
const newUser = reactive({ username: '', password: '', max_stores: 1 })

async function loadUsers() {
  if (!isAdmin.value) return
  try { users.value = (await api.adminListUsers()).users } catch (e) { /* 非 admin 被 403，忽略 */ }
}
onMounted(loadUsers)

async function createUser() {
  if (!newUser.username || !newUser.password) { ElMessage.warning('填用户名和密码'); return }
  try {
    await api.adminCreateUser(newUser.username.trim(), newUser.password, Number(newUser.max_stores) || 1)
    ElMessage.success('已创建用户')
    newUser.username = ''; newUser.password = ''; newUser.max_stores = 1
    await loadUsers()
  } catch (e) { ElMessage.error(e.message || '创建失败') }
}

async function updateMaxStores(u) {
  try { await api.adminUpdateUser(u.id, { max_stores: Number(u.max_stores) || 1 }); ElMessage.success('已更新上限') }
  catch (e) { ElMessage.error(e.message || '更新失败') }
}

async function resetPassword(u) {
  const pw = window.prompt(`给 ${u.username} 设新密码（≥6 位）`)
  if (!pw) return
  try { await api.adminUpdateUser(u.id, { password: pw }); ElMessage.success('密码已重置') }
  catch (e) { ElMessage.error(e.message || '重置失败') }
}

async function toggleStatus(u) {
  const next = u.status === 'active' ? 'disabled' : 'active'
  try { await api.adminUpdateUser(u.id, { status: next }); ElMessage.success(next === 'active' ? '已启用' : '已禁用'); await loadUsers() }
  catch (e) { ElMessage.error(e.message || '操作失败') }
}
```

- [ ] **Step 2: template 里加卡片（仅 admin）**

在 `Settings.vue` 模板的设置项末尾（最后一个 `el-card`/区块之后、根容器闭合之前）插入：

```html
    <el-card v-if="isAdmin" style="margin-top:16px">
      <template #header>用户管理（仅管理员）</template>
      <el-form :inline="true" style="margin-bottom:12px">
        <el-form-item label="用户名"><el-input v-model="newUser.username" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="newUser.password" type="password" /></el-form-item>
        <el-form-item label="最大店铺数"><el-input-number v-model="newUser.max_stores" :min="1" /></el-form-item>
        <el-form-item><el-button type="primary" @click="createUser">创建用户</el-button></el-form-item>
      </el-form>
      <el-table :data="users" size="small" border>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="role" label="角色" width="90" />
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="当前店数" width="90">
          <template #default="{ row }">{{ row.store_count }}</template>
        </el-table-column>
        <el-table-column label="最大店铺数" width="160">
          <template #default="{ row }">
            <el-input-number v-model="row.max_stores" :min="1" size="small" @change="() => updateMaxStores(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" @click="resetPassword(row)">重置密码</el-button>
            <el-button size="small" :type="row.status === 'active' ? 'danger' : 'success'" @click="toggleStatus(row)">
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
```

- [ ] **Step 3: 构建确认**

Run: `cd ozon-listing-webui/frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 4: 提交**

```bash
git add ozon-listing-webui/frontend/src/views/Settings.vue
git commit -m "feat(web): 设置页加 admin 用户管理卡片（建用户/改上限/重置密码/禁用启用）"
```

---

### Task 8: 部署到服务器并验证

**Files:** 无（运维）

- [ ] **Step 1: 本地构建前端 dist**

Run: `cd ozon-listing-webui/frontend && npm run build`
Expected: `dist/` 更新。

- [ ] **Step 2: 打包上传代码（沿用既有 SSH 工具，SFTP 坏→cat-pipe）**

```bash
cd /e/personal/ozon-helper
tar -czf /c/Users/42918/.ozon-deploy/app.tgz \
  --exclude='ozon-listing-webui/frontend/node_modules' --exclude='ozon-listing-webui/.venv' \
  --exclude='**/__pycache__' --exclude='*.pyc' --exclude='ozon-listing-webui/data' \
  ozon-listing-webui ozon_api
sh /c/Users/42918/.ozon-deploy/put.sh /c/Users/42918/.ozon-deploy/app.tgz /root/app.tgz
```

- [ ] **Step 3: 解压 + 重建镜像 + 重启容器**

```bash
python "C:/Users/42918/.ozon-deploy/_ssh.py" "
set -e
tar -xzf /root/app.tgz -C /opt/ozon-helper
docker build -t ozon-webui:latest -f /opt/ozon-helper/Dockerfile /opt/ozon-helper 2>&1 | tail -5
docker rm -f ozon-webui >/dev/null 2>&1 || true
docker run -d --name ozon-webui --restart always --network ozonnet -p 8585:8585 \
  -e OZON_MYSQL_HOST=mysql -e OZON_MYSQL_PORT=3306 -e OZON_MYSQL_USER=ozon -e OZON_MYSQL_PASSWORD=Ozon_8585_dbpw -e OZON_MYSQL_DB=ozon \
  -e OZON_OSS_INTERNAL_ENDPOINT=oss-cn-beijing-internal.aliyuncs.com \
  -v /opt/ozon-helper/appdata:/app/ozon-listing-webui/data \
  ozon-webui:latest >/dev/null
sleep 5; curl -s -m 8 http://127.0.0.1:8585/api/ext/ping; echo
"
```

- [ ] **Step 4: 验证 MySQL 加列 + admin 接口**

```bash
python "C:/Users/42918/.ozon-deploy/_ssh.py" "
echo '--- users 表有 max_stores 列吗 ---'
docker exec ozon-webui python -c \"from backend.store import Store; print([r['username'] for r in Store().list_users()]); print('max_stores ok')\"
echo '--- 无 token 调 admin 接口应 401/403 ---'
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8585/api/admin/users
echo '--- admin 登录并列用户 ---'
T=\$(curl -s http://127.0.0.1:8585/api/auth/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"admin\"}' | python -c 'import sys,json;print(json.load(sys.stdin)[\"token\"])')
curl -s http://127.0.0.1:8585/api/admin/users -H \"Authorization: Bearer \$T\" | head -c 300; echo
"
```
Expected: 列出用户成功；无 token 返回 401/403。

- [ ] **Step 5: 推送代码**

```bash
cd /e/personal/ozon-helper
GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new" git push origin main
```

---

## 备注

- admin 默认账号/密码仍是 `admin/admin`，上线前应改（见会话中"修改密码"方法或建好新 admin 后禁用默认 admin——但注意"不能禁用最后一个 admin"）。
- 本计划不动店铺隔离、不删用户、不加邀请码（见 spec 非目标）。
