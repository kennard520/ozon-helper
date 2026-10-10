# 类目属性字典值本地缓存 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把"采集后自动映射属性"从逐个跨境调 Ozon（实测 21.7s）改成本地缓存匹配为主、极少数才实时搜，并把映射放回采集流程。

**Architecture:** 新增"按 (类目,类型,属性) 缓存该属性全部字典值"的表；采集时对每个字典属性，本地精确匹配拿 value_id，没命中（或字典超大）才并发实时搜兜底；品牌跳过、填无品牌（现状不变）。

**Tech Stack:** Python 3 / FastAPI 后端、SQLite(本地)+MySQL(线上薄适配层)、`unittest`、`concurrent.futures.ThreadPoolExecutor`。

**测试怎么跑：** 所有命令在 `ozon-listing-webui/` 目录下执行：`python -m pytest tests/<file>::<Class>::<test> -v`。

---

## 文件结构

| 文件 | 职责 | 改动 |
|---|---|---|
| `ozon_api/client.py` | Ozon HTTP 客户端 | 加 `get_attribute_values`（分页拉某属性全部字典值 + 阈值保护） |
| `ozon-listing-webui/backend/ozon_client_adapter.py` | settings→client 的薄封装 | 加 `get_attribute_values` wrapper |
| `ozon-listing-webui/backend/db.py` | MySQL 建表 DDL 列表 | `MYSQL_DDL` 加 `category_attr_values_cache` |
| `ozon-listing-webui/backend/store.py` | 数据访问层 | SQLite 建表加新表 + `save_attr_values` / `load_attr_values` |
| `ozon-listing-webui/backend/app_service.py` | 业务逻辑 | 加 `_ensure_attr_values` / `_local_match_value` / `_search_one_value` / `_resolve_pairs_concurrent`；改 `_resolve_values` / `auto_map_attributes`；恢复 `ext_collect_parsed` 两处 `_auto_map_safe` |
| `ozon-listing-webui/tests/test_attr_values_cache.py` | 新测试 | 覆盖上述全部 |

---

## Task 1: Ozon client 拉某属性全部字典值

**Files:**
- Modify: `ozon_api/client.py`（在 `search_attribute_values` 方法后插入）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

- [ ] **Step 1: 写失败测试**

新建 `ozon-listing-webui/tests/test_attr_values_cache.py`：

```python
from __future__ import annotations
import sys, unittest
from pathlib import Path

# 让 `import ozon_api` 可用（ozon_api 在仓库根 = tests 的 parents[2]）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ozon_api.client import OzonSellerClient, SimpleResponse  # noqa: E402


class _FakeTransport:
    """记录每次请求并按顺序返回预设 JSON。"""
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls: list[dict] = []

    def request(self, *, method, url, headers, json, timeout):
        import json as _j
        self.calls.append({"url": url, "json": json})
        body = self.pages[len(self.calls) - 1]
        return SimpleResponse(status_code=200, text=_j.dumps(body))


class GetAttributeValuesTest(unittest.TestCase):
    def test_paginates_until_no_next(self):
        transport = _FakeTransport([
            {"result": [{"id": 1, "value": "красный"}, {"id": 2, "value": "синий"}], "has_next": True},
            {"result": [{"id": 3, "value": "зелёный"}], "has_next": False},
        ])
        c = OzonSellerClient("1", "k", transport=transport)
        out = c.get_attribute_values(100, 22, 99, language="RU", page_size=2, max_total=2000)
        self.assertFalse(out["oversized"])
        self.assertEqual([v["value"] for v in out["values"]], ["красный", "синий", "зелёный"])
        self.assertEqual([v["id"] for v in out["values"]], [1, 2, 3])
        # 端点正确、翻页用上一页最后一个 id
        self.assertTrue(transport.calls[0]["url"].endswith("/v1/description-category/attribute/values"))
        self.assertEqual(transport.calls[0]["json"]["last_value_id"], 0)
        self.assertEqual(transport.calls[1]["json"]["last_value_id"], 2)

    def test_oversized_stops_early(self):
        transport = _FakeTransport([
            {"result": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}, {"id": 3, "value": "c"}], "has_next": True},
        ])
        c = OzonSellerClient("1", "k", transport=transport)
        out = c.get_attribute_values(100, 22, 99, language="RU", page_size=100, max_total=2)
        self.assertTrue(out["oversized"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::GetAttributeValuesTest -v`
