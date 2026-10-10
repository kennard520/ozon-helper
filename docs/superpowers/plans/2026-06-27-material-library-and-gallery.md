# 素材库 / 图集(两池图片模型)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans。Steps 用 checkbox(`- [ ]`)。

**Goal:** 给 `draft_images` 加 `in_gallery` 标记,把"每变体一池图"拆成 **素材库(全部图)+ 图集(in_gallery=1,真正发布)**;新图按语义落池(采集→素材、AI出图→图集);图片编辑改成**按 id 细粒度操作 + 图集感知 _sync(不再删全表重插)**;跨变体复制改造成细粒度多目标。

**Architecture:** 一张表 + `in_gallery` 标记(不加 variant_group、不改 FK)。`DraftRepo`(webui)与 `DraftImageRepo`(worker)读路径产出 `images`=图集 + `materials`=全部;写路径用 `add_to_gallery/remove_from_gallery/delete_image/reorder_gallery` 细粒度方法;`_sync_draft_images` 重写为图集感知(UPDATE 标记/position,只 INSERT 真新图,**不 DELETE 全表**),保护素材行。HTTP 增图集管理端点;`copy-images-to` 改造成多目标、落目标图集。

**Tech Stack:** SQLAlchemy Core、Alembic、FastAPI、pytest(SQLite)。

**全局约定:** 仓库根 `E:\personal\ozon-helper`;分支 `feat/auto-listing-ai-pipeline`;**`uv` 用 `python -m uv`**;中文提交,结尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。回归 `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider`,**≥ 660 不下降**。ruff 只带本任务文件。SQLite 临时库测试 `try/finally: eng.dispose()` + `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`。

参考 spec:`docs/superpowers/specs/2026-06-27-material-library-and-gallery-design.md`。

---

## File Structure

| 文件 | 职责 | 改动 |
|---|---|---|
| `packages/ozon_common/src/ozon_common/dal/schema.py` | 表结构 | draft_images 加 `in_gallery` 列 |
| `migrations/versions/0006_in_gallery.py` | 迁移 | 新建:加列默认 1 |
| `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py` | webui 主仓储 | 读(images=图集+materials)、写(_sync 图集感知、采集 in_gallery=0) |
| `packages/ozon_common/src/ozon_common/dal/repositories/draft_image_repo.py` | worker 仓储 + 图集细粒度操作 | add_draft_image 加 in_gallery;新增 add_to_gallery/remove_from_gallery/delete_image/reorder_gallery/copy_images;读 images=图集 |
| `apps/webui/src/webui/main.py` | HTTP 路由 | 新增图集管理端点;改造 copy-images-to |
| `apps/webui/src/webui/app_service.py` | 服务层 | copy_images_to_draft 改造成多目标细粒度 |

---

## Task 1:schema + Alembic 0006(in_gallery 列)

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/schema.py`(draft_images 表,约 287-300)
- Create: `migrations/versions/0006_in_gallery.py`
- Test: `packages/ozon_common/tests/test_in_gallery_migration.py`

- [ ] **Step 1: schema 加列**

`schema.py` draft_images 表,在 `source` 列后加:
```python
    Column("in_gallery", Integer, nullable=False, server_default="1"),
```
(放在 `Column("source", ...)` 之后、`Column("created_at", ...)` 之前。`Integer` 已 import。)

- [ ] **Step 2: 写迁移**

`migrations/versions/0006_in_gallery.py`(参照 0002-0005 头部风格,`down_revision = "0005_fk"` —— 先确认 0005 文件里的 revision 名,用其值):
```python
"""0006 draft_images.in_gallery 两池标记

Revision ID: 0006_in_gallery
Revises: 0005_fk
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_in_gallery"
down_revision = "0005_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "draft_images",
        sa.Column("in_gallery", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("draft_images", "in_gallery")
```
**先做**:`grep -n "revision" migrations/versions/0005_fk*.py` 确认 0005 的 `revision = "..."` 实际值,把 `down_revision` 对上(若不是 `0005_fk` 则改成实际值)。

- [ ] **Step 3: 写测试(先红)**

`packages/ozon_common/tests/test_in_gallery_migration.py`:
```python
"""in_gallery 列:create_all 含该列,默认 1。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, insert, select

