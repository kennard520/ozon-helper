# 数据访问层 M5：草稿列表 N+1 批量化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。Steps 用 checkbox。

**Goal:** 把 `DraftRepo` 列表方法里"逐行查 draft_images"(N+1)改成"一次批量查 + Python 分组装配",一页查询数从 1+N(最多 201)降到 2。行为不变,659 兜底。

**Architecture:** 单文件 `draft_repo.py` 内部优化。新增 `_load_draft_images_batch(ids)`,`_row_to_draft(row, images=None)` 接预加载图(None 则回退单行查),三个列表方法走批量,单行方法不变。无 schema/契约变更。

**Tech Stack:** SQLAlchemy Core、pytest(SQLAlchemy event 计查询数)。

**全局约定:** 仓库根 `E:\personal\ozon-helper`;分支 `feat/auto-listing-ai-pipeline`;**`uv` 用 `python -m uv`**;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。回归 `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider`,**≥ 659**。

---

## Task 1：DraftRepo 列表 N+1 批量化

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py`
- Create: `packages/ozon_common/tests/test_draft_list_no_n1.py`

- [ ] **Step 1: 写查询计数测试(先红)**

Create `packages/ozon_common/tests/test_draft_list_no_n1.py`:
```python
"""M5:list_drafts_page 对 draft_images 只发 1 次 SELECT(N+1 消除)。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, event

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.schema import metadata
from ozon_common.dal.repositories.draft_repo import DraftRepo
from webui.drafts import create_draft_from_url


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'n1.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def test_list_drafts_page_batches_images():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            # 造 3 个草稿,各带 2 张图
            with S.session_scope():
                repo = DraftRepo()
                for i in range(3):
                    d = create_draft_from_url(f"https://detail.1688.com/offer/10000000000{i}.html")
                    d["images"] = [f"http://x/{i}-0.jpg", f"http://x/{i}-1.jpg"]
                    repo.insert_draft(d, user_id=1)
            # 计数 draft_images 的 SELECT 次数
            counter = {"n": 0}

            @event.listens_for(eng, "before_cursor_execute")
            def _count(conn, cursor, statement, params, context, executemany):
                s = statement.lower()
                if "from draft_images" in s and s.strip().startswith("select"):
                    counter["n"] += 1

            with S.session_scope():
                drafts, total = DraftRepo().list_drafts_page(user_id=1, page=1, page_size=20)
            assert total == 3
            assert len(drafts) == 3
            # 每个草稿都带 2 张图(装配正确)
            assert all(len(d["images"]) == 2 for d in drafts)
            # 关键:draft_images 只查 1 次(批量),不是 3 次(N+1)
            assert counter["n"] == 1, f"draft_images 查询了 {counter['n']} 次(应为 1,N+1 未消除)"
        finally:
            eng.dispose()
```

- [ ] **Step 2: 跑测试,确认先红(当前 N+1)**

Run: `cd /e/personal/ozon-helper && python -m uv run python -m pytest packages/ozon_common/tests/test_draft_list_no_n1.py -q -p no:cacheprovider 2>&1 | tail -8`
Expected: **FAIL**,`counter['n'] == 3`(当前每行单查 = N+1)。

- [ ] **Step 3: 实现批量化**

改 `draft_repo.py`:

(a) 新增私有批量方法(放在 `_load_draft_images` 附近):
```python
    def _load_draft_images_batch(self, draft_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """一次查多个 draft 的图,按 draft_id 分组。空 ids → {}。"""
        ids = [int(i) for i in draft_ids]
        if not ids:
            return {}
        rows = self.s.execute(
            select(DI.c.draft_id, DI.c.url, DI.c.type, DI.c.source)
            .where(DI.c.draft_id.in_(ids))
            .order_by(DI.c.draft_id, DI.c.position)
        ).all()
        out: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(int(r.draft_id), []).append(
                {"url": r.url, "type": r.type, "source": r.source}
            )
        return out
```

(b) `_row_to_draft` 签名加 `images=None`,用预加载图(否则回退单行查):
```python
    def _row_to_draft(self, row, images: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        m = row._mapping
        source_platform = m["source_platform"]
        purchase_url = m["purchase_url"] or (
            m["source_url"] if source_platform == "1688" else ""
        )
        # 图片从 draft_images 一对多表读;列表场景由调用方预加载(批量),单行场景回退单查
        dimg_rows = images if images is not None else self._load_draft_images(m["id"])
        images_list = [r["url"] for r in dimg_rows]
        image_types = {r["url"]: r["type"] for r in dimg_rows if r["type"]}
        # ... 其余装配逻辑【完全不变】,把原来的 `images = [...]` 变量名若与新参数冲突则用 images_list ...
```
**注意**:原 `_row_to_draft` 里局部变量名是 `images`(line 499 `images = [r["url"]...]`),现在参数也叫 `images`——把**局部那个**改名 `images_list`,并把返回 dict 里 `"images": images` 改为 `"images": images_list`。其余字段一字不动。

(c) 四个**列表**调用点改批量(收集 ids → 批量 → 逐行喂图):
- `list_drafts`(约 288-292):
```python
    def list_drafts(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.s.execute(
            select(D).where(D.c.user_id == int(user_id)).order_by(D.c.id.desc())
        ).all()
        imgs = self._load_draft_images_batch([r._mapping["id"] for r in rows])
        return [self._row_to_draft(r, imgs.get(r._mapping["id"], [])) for r in rows]
```
- `list_drafts_page` **普通分支**(约 370-377):
```python
        rows = self.s.execute(
            select(D).where(*conds).order_by(D.c.id.desc()).limit(page_size).offset(offset)
        ).all()
        imgs = self._load_draft_images_batch([r._mapping["id"] for r in rows])
        return [self._row_to_draft(r, imgs.get(r._mapping["id"], [])) for r in rows], total
```
- `list_drafts_page` **group 分支**(约 354-364):在 `rows = ... by_id = {...}` 之后,`for g in page_groups` 之前加 `imgs = self._load_draft_images_batch(list(by_id.keys()))`;循环里 `d = self._row_to_draft(r, imgs.get(r._mapping["id"], []))`。
- `list_drafts_by_variant_group`(约 409-417):
```python
        rows = self.s.execute(
            select(D).where(D.c.variant_group == group).order_by(D.c.id.asc())
        ).all()
        imgs = self._load_draft_images_batch([r._mapping["id"] for r in rows])
        return [self._row_to_draft(r, imgs.get(r._mapping["id"], [])) for r in rows]
```

(d) **单行**调用点(`get_draft`/`find_by_source_url`/`find_by_offer_id`):保持 `self._row_to_draft(row)`(不传 images → 回退单行查,1 次,无需改)。✅ 这几处**不用动**。

- [ ] **Step 4: 跑测试,确认绿(1 次查询)**

Run: `cd /e/personal/ozon-helper && python -m uv run python -m pytest packages/ozon_common/tests/test_draft_list_no_n1.py -q -p no:cacheprovider 2>&1 | tail -5`
Expected: **PASS**(`counter['n'] == 1`)。

- [ ] **Step 5: 全量回归(parity)**

Run: `cd /e/personal/ozon-helper && python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider 2>&1 | tail -3`
Expected: **≥ 659**(原 659 + 本测试 = 660)。draft 列表/分页/分组测试(test_drafts/test_pagination/test_publish_group/test_variant_publish)必须仍绿——证明装配行为不变。

- [ ] **Step 6: ruff + 提交**

```bash
cd /e/personal/ozon-helper && python -m ruff check --select I --fix packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py packages/ozon_common/tests/test_draft_list_no_n1.py 2>&1 | tail -2
git add packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py packages/ozon_common/tests/test_draft_list_no_n1.py
git commit -m "perf(dal): M5 草稿列表 draft_images 批量取图,消除 N+1

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git log --oneline -1
```
(ruff 只带这两个文件,无关 deploy/scripts 别带。)

---

## Self-Review
- **Spec 覆盖**:批量取图(_load_draft_images_batch)/_row_to_draft 加 images 参/三列表方法走批量/单行不变/查询计数测试 → 全在 Task 1。
- **占位符**:无;批量方法、_row_to_draft 改法、四列表调用点都给了真实代码。
- **类型一致**:`_load_draft_images_batch(draft_ids)->dict[int,list[dict]]`、`_row_to_draft(row, images=None)`、`r._mapping["id"]` 取 id 贯穿一致。变量名冲突(局部 images vs 参数 images)已显式提示改 `images_list`。
- **风险**:仅 `images=None` 回退分支 + 变量改名易错,Step3(b) 已点明;parity 由 659 + 计数测试双验。