Expected: FAIL，`AttributeError: 'OzonSellerClient' object has no attribute 'get_attribute_values'`

- [ ] **Step 3: 实现**

在 `ozon_api/client.py` 的 `search_attribute_values` 方法之后插入：

```python
    def get_attribute_values(
        self, description_category_id: int, type_id: int, attribute_id: int,
        *, language: str = "RU", page_size: int = 100, max_total: int = 2000,
    ) -> dict[str, Any]:
        """分页拉某属性的全部字典值。累计超过 max_total 即停止并标 oversized。
        返回 {"values": [{"id": int, "value": str}, ...], "oversized": bool}。"""
        values: list[dict[str, Any]] = []
        last_value_id = 0
        oversized = False
        while True:
            resp = self.request(
                "/v1/description-category/attribute/values",
                {
                    "description_category_id": description_category_id,
                    "type_id": type_id,
                    "attribute_id": attribute_id,
                    "language": language,
                    "limit": page_size,
                    "last_value_id": last_value_id,
                },
            )
            batch = resp.get("result") or []
            for it in batch:
                vid = it.get("id")
                if vid is None:
                    continue
                values.append({"id": int(vid), "value": str(it.get("value") or "")})
            if len(values) > max_total:
                oversized = True
                break
            if not resp.get("has_next") or not batch:
                break
            last_value_id = int(batch[-1].get("id") or 0)
        return {"values": values, "oversized": oversized}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::GetAttributeValuesTest -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add ozon_api/client.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(ozon_api): get_attribute_values 分页拉属性全部字典值 + 阈值保护"
```

---

## Task 2: adapter 层 wrapper

**Files:**
- Modify: `ozon-listing-webui/backend/ozon_client_adapter.py`（在 `search_attribute_values` 函数后）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾（`if __name__` 之前）加：

```python
import backend.ozon_client_adapter as adapter  # noqa: E402


class AdapterGetAttributeValuesTest(unittest.TestCase):
    def test_forwards_to_client(self):
        captured = {}

        class _C:
            def get_attribute_values(self, cat, typ, aid, *, language, max_total):
                captured.update(cat=cat, typ=typ, aid=aid, language=language, max_total=max_total)
                return {"values": [{"id": 5, "value": "x"}], "oversized": False}

        orig = adapter._client
        adapter._client = lambda settings: _C()
        try:
            out = adapter.get_attribute_values({"ozon_client_id": "1", "ozon_api_key": "k"},
                                               100, 22, 99, language="RU", max_total=2000)
        finally:
            adapter._client = orig
        self.assertEqual(out["values"][0]["id"], 5)
        self.assertEqual(captured, {"cat": 100, "typ": 22, "aid": 99, "language": "RU", "max_total": 2000})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::AdapterGetAttributeValuesTest -v`
Expected: FAIL，`AttributeError: module 'backend.ozon_client_adapter' has no attribute 'get_attribute_values'`

- [ ] **Step 3: 实现**

在 `ozon-listing-webui/backend/ozon_client_adapter.py` 的 `search_attribute_values` 函数之后插入：

```python
def get_attribute_values(
    settings: dict[str, Any], description_category_id: int, type_id: int,
    attribute_id: int, *, language: str = "RU", max_total: int = 2000,
) -> dict[str, Any]:
    return _client(settings).get_attribute_values(
        description_category_id, type_id, attribute_id, language=language, max_total=max_total
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::AdapterGetAttributeValuesTest -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/ozon_client_adapter.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(adapter): get_attribute_values wrapper"
```

---

## Task 3: 字典值缓存表 + store 读写

**Files:**
- Modify: `ozon-listing-webui/backend/db.py`（`MYSQL_DDL` 列表，约 157 行起）
- Modify: `ozon-listing-webui/backend/store.py`（SQLite 建表，约 203 行 `catalog_tree_cache` 之后；以及加方法）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾加：