from ozon_common.dal.schema import metadata, draft_images as DI, drafts as DR


def test_in_gallery_column_default_1():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = create_engine(f"sqlite:///{Path(tmp) / 'g.db'}")
        try:
            metadata.create_all(eng)
            assert "in_gallery" in DI.c, "draft_images 缺 in_gallery 列"
            with eng.begin() as c:
                c.execute(insert(DR).values(id=1, user_id=1, source_platform="1688",
                                            source_url="u", created_at="2026-01-01T00:00:00+00:00",
                                            updated_at="2026-01-01T00:00:00+00:00"))
                c.execute(insert(DI).values(draft_id=1, position=0, url="x",
                                            created_at="2026-01-01T00:00:00+00:00"))
                v = c.execute(select(DI.c.in_gallery).where(DI.c.url == "x")).scalar()
            assert v == 1, f"in_gallery 默认应为 1,实际 {v}"
        finally:
            eng.dispose()
```
> 注:drafts 必填列若不止上面几个会报错——按 schema.py drafts 的 `nullable=False` 列补齐 values(没有 server_default 的才必填)。先跑,按报错补。

- [ ] **Step 4: 跑测试** `cd /e/personal/ozon-helper && python -m uv run python -m pytest packages/ozon_common/tests/test_in_gallery_migration.py -q -p no:cacheprovider 2>&1 | tail -8` → PASS。

- [ ] **Step 5: 全量回归** `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider 2>&1 | tail -3` → **≥ 661**(原 660 + 本测试)。

- [ ] **Step 6: ruff + 提交**
```bash
python -m ruff check --select I --fix packages/ozon_common/src/ozon_common/dal/schema.py migrations/versions/0006_in_gallery.py packages/ozon_common/tests/test_in_gallery_migration.py 2>&1 | tail -2
git add packages/ozon_common/src/ozon_common/dal/schema.py migrations/versions/0006_in_gallery.py packages/ozon_common/tests/test_in_gallery_migration.py
git commit -m "feat(dal): draft_images 加 in_gallery 两池标记 + Alembic 0006(默认1,老草稿不变)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2:DraftRepo 读模型(images=图集 + materials=全部)

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py`(`_load_draft_images` 452、`_load_draft_images_batch` 460、`_row_to_draft` 512)
- Test: `packages/ozon_common/tests/test_two_pool_read.py`

- [ ] **Step 1: 写测试(先红)**

`packages/ozon_common/tests/test_two_pool_read.py`:
```python
"""get_draft:images=图集(in_gallery=1),materials=全部(带 id/in_gallery)。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, insert

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.schema import metadata, draft_images as DI
from ozon_common.dal.repositories.draft_repo import DraftRepo
from webui.drafts import create_draft_from_url


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 't.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def test_images_is_gallery_materials_is_all():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope():
                d = create_draft_from_url("https://detail.1688.com/offer/100000000001.html")
                did = DraftRepo().insert_draft(d, user_id=1)
                # 直接插两行:一张素材(in_gallery=0)、一张图集(in_gallery=1)
                S.current_session().execute(insert(DI).values(
                    draft_id=did, position=0, url="http://m/material.jpg",
                    type="细节图", source="collected", in_gallery=0,
                    created_at="2026-01-01T00:00:00+00:00"))
                S.current_session().execute(insert(DI).values(
                    draft_id=did, position=1, url="http://m/gallery.jpg",
                    type="白底主图", source="generated", in_gallery=1,
                    created_at="2026-01-01T00:00:00+00:00"))
            with S.session_scope():
                got = DraftRepo().get_draft(did)
            # images 只含图集那张
            assert got["images"] == ["http://m/gallery.jpg"], got["images"]
            # materials 含两张,带 id/in_gallery/type/source/position
            urls = {m["url"]: m for m in got["materials"]}
            assert set(urls) == {"http://m/material.jpg", "http://m/gallery.jpg"}
            assert urls["http://m/material.jpg"]["in_gallery"] == 0
            assert urls["http://m/gallery.jpg"]["in_gallery"] == 1
            assert isinstance(urls["http://m/material.jpg"]["id"], int)
            assert urls["http://m/gallery.jpg"]["type"] == "白底主图"
        finally:
            eng.dispose()
```
> `create_draft_from_url` 默认可能带 images;若带,断言前先把它产生的图清掉或改用不带图的构造。先跑,按实际调整 setup(关键是验证 in_gallery 过滤 + materials 形状)。

- [ ] **Step 2: 跑测试确认红** → FAIL(无 materials / images 含全部)。

- [ ] **Step 3: 改读取(带 in_gallery + id,产出 materials)**

`_load_draft_images`(452)改为带 id/in_gallery,并支持只取图集:
```python
    def _load_draft_images(self, draft_id: int, *, gallery_only: bool = False) -> list[dict[str, Any]]:
        conds = [DI.c.draft_id == int(draft_id)]
        if gallery_only:
            conds.append(DI.c.in_gallery == 1)
        rows = self.s.execute(
            select(DI.c.id, DI.c.url, DI.c.type, DI.c.source, DI.c.in_gallery, DI.c.position)
            .where(*conds).order_by(DI.c.position)
        ).all()
        return [{"id": int(r.id), "url": r.url, "type": r.type, "source": r.source,
                 "in_gallery": int(r.in_gallery), "position": int(r.position)} for r in rows]
```

`_load_draft_images_batch`(460)同样带新字段(取全部,不过滤):
```python
    def _load_draft_images_batch(self, draft_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        ids = [int(i) for i in draft_ids]
        if not ids:
            return {}
        rows = self.s.execute(
            select(DI.c.draft_id, DI.c.id, DI.c.url, DI.c.type, DI.c.source,
                   DI.c.in_gallery, DI.c.position)
            .where(DI.c.draft_id.in_(ids)).order_by(DI.c.draft_id, DI.c.position)
        ).all()
        out: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(int(r.draft_id), []).append(
                {"id": int(r.id), "url": r.url, "type": r.type, "source": r.source,
                 "in_gallery": int(r.in_gallery), "position": int(r.position)})
        return out
```

`_row_to_draft`(512):`dimg_rows` 现在是"全部图"(materials),从中过滤出图集做 images/image_types,并加 materials 字段:
```python
        # dimg_rows = 全部图(materials);images/image_types 只取图集(in_gallery=1)
        all_imgs = images if images is not None else self._load_draft_images(m["id"])
        gallery = [r for r in all_imgs if r.get("in_gallery", 1)]
        images_list = [r["url"] for r in gallery]
        image_types = {r["url"]: r["type"] for r in gallery if r["type"]}
```
并在返回 dict 里 `"images": images_list,` 之后加:
```python
            "materials": [
                {"id": r["id"], "url": r["url"], "type": r["type"],
                 "source": r["source"], "in_gallery": r["in_gallery"],
                 "position": r["position"]}
                for r in all_imgs
            ],
```
(列表批量路径传入的 `images` 已是"全部图带 in_gallery",过滤逻辑同样生效,N+1 不回退。)

- [ ] **Step 4: 跑测试确认绿** → PASS。

- [ ] **Step 5: 全量回归** ≥ 662。**重点**:test_drafts/test_pagination/test_publish_group/test_variant_publish/test_draft_list_no_n1 必须仍绿(老数据 in_gallery=1 → images=全部,不变)。

- [ ] **Step 6: ruff + 提交**(只带 draft_repo.py + 新测试)
```
git commit -m "feat(dal): DraftRepo 读模型两池化(images=图集 in_gallery=1 + materials=全部)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3:写入落池(采集→0、AI出图→1)+ _sync 图集感知

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py`(`_sync_draft_images` 477;`insert_draft` 142、`update_draft` 215、媒体更新 259 三处调用)
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_image_repo.py`(`add_draft_image` 34)
- Test: `packages/ozon_common/tests/test_two_pool_write.py`

- [ ] **Step 1: 写测试(先红)**

`packages/ozon_common/tests/test_two_pool_write.py`:
```python
"""写入落池:采集图→素材(in_gallery=0),AI出图→图集(in_gallery=1);
_sync 图集感知:编辑图集不删素材、不删表全行。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, select, func

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.schema import metadata, draft_images as DI
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo
from webui.drafts import create_draft_from_url


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'w.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def test_collected_to_material_ai_to_gallery_and_sync_keeps_material():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope():
                d = create_draft_from_url("https://detail.1688.com/offer/100000000002.html")
                d["images"] = ["http://c/0.jpg", "http://c/1.jpg"]  # 采集图
                did = DraftRepo().insert_draft(d, user_id=1)
            with S.session_scope():
                got = DraftRepo().get_draft(did)
            # 采集图进素材、图集为空
            assert got["images"] == []
            assert {m["url"] for m in got["materials"]} == {"http://c/0.jpg", "http://c/1.jpg"}
            assert all(m["in_gallery"] == 0 for m in got["materials"])
            # AI 出图 → 图集
            with S.session_scope():
                DraftImageRepo().add_draft_image(did, "http://ai/main.jpg", type="白底主图", source="generated")
            with S.session_scope():
                got = DraftRepo().get_draft(did)
            assert got["images"] == ["http://ai/main.jpg"]
            # _sync 图集感知:把图集设成 [ai/main],素材两张不动、总行数=3(不删表)
            with S.session_scope():
                DraftRepo()._sync_draft_images(did, ["http://ai/main.jpg"])
                n = S.current_session().execute(
                    select(func.count()).select_from(DI).where(DI.c.draft_id == did)).scalar()
            assert n == 3, f"总行数应为 3(2素材+1图集),实际 {n}——_sync 删了素材"
        finally:
            eng.dispose()
