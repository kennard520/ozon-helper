# 采集属性优化（原产国一律中国 + 并发16）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 auto_map 对原产国属性一律填“中国”（不管竞品采到什么、没采到也填），并把属性映射并发从 8 提到 16。

**Architecture:** 这是 spec `2026-06-20-collect-perf-v2-design.md` 的 Part 1（后端小改）。媒体后台异步（Part 2/3）是单独的计划二。本计划只动 `app_service.py`，两个独立任务。

**Tech Stack:** Python 3 / FastAPI、`unittest`、`ThreadPoolExecutor`。

**测试怎么跑：** 在 `ozon-listing-webui/` 目录下：`PYTHONPATH=. python tests/test_attr_values_cache.py -v`（pytest 未安装，用 unittest）。

---

## Task 1: 原产国一律“中国”

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（新增 `_force_country_to_china` 方法；`auto_map_attributes` 在 `free_text` 循环后调用它）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`

背景：`auto_map_attributes`（`app_service.py:~982` 起）里 `meta = self._category_attrs(cat_i, typ_i, language="RU")` 是俄文类目属性表，`publish_by_id`（dict，键=attribute_id）是最终要发布的属性。原产国属性俄文名含 `Страна`（如 `Страна-изготовитель`）。要做到：只要类目有原产国属性，就强制填“中国”（`Китай`），覆盖竞品采到的任何值，竞品没采到也填。`_to_int` / `BRAND_ATTR_ID` 已在本文件可用。

- [ ] **Step 1: 写失败测试**

在 `ozon-listing-webui/tests/test_attr_values_cache.py` 末尾（`if __name__` 之前）加：

```python
class ForceCountryChinaTest(unittest.TestCase):
    def test_fills_china_when_category_has_country_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                # _resolve_values 只对 "Китай" 返回字典值，证明强制用的是中国
                def fake_resolve(cat, typ, aid, texts, is_coll):
                    if texts == ["Китай"]:
                        return [{"dictionary_value_id": 999, "value": "Китай"}]
                    return [{"dictionary_value_id": 1, "value": texts[0]}]
                app._resolve_values = fake_resolve
                meta = [{"id": 4389, "name": "Страна-изготовитель"}, {"id": 100, "name": "Цвет"}]
                publish, mapped = {}, []
                # 即使竞品已把原产国填成别的，也要被覆盖成中国
                publish[4389] = {"id": 4389, "values": [{"dictionary_value_id": 7, "value": "Россия"}]}
                app._force_country_to_china(100, 22, meta, publish, mapped)
                self.assertEqual(publish[4389], {"id": 4389, "values": [{"dictionary_value_id": 999, "value": "Китай"}]})
            finally:
                app.store.close()

    def test_noop_when_no_country_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc, app = _make_app(tmp)
            try:
                app._resolve_values = lambda *a, **k: [{"dictionary_value_id": 1, "value": "x"}]
                meta = [{"id": 100, "name": "Цвет"}]
                publish = {}
                app._force_country_to_china(100, 22, meta, publish, [])
                self.assertEqual(publish, {})
            finally:
                app.store.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. python tests/test_attr_values_cache.py ForceCountryChinaTest -v`（在 `ozon-listing-webui/` 目录）
Expected: FAIL，`AttributeError: 'App' object has no attribute '_force_country_to_china'`

- [ ] **Step 3: 实现方法**

在 `app_service.py` 的 `auto_map_attributes` 方法**之后**（即 `_no_brand_value` 之前）插入：

```python
    def _force_country_to_china(self, cat: int, typ: int, meta: list[dict],
                                publish_by_id: dict, mapped: list[dict]) -> None:
        """原产国一律「中国」：类目里只要有原产国属性(俄文名含 Страна)，就把它的值强制
        设成 Китай(中国)、覆盖竞品采到的任何值；竞品没采到也主动填。与采集内容无关。"""
        for attr in meta:
            if "страна" not in str(attr.get("name") or "").lower():
                continue
            caid = _to_int(attr.get("id"))
            if not caid or caid == BRAND_ATTR_ID:
                continue
            cvals = self._resolve_values(cat, typ, caid, ["Китай"], False)
            if cvals:
                publish_by_id[caid] = {"id": caid, "values": cvals}
                mapped.append({"id": caid, "name": attr.get("name"), "value": "Китай"})