```python
import tempfile  # noqa: E402
from backend.store import Store  # noqa: E402


class AttrValuesStoreTest(unittest.TestCase):
    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            self.assertIsNone(store.load_attr_values(100, 22, 99))
            vals = [{"id": 1, "value": "красный"}, {"id": 2, "value": "синий"}]
            store.save_attr_values(100, 22, 99, vals, False)
            got = store.load_attr_values(100, 22, 99)
            self.assertEqual(got, (vals, False))
            store.close()

    def test_oversized_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            store.save_attr_values(100, 22, 99, [], True)
            self.assertEqual(store.load_attr_values(100, 22, 99), ([], True))
            store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::AttrValuesStoreTest -v`
Expected: FAIL，`AttributeError: 'Store' object has no attribute 'load_attr_values'`

- [ ] **Step 3a: MySQL 建表**

在 `ozon-listing-webui/backend/db.py` 的 `MYSQL_DDL = [` 列表里，加一个元素（放在 `catalog_cache` 那条之后即可）：

```python
    """
    CREATE TABLE IF NOT EXISTS category_attr_values_cache (
        description_category_id BIGINT NOT NULL,
        type_id BIGINT NOT NULL,
        attribute_id BIGINT NOT NULL,
        language VARCHAR(32) NOT NULL DEFAULT 'RU',
        values_json LONGTEXT NOT NULL,
        oversized INT NOT NULL DEFAULT 0,
        fetched_at VARCHAR(40) NOT NULL,
        PRIMARY KEY (description_category_id, type_id, attribute_id, language)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
```

- [ ] **Step 3b: SQLite 建表**

在 `ozon-listing-webui/backend/store.py` 中 `catalog_tree_cache` 建表语句（约 203 行）之后插入：

```python
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS category_attr_values_cache ("
                "description_category_id INTEGER, type_id INTEGER, attribute_id INTEGER, "
                "language TEXT NOT NULL DEFAULT 'RU', values_json TEXT NOT NULL, "
                "oversized INTEGER NOT NULL DEFAULT 0, fetched_at TEXT NOT NULL, "
                "PRIMARY KEY(description_category_id, type_id, attribute_id, language))"
            )
```

- [ ] **Step 3c: store 读写方法**

在 `ozon-listing-webui/backend/store.py` 的 `load_category_attrs` 方法之后插入（与 `save_category_attrs` 同风格；`dumps_json`/`loads_json`/`utc_now_iso` 已在本文件 import）：

```python
    def save_attr_values(self, cat: int, type_id: int, attr_id: int,
                         values: list[dict[str, Any]], oversized: bool,
                         language: str = "RU") -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO category_attr_values_cache"
                "(description_category_id, type_id, attribute_id, language, values_json, oversized, fetched_at) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(description_category_id, type_id, attribute_id, language) "
                "DO UPDATE SET values_json=excluded.values_json, oversized=excluded.oversized, "
                "fetched_at=excluded.fetched_at",
                (int(cat), int(type_id), int(attr_id), str(language or "RU"),
                 dumps_json(values), 1 if oversized else 0, utc_now_iso()),
            )
            self.conn.commit()

    def load_attr_values(self, cat: int, type_id: int, attr_id: int,
                         language: str = "RU") -> tuple[list[dict[str, Any]], bool] | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT values_json, oversized FROM category_attr_values_cache "
                "WHERE description_category_id=? AND type_id=? AND attribute_id=? AND language=?",
                (int(cat), int(type_id), int(attr_id), str(language or "RU")),
            ).fetchone()
        if not row:
            return None
        vals = loads_json(row["values_json"], None)
        if vals is None:
            return None
        return (vals, bool(row["oversized"]))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::AttrValuesStoreTest -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/db.py ozon-listing-webui/backend/store.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(store): category_attr_values_cache 表 + save/load_attr_values"
```

---

## Task 4: `_ensure_attr_values`（缓存优先 + 拉取 + 阈值）

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（import 行加 `get_attribute_values`；新增方法）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾加（沿用 `test_auto_match_category.py` 的 App 构造法）：

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