```

- [ ] **Step 2: 跑测试确认红** → FAIL。

- [ ] **Step 3a: add_draft_image 加 in_gallery**

`draft_image_repo.py:add_draft_image`(34)签名加 `in_gallery: int | None = None`,默认按 source 推断(generated→1,其它→0),并写入 insert:
```python
    def add_draft_image(self, draft_id, url, *, type="", source="generated", in_gallery=None):
        if in_gallery is None:
            in_gallery = 1 if source == "generated" else 0
        nxt = (self.s.execute(
            select(func.coalesce(func.max(DI.c.position), -1) + 1)
            .where(DI.c.draft_id == int(draft_id))).scalar() or 0)
        res = self.s.execute(insert(DI).values(
            draft_id=int(draft_id), position=int(nxt), url=str(url),
            type=str(type or ""), source=str(source), in_gallery=int(in_gallery),
            created_at=utc_now_iso()))
        return int(res.inserted_primary_key[0])
```
(worker `_row_to_draft` 81-100 也改成只取图集:`select(DI.c.url, DI.c.type).where(draft_id == ... , DI.c.in_gallery == 1)`——加 `DI.c.in_gallery == 1` 过滤,保持 worker 的 images=图集 与 webui 一致。)

- [ ] **Step 3b: _sync_draft_images 重写(图集感知,不删全表)**

`draft_repo.py:_sync_draft_images`(477)整体替换:
```python
    def _sync_draft_images(self, draft_id, images, image_types=None, *, gallery=True):
        """gallery=True:把 images 当成"目标图集顺序"同步——已有行 UPDATE in_gallery/position,
        新 url INSERT(in_gallery=1),原图集中不在 images 的行降级 in_gallery=0(留素材)。**不 DELETE 全表**。
        gallery=False:初始采集——全部 INSERT 为素材(in_gallery=0)。"""
        now = utc_now_iso()
        types = dict(image_types or {})
        rows = self.s.execute(
            select(DI.c.id, DI.c.url, DI.c.type, DI.c.in_gallery).where(DI.c.draft_id == int(draft_id))
        ).all()
        by_url = {str(r.url): r for r in rows}
        target = [str(u) for u in images]
        target_set = set(target)
        if not gallery:
            base = self.s.execute(
                select(func.coalesce(func.max(DI.c.position), -1) + 1).where(DI.c.draft_id == int(draft_id))
            ).scalar() or 0
            for i, url in enumerate(target):
                if url in by_url:
                    continue
                self.s.execute(insert(DI).values(
                    draft_id=int(draft_id), position=int(base) + i, url=url,
                    type=types.get(url) or "其他", source="collected", in_gallery=0, created_at=now))
            return
        # gallery 模式
        for url, r in by_url.items():
            if r.in_gallery == 1 and url not in target_set:
                self.s.execute(update(DI).where(DI.c.id == r.id).values(in_gallery=0))
        for i, url in enumerate(target):
            r = by_url.get(url)
            if r is not None:
                self.s.execute(update(DI).where(DI.c.id == r.id).values(in_gallery=1, position=i))
            else:
                self.s.execute(insert(DI).values(
                    draft_id=int(draft_id), position=i, url=url,
                    type=types.get(url) or "其他", source="generated", in_gallery=1, created_at=now))