```

- [ ] **Step 4: 在 auto_map_attributes 里调用**

在 `app_service.py` 的 `auto_map_attributes` 里，把这一段：

```python
        for aid, text, name in free_text:
            publish_by_id[aid] = {"id": aid, "values": [{"value": text}]}
            mapped.append({"id": aid, "name": name, "value": text})

        new_attributes = passthrough + list(publish_by_id.values())
```

改成（在 `new_attributes = ...` 之前插入一行调用）：

```python
        for aid, text, name in free_text:
            publish_by_id[aid] = {"id": aid, "values": [{"value": text}]}
            mapped.append({"id": aid, "name": name, "value": text})

        self._force_country_to_china(cat_i, typ_i, meta, publish_by_id, mapped)  # 原产国一律中国
        new_attributes = passthrough + list(publish_by_id.values())
```

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONPATH=. python tests/test_attr_values_cache.py ForceCountryChinaTest -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 回归**

Run: `PYTHONPATH=. python tests/test_ext_bridge.py 2>&1 | tail -2`
Expected: OK（auto_map 整体不破）

- [ ] **Step 7: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py ozon-listing-webui/tests/test_attr_values_cache.py
git commit -m "feat(app): 原产国一律中国（类目有该属性就强制填Китай，不管竞品采到啥）"
```

---

## Task 2: 属性映射并发 8 → 16

**Files:**
- Modify: `ozon-listing-webui/backend/app_service.py`（`_resolve_pairs_concurrent` 的 `max_workers`）
- Test: `ozon-listing-webui/tests/test_attr_values_cache.py`（现有 `ResolvePairsConcurrentTest` 回归即可）

- [ ] **Step 1: 改并发上限**

在 `app_service.py` 的 `_resolve_pairs_concurrent` 里，把：

```python
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as ex:
            return dict(ex.map(lambda c, t: c.run(_one, t), ctxs, tasks))
```

改成：

```python
        with ThreadPoolExecutor(max_workers=min(16, len(tasks))) as ex:
            return dict(ex.map(lambda c, t: c.run(_one, t), ctxs, tasks))
```

- [ ] **Step 2: 跑现有并发测试确认不破**

Run: `PYTHONPATH=. python tests/test_attr_values_cache.py ResolvePairsConcurrentTest -v`
Expected: PASS（并发数变大不影响结果正确性）

- [ ] **Step 3: 提交**

```bash
git add ozon-listing-webui/backend/app_service.py
git commit -m "perf(app): 属性映射并发上限 8 -> 16"
```

---

## 部署（两任务完成后）

```bash
cd ozon-listing-webui && PYTHONPATH=. python tests/test_attr_values_cache.py 2>&1 | tail -2 && cd ..
# 重建镜像 + 重启（沿用现有部署脚本：tar 上传 + docker build + docker run）
```

属性优化是纯后端改动，部署后立即生效，**用户无需刷新插件**。

---

## 自检（写计划时已核对）

- **spec 覆盖**：Part 1 的三条——原产国一律中国(Task 1)、并发16(Task 2)、全属性映射(未改动，本来就全映射)、品牌无品牌(未动)。
- **无占位符**：每步含可运行测试/实现代码与确切命令。
- **类型一致**：`_force_country_to_china(cat, typ, meta, publish_by_id, mapped)` 签名在测试与调用处一致；用 `_resolve_values` 已有签名 `(cat, typ, attr_id, texts, is_collection)`。