class EnsureAttrValuesTest(unittest.TestCase):
    def test_fetches_then_caches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                calls = []

                def fake_get(settings, cat, typ, aid, *, language="RU", max_total=2000):
                    calls.append((cat, typ, aid))
                    return {"values": [{"id": 7, "value": "хлопок"}], "oversized": False}

                svc.get_attribute_values = fake_get
                vals, over = app._ensure_attr_values(100, 22, 99)
                self.assertEqual(vals, [{"id": 7, "value": "хлопок"}])
                self.assertFalse(over)
                # 第二次走缓存，不再调 get
                vals2, _ = app._ensure_attr_values(100, 22, 99)
                self.assertEqual(vals2, [{"id": 7, "value": "хлопок"}])
                self.assertEqual(len(calls), 1)
            finally:
                app.store.close()

    def test_oversized_cached_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                svc.get_attribute_values = lambda *a, **k: {"values": [{"id": 1, "value": "x"}], "oversized": True}
                vals, over = app._ensure_attr_values(100, 22, 99)
                self.assertEqual(vals, [])
                self.assertTrue(over)
                self.assertEqual(app.store.load_attr_values(100, 22, 99), ([], True))
            finally:
                app.store.close()

    def test_fetch_error_returns_empty_not_cached(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                def boom(*a, **k):
                    raise RuntimeError("limit")
                svc.get_attribute_values = boom
                self.assertEqual(app._ensure_attr_values(100, 22, 99), ([], False))
                self.assertIsNone(app.store.load_attr_values(100, 22, 99))  # 失败不写缓存
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::EnsureAttrValuesTest -v`
Expected: FAIL，`AttributeError: 'App' object has no attribute '_ensure_attr_values'`

- [ ] **Step 3a: 加 import**

在 `ozon-listing-webui/backend/app_service.py` 的 import 块里（已有 `get_category_attributes,` / `search_attribute_values,` 那一段），加一行：

```python
    get_attribute_values,
```

- [ ] **Step 3b: 加方法**

在 `app_service.py` 的 `_resolve_values` 方法**之前**插入：

```python
    def _ensure_attr_values(self, cat: int, typ: int, attr_id: int) -> tuple[list[dict], bool]:
        """确保本地有该属性的全部字典值。返回 (values, oversized)。
        命中缓存直接返回；未命中拉全量并存库；oversized 时 values 存空、走实时搜；
        拉取失败返回 ([], False)（不写缓存，调用方回退实时 search）。"""
        cached = self.store.load_attr_values(cat, typ, attr_id, language="RU")
        if cached is not None:
            return cached
        try:
            out = get_attribute_values(self.store.get_settings(), cat, typ, attr_id,
                                       language="RU", max_total=2000)
        except Exception:  # noqa: BLE001
            return ([], False)
        oversized = bool(out.get("oversized"))
        store_values: list[dict] = [] if oversized else (out.get("values") or [])
        self.store.save_attr_values(cat, typ, attr_id, store_values, oversized, language="RU")
        return (store_values, oversized)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::EnsureAttrValuesTest -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(app): _ensure_attr_values 缓存优先拉全量字典值 + 阈值/失败处理"
```

---

## Task 5: `_local_match_value`（本地精确匹配）

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（`_ensure_attr_values` 之后）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾加：

```python
class LocalMatchTest(unittest.TestCase):
    def test_exact_case_insensitive(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                vals = [{"id": 1, "value": "Красный"}, {"id": 2, "value": "Синий"}]
                self.assertEqual(app._local_match_value(vals, "красный"),
                                 {"dictionary_value_id": 1, "value": "Красный"})
                self.assertEqual(app._local_match_value(vals, "  СИНИЙ "),
                                 {"dictionary_value_id": 2, "value": "Синий"})
                self.assertIsNone(app._local_match_value(vals, "зелёный"))
                self.assertIsNone(app._local_match_value(vals, "a"))  # <2 字符
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::LocalMatchTest -v`
Expected: FAIL，`AttributeError: ... '_local_match_value'`

- [ ] **Step 3: 实现**

在 `app_service.py` 的 `_ensure_attr_values` 之后插入：

```python
    @staticmethod
    def _local_match_value(values: list[dict], text: str) -> dict | None:
        """在缓存的字典值里按俄文精确匹配（strip+lower 相等）。
        命中返回 {"dictionary_value_id": id, "value": value}，否则 None。"""
        t = str(text or "").strip().lower()
        if len(t) < 2:
            return None
        for v in values:
            if str(v.get("value") or "").strip().lower() == t:
                return {"dictionary_value_id": int(v["id"]), "value": str(v.get("value") or text)}
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::LocalMatchTest -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(app): _local_match_value 本地字典值精确匹配"
```

---

## Task 6: 改 `_resolve_values`（本地优先 + 实时搜兜底）

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（替换 `_resolve_values` 方法体；新增 `_search_one_value`）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

当前 `_resolve_values` 直接对每个值调 `search_attribute_values`。改成：先 `_ensure_attr_values` 本地匹配，没命中（或 oversized）才调实时搜（抽成 `_search_one_value`）。

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾加：

```python
class ResolveValuesTest(unittest.TestCase):
    def test_local_hit_skips_search(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app.store.save_attr_values(100, 22, 99, [{"id": 5, "value": "Хлопок"}], False)

                def boom(*a, **k):
                    raise AssertionError("不应调用实时搜")
                svc.search_attribute_values = boom
                out = app._resolve_values(100, 22, 99, ["хлопок"], False)
                self.assertEqual(out, [{"dictionary_value_id": 5, "value": "Хлопок"}])
            finally:
                app.store.close()

    def test_local_miss_falls_back_to_search(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app.store.save_attr_values(100, 22, 99, [{"id": 5, "value": "Хлопок"}], False)
                calls = []

                def fake_search(settings, cat, typ, aid, value, language="RU"):
                    calls.append(value)
                    return {"result": [{"id": 8, "value": "Шёлк"}]}
                svc.search_attribute_values = fake_search
                out = app._resolve_values(100, 22, 99, ["шёлк"], False)
                self.assertEqual(out, [{"dictionary_value_id": 8, "value": "Шёлк"}])
                self.assertEqual(calls, ["шёлк"])
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::ResolveValuesTest -v`
Expected: FAIL（`test_local_hit_skips_search` 因旧实现会调 search 而触发 AssertionError）

- [ ] **Step 3: 实现**

把 `app_service.py` 里现有的 `_resolve_values` 方法体整体替换为：

```python
    def _resolve_values(self, cat: int, typ: int, attr_id: int, texts: list[str],
                        is_collection: bool) -> list[dict]:
        """把(俄文)文本值解析成 Ozon 字典值 [{dictionary_value_id, value}]。
        先用本地缓存的全量字典值精确匹配；没命中或字典超大(oversized)才实时 search。"""
        values, oversized = self._ensure_attr_values(cat, typ, attr_id)
        out: list[dict] = []
        seen: set[int] = set()
        for t in (texts if is_collection else texts[:1]):
            if len(str(t).strip()) < 2:
                continue
            hit = None if oversized else self._local_match_value(values, t)
            if hit is None:
                hit = self._search_one_value(cat, typ, attr_id, t)
            if not hit:
                continue
            vid = int(hit["dictionary_value_id"])
            if vid and vid not in seen:
                seen.add(vid)
                out.append({"dictionary_value_id": vid, "value": hit["value"]})
        return out

    def _search_one_value(self, cat: int, typ: int, attr_id: int, text: str) -> dict | None:
        """实时搜单个值（兜底）。精确优先，否则取第一个结果。失败/无结果返回 None。"""
        try:
            resp = search_attribute_values(self.store.get_settings(), cat, typ, attr_id, text, language="RU")
            res = resp.get("result") or []
        except Exception:  # noqa: BLE001
            return None
        if not res:
            return None
        t = str(text).strip().lower()
        hit = next((r for r in res if str(r.get("value") or "").strip().lower() == t), res[0])
        vid = _to_int(hit.get("id"))
        if not vid:
            return None
        return {"dictionary_value_id": vid, "value": str(hit.get("value") or text)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::ResolveValuesTest -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 回归既有用例**

Run: `python -m pytest tests/test_auto_match_category.py tests/test_variant_publish.py -v`
Expected: PASS（`_resolve_values` 的调用方仍工作）

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "perf(app): _resolve_values 本地缓存优先匹配，未命中才实时搜"
```

---

## Task 7: `auto_map_attributes` 并发兜底

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（新增 `_resolve_pairs_concurrent`；改 `auto_map_attributes` 字典属性循环）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

并发理由：首次采某类目时，对几十个字典属性各自 `_ensure_attr_values` 要拉全量字典值；串行会让首次很慢。用线程池并发，让"首次拉取"和"兜底搜"都并行。

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾加：

```python
class ResolvePairsConcurrentTest(unittest.TestCase):
    def test_resolves_each_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app.store.save_attr_values(100, 22, 11, [{"id": 1, "value": "Красный"}], False)
                app.store.save_attr_values(100, 22, 22, [{"id": 2, "value": "M"}], False)

                def boom(*a, **k):
                    raise AssertionError("本地命中不应实时搜")
                svc.search_attribute_values = boom
                res = app._resolve_pairs_concurrent(100, 22, [
                    (11, ["красный"], False),
                    (22, ["m"], False),
                ])
                self.assertEqual(res[11], [{"dictionary_value_id": 1, "value": "Красный"}])
                self.assertEqual(res[22], [{"dictionary_value_id": 2, "value": "M"}])
            finally:
                app.store.close()

    def test_empty_tasks(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                self.assertEqual(app._resolve_pairs_concurrent(100, 22, []), {})
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::ResolvePairsConcurrentTest -v`
Expected: FAIL，`AttributeError: ... '_resolve_pairs_concurrent'`

- [ ] **Step 3a: 加并发解析方法**

在 `app_service.py` 的 `_search_one_value` 之后插入：

```python
    def _resolve_pairs_concurrent(self, cat: int, typ: int,
                                  tasks: list[tuple[int, list[str], bool]]) -> dict[int, list[dict]]:
        """并发解析多个字典属性的值。tasks = [(attr_id, texts, is_collection), ...]。
        返回 {attr_id: [{dictionary_value_id, value}, ...]}。本地命中不走网络，未命中并发实时搜。"""
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        if not tasks:
            return {}

        def _one(task: tuple[int, list[str], bool]) -> tuple[int, list[dict]]:
            aid, texts, is_coll = task
            return (aid, self._resolve_values(cat, typ, aid, texts, is_coll))

        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as ex:
            return dict(ex.map(_one, tasks))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::ResolvePairsConcurrentTest -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 改 `auto_map_attributes` 用并发解析**

在 `auto_map_attributes` 里，把现有"逐个 `p` 循环、对字典属性调 `_resolve_values`"那段（从 `mapped: list[dict] = []` 到该 for 循环结束、`new_attributes = ...` 之前）替换为：

```python
        mapped: list[dict] = []
        unmapped: list[dict] = []
        dict_tasks: list[tuple[int, list[str], bool]] = []     # (aid, texts, is_collection)
        dict_meta: dict[int, dict] = {}                        # aid -> {name, text}
        free_text: list[tuple[int, str, str]] = []             # (aid, text, name)
        for p in pairs:
            attr, ch = p["attr"], p["char"]
            aid = _to_int(attr.get("id"))
            if aid == BRAND_ATTR_ID:
                continue
            text = str(ch.get("value") or "")
            if attr.get("dictionary_id"):
                dict_tasks.append((aid, split_collection_value(text), bool(attr.get("is_collection"))))
                dict_meta[aid] = {"name": attr.get("name"), "text": text}
            else:  # 自由文本属性
                free_text.append((aid, text, str(attr.get("name") or "")))

        resolved = self._resolve_pairs_concurrent(cat_i, typ_i, dict_tasks)
        for aid, meta in dict_meta.items():
            values = resolved.get(aid) or []
            if not values:
                unmapped.append({"id": aid, "name": meta["name"], "value": meta["text"]})
                continue
            publish_by_id[aid] = {"id": aid, "values": values}
            mapped.append({"id": aid, "name": meta["name"],
                           "value": " , ".join(v["value"] for v in values)})
        for aid, text, name in free_text:
            publish_by_id[aid] = {"id": aid, "values": [{"value": text}]}
            mapped.append({"id": aid, "name": name, "value": text})
```

（`publish_by_id` 在这段之前已构造，保持不动；其余 `new_attributes = ...` 起的代码不变。）

- [ ] **Step 6: 回归 + 提交**

Run: `python -m pytest tests/test_attr_values_cache.py -v`
Expected: PASS（全绿）

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "perf(app): auto_map_attributes 字典属性并发解析（首次拉取/兜底搜并行）"
```

---

## Task 8: 把自动映射放回采集流程

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（`ext_collect_parsed` 两处返回前恢复 `_auto_map_safe`）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

- [ ] **Step 1: 写失败测试**

在 `test_attr_values_cache.py` 末尾加（验证采集后会触发自动映射）：

```python
class CollectTriggersAutoMapTest(unittest.TestCase):
    def test_ext_collect_parsed_calls_auto_map(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                seen = []
                app._auto_map_safe = lambda did: seen.append(did)
                # 跳过类目自动匹配的外部依赖
                app._auto_match_category = lambda scraped: None
                res = app.ext_collect_parsed({"url": "https://www.ozon.ru/product/x-1/",
                                              "data": {"title": "t"}})
                created = res.get("created") or []
                self.assertTrue(created)
                self.assertEqual(seen, [created[0]["id"]])  # 新建草稿后调了一次自动映射
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_attr_values_cache.py::CollectTriggersAutoMapTest -v`
Expected: FAIL（当前 `ext_collect_parsed` 已无 `_auto_map_safe` 调用，`seen` 为空）

- [ ] **Step 3: 恢复调用**

在 `app_service.py` 的 `ext_collect_parsed` 里：

新建分支（方法末尾），把
```python
        saved = self.store.insert_draft(new_draft)
        # 视频走 OSS（插件已传，data.video_url 已是 OSS 直链）；属性自动映射(auto-map)挪到
        # 编辑器「自动填充」按需做——它要逐个属性跨境查 Ozon(曾达 20s+)，绝不能卡在采集流程里。
        return {"created": [{"id": saved["id"], "source_title": saved.get("source_title")}], "errors": []}
```
改为
```python
        saved = self.store.insert_draft(new_draft)
        # 视频走 OSS（插件已传，data.video_url 已是 OSS 直链）
        self._auto_map_safe(saved["id"])   # 采集后自动映射属性（已本地缓存化，快）
        return {"created": [{"id": saved["id"], "source_title": saved.get("source_title")}], "errors": []}
```

重复采集分支（`deduped` 那条），把
```python
            # 视频走 OSS（插件已传）；属性自动映射(auto-map)挪到编辑器「自动填充」按需做——
            # 它要逐个属性跨境查 Ozon(曾达 20s+)，绝不能卡在采集流程里。
            return {"created": [{"id": existing["id"], "source_title": existing.get("source_title")}], "errors": [], "deduped": True}
```
改为
```python
            self._auto_map_safe(existing["id"])   # 采集后自动映射属性（已本地缓存化，快）
            return {"created": [{"id": existing["id"], "source_title": existing.get("source_title")}], "errors": [], "deduped": True}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_attr_values_cache.py::CollectTriggersAutoMapTest -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `python -m pytest tests/ -q`
Expected: 全绿（无回归）

- [ ] **Step 6: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(app): 采集后自动映射属性放回采集流程（属性映射已本地缓存化）"
```

---

## 部署（全部任务完成后）

```bash
# 1. 本地全量回归
cd ozon-listing-webui && python -m pytest tests/ -q && cd ..
# 2. 打包上传 + 重建镜像 + 重启（沿用现有部署脚本）
tar -czf /c/Users/42918/.ozon-deploy/app.tgz \
  --exclude='ozon-listing-webui/frontend/node_modules' --exclude='ozon-listing-webui/.venv' \
  --exclude='**/__pycache__' --exclude='*.pyc' --exclude='ozon-listing-webui/data' \
  ozon-listing-webui ozon_api
sh /c/Users/42918/.ozon-deploy/put.sh /c/Users/42918/.ozon-deploy/app.tgz /root/app.tgz
# 然后在服务器 tar 解压 + docker build + docker run（见前几次部署命令；新表会在容器启动时自动建）
```

验证：采一次新类目商品（首次拉字典稍慢、几秒），再采同类目第二件（应秒级、属性已自动填好）。

---

## 自检（写计划时已核对）

- **spec 覆盖**：全量拉取端点(T1)、wrapper(T2)、缓存表(T3)、缓存优先+阈值+失败回退(T4)、本地匹配(T5)、本地优先解析(T6)、并发兜底+首次并发拉(T7)、放回采集(T8)、品牌跳过填无品牌(auto_map 现状未改动，T7 保留 `if aid == BRAND_ATTR_ID: continue`)。
- **无占位符**：每步含可运行的测试/实现代码与确切命令。
- **类型一致**：`load_attr_values` 返回 `tuple[list,bool]|None`；`_ensure_attr_values` 返回 `tuple[list,bool]`；`get_attribute_values` 返回 `{"values","oversized"}`——T1/T3/T4/T6/T7 引用一致。`_resolve_values` 签名不变（T6 内部改），`auto_map_attributes` / `_no_brand_value` 调用方不破坏。