```
(`update` 需 import:`from sqlalchemy import ... update`——确认 draft_repo.py 顶部已 import update,没有则加。)

- [ ] **Step 3c: insert_draft 用 gallery=False**

`insert_draft`(142 调用处):把 `self._sync_draft_images(draft_id, ...)` 改为 `self._sync_draft_images(draft_id, ..., gallery=False)`(采集图进素材)。`update_draft`(215)与媒体更新(259)保持默认 `gallery=True`(它们改的是图集/url)。

> 注:媒体更新 259(`update_draft_media` rehost 换 url)默认 gallery=True 会把 rehost 后的 url 当图集——但 rehost 是把图集里的图换成公网 url,本就在图集,语义正确。

- [ ] **Step 4: 跑测试确认绿** → PASS。

- [ ] **Step 5: 全量回归** ≥ 663。**重点**:test_drafts(采集后 images 断言)可能因"采集图现进素材、images 空"而**需要更新断言**——这是预期的语义变更:把这些测试里"采集后 draft['images'] 含采集图"改为"draft['materials'] 含采集图、images 空"。逐个核对修正(这是真实语义变更,不是 bug)。

- [ ] **Step 6: ruff + 提交**
```
git commit -m "feat(dal): 写入落池(采集→素材0/AI出图→图集1)+ _sync 图集感知(UPDATE 标记不删全表)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4:图集细粒度操作(add/remove/delete/reorder)

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_image_repo.py`(新增 4 方法)
- Test: `packages/ozon_common/tests/test_gallery_ops.py`

- [ ] **Step 1: 写测试(先红)**

`packages/ozon_common/tests/test_gallery_ops.py`:
```python
"""细粒度图集操作:add/remove/delete/reorder 按 id,id 稳定,素材不误删。"""
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, insert, select

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.schema import metadata, draft_images as DI, drafts as DR
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo


def _setup(tmp):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'o.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def _seed(did):
    s = S.current_session()
    s.execute(insert(DR).values(id=did, user_id=1, source_platform="1688", source_url=f"u{did}",
              created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00"))
    ids = []
    for i, ig in enumerate([0, 0, 1]):  # 2素材 + 1图集
        r = s.execute(insert(DI).values(draft_id=did, position=i, url=f"http://x/{i}.jpg",
                      type="", source="collected", in_gallery=ig,
                      created_at="2026-01-01T00:00:00+00:00"))
        ids.append(int(r.inserted_primary_key[0]))
    return ids  # [mat0, mat1, gal2]


def test_add_remove_delete_reorder():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _setup(tmp)
        try:
            with S.session_scope():
                ids = _seed(1)
            repo = lambda: DraftImageRepo()
            # add 素材0 进图集
            with S.session_scope():
                repo().add_to_gallery(1, [ids[0]])
            with S.session_scope():
                g = S.current_session().execute(
                    select(DI.c.in_gallery).where(DI.c.id == ids[0])).scalar()
            assert g == 1
            # remove 图集2 → 留素材
            with S.session_scope():
                repo().remove_from_gallery(1, [ids[2]])
            with S.session_scope():
                g = S.current_session().execute(
                    select(DI.c.in_gallery).where(DI.c.id == ids[2])).scalar()
            assert g == 0
            # delete 素材1 → 行没了,其它行 id 不变
            with S.session_scope():
                repo().delete_image(1, ids[1])
            with S.session_scope():
                left = {int(r.id) for r in S.current_session().execute(
                    select(DI.c.id).where(DI.c.draft_id == 1)).all()}
            assert ids[1] not in left and ids[0] in left
            # reorder 图集(现图集=[ids[0]]):设顺序
            with S.session_scope():
                repo().reorder_gallery(1, [ids[0]])
                p = S.current_session().execute(
                    select(DI.c.position).where(DI.c.id == ids[0])).scalar()
            assert p == 0
        finally:
            eng.dispose()
```

- [ ] **Step 2: 跑测试确认红** → FAIL(方法不存在)。

- [ ] **Step 3: 实现 4 方法**(`draft_image_repo.py`,顶部 import 加 `update, delete`)
```python
    def add_to_gallery(self, draft_id, image_ids):
        ids = [int(i) for i in image_ids]
        if not ids:
            return
        base = (self.s.execute(select(func.coalesce(func.max(DI.c.position), -1) + 1)
                .where(DI.c.draft_id == int(draft_id), DI.c.in_gallery == 1)).scalar() or 0)
        for off, iid in enumerate(ids):
            self.s.execute(update(DI).where(DI.c.id == iid, DI.c.draft_id == int(draft_id))
                           .values(in_gallery=1, position=int(base) + off))

    def remove_from_gallery(self, draft_id, image_ids):
        ids = [int(i) for i in image_ids]
        if ids:
            self.s.execute(update(DI).where(DI.c.draft_id == int(draft_id), DI.c.id.in_(ids))
                           .values(in_gallery=0))

    def delete_image(self, draft_id, image_id):
        self.s.execute(delete(DI).where(DI.c.draft_id == int(draft_id), DI.c.id == int(image_id)))

    def reorder_gallery(self, draft_id, ordered_image_ids):
        for pos, iid in enumerate(int(i) for i in ordered_image_ids):
            self.s.execute(update(DI).where(DI.c.id == iid, DI.c.draft_id == int(draft_id),
                           DI.c.in_gallery == 1).values(position=pos))
```

- [ ] **Step 4: 跑测试确认绿** → PASS。
- [ ] **Step 5: 全量回归** ≥ 664。
- [ ] **Step 6: ruff + 提交**
```
git commit -m "feat(dal): 图集细粒度操作 add/remove/delete/reorder(按 id,不 churn)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5:图集管理 HTTP 端点

**Files:**
- Modify: `apps/webui/src/webui/main.py`(在 copy-images-to 端点 898 附近加)
- Modify: `apps/webui/src/webui/app_service.py`(加薄封装方法,调 DraftImageRepo,走 session/UoW)
- Test: `apps/webui/tests/test_gallery_endpoints.py`

- [ ] **Step 1: 看现有端点风格**:`sed -n '884,915p' apps/webui/src/webui/main.py` + 看 app_service 里某个改图方法怎么开 session(找 `with` / UoW 模式),照抄。

- [ ] **Step 2: 写测试(先红)** —— 用现有测试客户端 fixture(参照 `apps/webui/tests/` 里调 `/api/drafts/.../copy-images-to` 或类似的测试),建草稿+素材,POST `/api/drafts/{id}/gallery/add` 后断言 `get_draft` 的 images 含该图。(按现有测试 client fixture 写;先 grep `apps/webui/tests` 找一个调用图片端点的测试照搬骨架。)

- [ ] **Step 3: app_service 加 4 方法**(薄封装,事务内调 DraftImageRepo)
```python
    def gallery_add(self, draft_id, image_ids):
        with self.uow():               # ← 用本仓库实际的事务/ session 上下文(照抄同文件其它写方法)
            DraftImageRepo().add_to_gallery(draft_id, image_ids)
        return self.store.get_draft(draft_id)
    # remove/delete/reorder 同形
```
> 关键:`self.uow()` 是占位——**照抄 app_service 里现有"改 draft_images 后返回 draft"的写方法的事务写法**(同文件 copy_images_to_draft 3785 就有现成模式:它直接调 self.store.update_draft;这里改成 DraftImageRepo 细粒度,事务边界对齐 store 的写)。实现时先读 3785 与其上下文确定 session 获取方式。

- [ ] **Step 4: main.py 加端点**
```python
@app.post("/api/drafts/{draft_id}/gallery/add")
def gallery_add(draft_id: int, body: dict) -> dict:
    return APP.gallery_add(draft_id, (body or {}).get("image_ids") or [])

@app.post("/api/drafts/{draft_id}/gallery/remove")
def gallery_remove(draft_id: int, body: dict) -> dict:
    return APP.gallery_remove(draft_id, (body or {}).get("image_ids") or [])

@app.post("/api/drafts/{draft_id}/gallery/reorder")
def gallery_reorder(draft_id: int, body: dict) -> dict:
    return APP.gallery_reorder(draft_id, (body or {}).get("image_ids") or [])

@app.delete("/api/drafts/{draft_id}/images/{image_id}")
def delete_draft_image(draft_id: int, image_id: int) -> dict:
    return APP.gallery_delete(draft_id, image_id)
```

- [ ] **Step 5: 跑测试确认绿 + 全量回归** ≥ 665。
- [ ] **Step 6: ruff + 提交**
```
git commit -m "feat(webui): 图集管理端点 gallery/add|remove|reorder + 删图

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6:跨变体复制改造(多目标 + 落图集)

**Files:**
- Modify: `apps/webui/src/webui/app_service.py`(`copy_images_to_draft` 3785)
- Modify: `apps/webui/src/webui/main.py`(`copy-images-to` 端点 898,接 target_draft_ids)
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_image_repo.py`(加 `copy_images`)
- Test: `apps/webui/tests/test_copy_images_multi.py`

- [ ] **Step 1: 写测试(先红)**:同组建两个变体 A、B(同 variant_group),A 有图集图;调 copy 到 [B];断言 B 的 images(图集)新增该图、去重、source/type 复制;再调一次断言不重复。(参照现有 copy-images-to 测试骨架。)

- [ ] **Step 2: DraftImageRepo 加 copy_images**
```python
    def copy_images(self, src_draft_id, image_urls, target_draft_ids):
        """把 src 的指定 url 复制到每个目标变体的图集(in_gallery=1),按 url 去重。返回 {tid: added}。"""
        urls = [str(u).strip() for u in image_urls if str(u).strip()]
        src_rows = {str(r.url): r for r in self.s.execute(
            select(DI.c.url, DI.c.type, DI.c.source).where(
                DI.c.draft_id == int(src_draft_id), DI.c.url.in_(urls))).all()}
        out = {}
        for tid in [int(t) for t in target_draft_ids]:
            have = {str(r.url) for r in self.s.execute(
                select(DI.c.url).where(DI.c.draft_id == tid)).all()}
            added = 0
            for u in urls:
                if u in have:
                    continue
                sr = src_rows.get(u)
                self.add_draft_image(tid, u, type=(sr.type if sr else ""),
                                     source=(sr.source if sr else "generated"), in_gallery=1)
                added += 1
            out[tid] = added
        return out
```

- [ ] **Step 3: app_service.copy_images_to_draft 改造**(接 target_draft_ids 列表,保留同组校验)
```python
    def copy_images_to_draft(self, draft_id, image_urls, target_draft_ids):
        if not image_urls:
            raise ValueError("未选择图片")
        targets = [int(t) for t in (target_draft_ids or []) if int(t)]
        if not targets:
            raise ValueError("未指定目标变体")
        src = self.store.get_draft(draft_id)
        if src is None:
            raise KeyError(f"draft {draft_id} not found")
        vg_src = str((src.get("source_raw") or {}).get("variant_group") or "")
        for tid in targets:
            tgt = self.store.get_draft(tid)
            if tgt is None:
                raise KeyError(f"draft {tid} not found")
            vg_tgt = str((tgt.get("source_raw") or {}).get("variant_group") or "")
            if vg_src and vg_src != vg_tgt:
                raise ValueError("只能在同一变体组内复制图片")
        added = DraftImageRepo().copy_images(draft_id, image_urls, targets)  # 在 store 的事务内调
        return {"ok": True, "added": added}
```
> 事务:照抄 store 写方法的 session 获取(同 Task 5)。

- [ ] **Step 4: main.py 端点接 target_draft_ids(兼容旧 target_draft_id)**
```python
@app.post("/api/drafts/{draft_id}/copy-images-to")
def copy_images_to_target(draft_id: int, body: dict) -> dict:
    b = body or {}
    targets = b.get("target_draft_ids")
    if not targets and b.get("target_draft_id"):
        targets = [b["target_draft_id"]]
    try:
        return APP.copy_images_to_draft(draft_id, b.get("image_urls") or [], targets or [])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 5: 跑测试确认绿 + 全量回归** ≥ 666。现有 copy-images-to 测试(单 target_draft_id)必须仍绿(兼容)。
- [ ] **Step 6: ruff + 提交**
```
git commit -m "feat(webui): 跨变体复制图片改造(多目标+细粒度INSERT+落目标图集,兼容旧单目标)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7:收尾回归 + N+1 复核

- [ ] **Step 1: 全量回归** `python -m uv run python -m pytest apps/webui/tests packages/ozon_common/tests --ignore-glob='*_live.py' -q -p no:cacheprovider 2>&1 | tail -5` → 全绿(应 ≥ 666)。
- [ ] **Step 2: N+1 复核** 跑 `test_draft_list_no_n1.py` 确认仍只 1 次 draft_images 批量查(读模型加了字段但没回退批量)。
- [ ] **Step 3: 全新 SQLite create_all 自检**:`python -m uv run python -c "from ozon_common.dal.schema import metadata; from sqlalchemy import create_engine; e=create_engine('sqlite://'); metadata.create_all(e); print('in_gallery' in [c.name for c in __import__('ozon_common.dal.schema', fromlist=['draft_images']).draft_images.c])"` → True。
- [ ] **Step 4: 无新增提交则跳过**;有遗漏 ruff/收尾改动则提交。

---

## Self-Review
- **Spec 覆盖**:① in_gallery 列+迁移→T1;② 读模型 images=图集/materials=全部→T2;③ 写入落池+_sync 图集感知→T3;④ 细粒度 add/remove/delete/reorder→T4;⑤ HTTP 端点→T5;⑥ 跨变体复制多目标落图集→T6;⑦ 发布走 images=图集→T2 自动达成(不需改 listing_build);⑧ N+1 不回退→T7 复核。全覆盖。
- **占位符**:T5/T6 的 `self.uow()` 是显式标注的"照抄现有事务写法"占位——已点明读 app_service 3785 现有模式确定 session 获取,非真空泛占位(实现者有明确出处)。其余步骤均含真实代码。
- **类型一致**:`in_gallery` int(0/1) 贯穿;materials 形状 `{id,url,type,source,in_gallery,position}` 在 T2 定义、T4/T6 复用;`add_draft_image(..., in_gallery=None)`、`copy_images(src, urls, target_ids)->{tid:added}`、`add_to_gallery(draft_id, image_ids)` 等签名前后一致。
- **风险点**:T3 Step5 —— 采集语义变更会让若干"采集后 images 含采集图"的现有测试变红,**这是预期**,需把断言改成 materials;实现者要逐个甄别"语义变更"vs"真 bug"。已在步骤里点明。
