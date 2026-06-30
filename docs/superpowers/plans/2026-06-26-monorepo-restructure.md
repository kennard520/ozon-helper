# Monorepo 项目化重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `ozon-listing-webui`(后端)与 `ozon-image-worker` 改造成 uv workspace 单仓多包结构(`packages/ozon_common`、`packages/ozon_api`、`apps/webui`、`apps/image_worker`),消除 worker 对 backend 6 个模块的复制粘贴,行为保持不变。

**Architecture:** 四个 workspace 成员,单向依赖 `webui → {ozon_common, ozon_api}`、`image_worker → ozon_common`。共享内核(db/oss/mq/gen_image/image_plan + settings/json/draft_images 数据访问)集中到 `ozon_common`,webui 与 worker 都依赖同一份。webui 的大 `Store`(1946 行业务数据层)留在 webui 不动其内部。

**Tech Stack:** Python 3.11+/3.14、uv(workspace + lock)、src-layout 包、ruff(import 排序)、pytest(512 个 SQLite 单测做回归基线)、Docker(uv 多阶段)。

**全局约定:**
- 仓库根 = `E:\personal\ozon-helper`(git-bash 路径 `/e/personal/ozon-helper`)。
- **回归基线命令(下称「基线测试」)**:
  ```bash
  cd /e/personal/ozon-helper/ozon-listing-webui && python -m pytest tests -q --ignore-glob='*_live.py' -p no:cacheprovider
  ```
  迁移前先记录通过数(预期 ~512 collected;`*_live.py` 需真实服务,跳过)。每个改动导入/移动的 Task 后必须重跑且通过数不下降。
- **worker 冒烟**:worker 依赖 MySQL/RabbitMQ,无法整跑;验证以「导入成功」为准:
  ```bash
  cd /e/personal/ozon-helper && uv run --package ozon-image-worker python -c "import image_worker.worker; print('ok')"
  ```
- **ruff import 检查**:`python -m ruff check --select I packages apps`(根 pyproject 已配 isort 规则)。
- 提交信息结尾固定加:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- 当前分支 `feat/auto-listing-ai-pipeline`,**就在此分支上推进**(用户已确认开干)。

---

## File Structure(决策锁定)

新建/移动后的关键文件职责:

| 路径 | 来源 | 职责 |
|---|---|---|
| `pyproject.toml`(根) | 新建 | uv workspace + [tool.uv] 阿里云镜像 + [tool.ruff] |
| `packages/ozon_common/src/ozon_common/db.py` | ← `backend/db.py`(canonical) | SQLite+MySQL 方言层;worker 用 `make_mysql_conn` |
| `…/ozon_common/oss.py` | ← `backend/oss.py` | OSS 客户端(含 `OssClient`) |
| `…/ozon_common/mq.py` | ← `backend/mq.py` + 替换 consume | `publish_gen_job`(webui)+ 4 参 `consume_gen_jobs`(worker) |
| `…/ozon_common/gen_image.py` | ← `backend/gen_image.py` | 出图 SDK(含 `GenImageConfig`、prompts、`build_infographic_prompt`) |
| `…/ozon_common/image_plan.py` | ← `backend/image_plan.py` | `build_image_plan` |
| `…/ozon_common/jsonio.py` | 新建(取自 worker/store.py) | `utc_now_iso` / `dumps_json` / `loads_json` |
| `…/ozon_common/settings.py` | 新建(取自 worker/store.py) | `_KIND_ENGINE` / `_ai_platforms` / `ai_config` / `oss_config` |
| `…/ozon_common/draft_images.py` | 新建(取自 worker/store.py 的 `DataStore`) | gen_jobs/draft_images 数据访问,worker 用 |
| `packages/ozon_api/src/ozon_api/**` | ← `ozon_api/**`(git mv) | Ozon Seller API 客户端 + 选品定价流 |
| `apps/webui/src/webui/**` | ← `ozon-listing-webui/backend/**`(git mv,删 5 个基础设施模块) | web 业务层;`backend.` → `webui.`;共享导入 → `ozon_common.` |
| `apps/webui/src/webui/server.py` | ← `ozon-listing-webui/run_api.py` | 启动器;`backend.main:app` → `webui.main:app` |
| `apps/image_worker/src/image_worker/worker.py` | ← `ozon-image-worker/worker.py` | 删本地 6 模块,导入指向 `ozon_common.` |

**ozon_common 依赖边界说明(回答 spec §4 的精化):**
- `jsonio` + `settings` 是跨 webui 内部就重复的纯函数(`backend/drafts.py`、`backend/settings_migrate.py`、worker 各一份)→ 三处统一 import 自 `ozon_common`,这是高价值低风险去重,本计划完成。
- `draft_images.DataStore` 是 worker 的数据访问类;webui 的大 `Store` 有平行的同名方法(`add_draft_image`/`create_gen_job_images` 等)。**本计划不重构 webui 的 `Store` 去调用 `DataStore`**(在 1946 行、且分支有 WIP 的大类上做收敛风险过高、收益边际)。`Store` 与 `DataStore` 的方法收敛列为后续独立工作。worker 独占消费 `ozon_common.draft_images`。

---

## Task 0: 基线与 WIP 提交

**Files:** 无新建;提交现有工作区改动。

- [ ] **Step 1: 记录回归基线**

Run:
```bash
cd /e/personal/ozon-helper/ozon-listing-webui && python -m pytest tests -q --ignore-glob='*_live.py' -p no:cacheprovider 2>&1 | tail -5
```
Expected: 末尾形如 `NNN passed`(记下 NNN,作为后续不可下降的基线;若已有少量 fail,记下 `X failed` 数,后续不可增加)。

- [ ] **Step 2: 提交当前 WIP 作为干净基线**

Run:
```bash
cd /e/personal/ozon-helper && git add -A && git status --short | head
```
检查待提交内容(含前序 requirements/scratch/ruff import 整理改动)。然后:
```bash
git commit -m "chore: 重构前基线快照(requirements/scratch 归档/import 排序)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git log --oneline -1
```
Expected: 一条新提交;`git status` 干净(除被忽略项)。

---

## Task 1: uv workspace 骨架

**Files:**
- Create: `pyproject.toml`(根)
- Create: 目录 `packages/`、`apps/`(占位)

- [ ] **Step 1: 确认 uv 可用**

Run: `uv --version`
Expected: 打印版本号。若「command not found」,先装:`python -m pip install uv` 或 `pipx install uv`,再重试。

- [ ] **Step 2: 写根 `pyproject.toml`**

Create `pyproject.toml`:
```toml
[tool.uv.workspace]
members = ["packages/*", "apps/*"]

[tool.uv]
# 国内加速:阿里云 PyPI 镜像(本地与 Docker 共用)
index-url = "https://mirrors.aliyun.com/pypi/simple/"

[tool.uv.sources]
ozon-common = { workspace = true }
ozon-api = { workspace = true }

[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["I"]

[tool.ruff.lint.isort]
known-first-party = ["ozon_common", "ozon_api", "webui", "image_worker"]
```
说明:本文件取代之前临时建的根 ruff 配置(若存在 `[tool.ruff]` 单独文件,合并进此处即可)。

- [ ] **Step 3: 建占位目录**

Run:
```bash
cd /e/personal/ozon-helper && mkdir -p packages apps && echo "skeleton ok"
```

- [ ] **Step 4: 提交**

```bash
git add pyproject.toml && git commit -m "build: 初始化 uv workspace 骨架(根 pyproject + 阿里云镜像 + ruff)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `ozon_common` —— 基础设施模块(db/oss/mq/gen_image/image_plan)

**Files:**
- Create: `packages/ozon_common/pyproject.toml`、`packages/ozon_common/src/ozon_common/__init__.py`
- Move: `ozon-listing-webui/backend/{db,oss,mq,gen_image,image_plan}.py` → `packages/ozon_common/src/ozon_common/`
- Modify: `packages/ozon_common/src/ozon_common/mq.py`(替换 consume_gen_jobs)
- Delete(稍后 Task 6): worker 的同名副本

- [ ] **Step 1: 建包骨架**

Create `packages/ozon_common/pyproject.toml`:
```toml
[project]
name = "ozon-common"
version = "0.1.0"
description = "Ozon 上品助手共享内核:db/oss/mq/出图/数据访问"
requires-python = ">=3.10"
dependencies = [
    "PyMySQL>=1.1",
    "oss2>=2.18",
    "pika>=1.3",
    "openai>=1.30",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
Create `packages/ozon_common/src/ozon_common/__init__.py`:
```python
"""Ozon 上品助手共享内核包。"""
```

- [ ] **Step 2: 迁移 5 个基础设施模块(git mv,backend 为 canonical)**

Run:
```bash
cd /e/personal/ozon-helper
DST=packages/ozon_common/src/ozon_common
for m in db oss mq gen_image image_plan; do
  git mv ozon-listing-webui/backend/$m.py $DST/$m.py
done
ls $DST
```
Expected: 列出 `db.py oss.py mq.py gen_image.py image_plan.py __init__.py`。

- [ ] **Step 3: 合并 mq.py 的 consume(用 worker 的 4 参版)**

`packages/ozon_common/src/ozon_common/mq.py` 当前的 `consume_gen_jobs` 是旧 3 参版(`Callable[[int,int,int],None]`)。worker 需要 4 参(带 `mode`)。打开 worker 的 `ozon-image-worker/mq.py`,把它的 `consume_gen_jobs` 函数体整体替换进 `ozon_common/mq.py` 的同名函数(保留 `publish_gen_job` 不变)。替换后该函数签名应为:
```python
def consume_gen_jobs(callback: Callable[[int, int, int, str], None]) -> None:
```
并确保回调以 `(job_id, draft_id, target, mode)` 四参调用(参照 worker 版实现)。

验证 webui 内无人调用旧 consume:
```bash
cd /e/personal/ozon-helper && grep -rn "consume_gen_jobs" ozon-listing-webui | grep -v test
```
Expected: 无 webui 业务调用(只 worker 用)。若有,需同步改其调用签名。

- [ ] **Step 4: 并入 worker 的 MySQL 连接工厂到 db.py**

worker 用 `make_conn()`;`ozon_common/db.py`(原 backend)只有 `make_mysql_conn()`。在 `ozon_common/db.py` 末尾追加别名,避免 worker 改名:
```python


def make_conn() -> "MySQLConn":
    """worker 用的 MySQL 连接工厂别名(= make_mysql_conn)。"""
    return make_mysql_conn()
```
若 `ozon_common/db.py` 的 `mysql_config()` 不是从环境变量 `OZON_MYSQL_HOST/PORT/USER/PASSWORD/DB` 读取(worker 运行时依赖这些 env),则保留其现有逻辑即可——`make_mysql_conn` 内部已用 `mysql_config`;仅当二者 env 字段不一致时,以兼容 worker env 为准补齐。

- [ ] **Step 5: 修正 ozon_common 内部相对导入**

这 5 个模块原来在 `backend` 包内若互相引用(如 `gen_image` 引 `db`),用的是 `from backend.x` 或 `from .x`。统一改为包内相对导入。检查并修正:
```bash
cd /e/personal/ozon-helper && grep -rnE "from backend\.|import backend|from \.\.?[a-z]" packages/ozon_common/src/ozon_common
```
对每条命中:`from backend.db import X` → `from ozon_common.db import X`(或 `from .db import X`)。

- [ ] **Step 6: 导入冒烟**

Run:
```bash
cd /e/personal/ozon-helper && uv sync 2>&1 | tail -3 && uv run python -c "import ozon_common.db, ozon_common.oss, ozon_common.mq, ozon_common.gen_image, ozon_common.image_plan; print('ozon_common infra ok')"
```
Expected: `ozon_common infra ok`。(`uv sync` 首次会创建根 `.venv` 并装好四包。)

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "refactor(common): 迁入 db/oss/mq/gen_image/image_plan 到 ozon_common(mq consume 取 worker 4 参版)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `ozon_common` —— store 内核(jsonio / settings / draft_images)

**Files:**
- Create: `packages/ozon_common/src/ozon_common/{jsonio,settings,draft_images}.py`

源内容取自 `ozon-image-worker/store.py`(worker 版,干净且最新)。

- [ ] **Step 1: 写 `jsonio.py`**

Create `packages/ozon_common/src/ozon_common/jsonio.py`:
```python
"""JSON / 时间小工具(跨 webui 与 worker 共用)。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def loads_json(text: object, default=None):
    if not text:
        return default
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(str(text))
    except (TypeError, ValueError):
        return default
```

- [ ] **Step 2: 写 `settings.py`**

Create `packages/ozon_common/src/ozon_common/settings.py`:
```python
"""从 settings 字典解析 AI / OSS 配置(跨 webui 与 worker 共用)。"""

from __future__ import annotations

_KIND_ENGINE = {"text": "agnes", "multimodal": "agnes", "image": "gptimage", "video": "agnes"}


def _ai_platforms(settings: dict) -> dict:
    out: dict = {}
    for p in settings.get("ai_platforms") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        out[name] = {"base": str(p.get("base") or p.get("api_base") or "").strip(),
                     "key": str(p.get("key") or p.get("api_key") or "").strip()}
    return out


def ai_config(settings: dict, kind: str) -> dict:
    """kind ∈ text/image/video/multimodal → {engine, base, key, model}。"""
    slot = settings.get(f"ai_{kind}") if isinstance(settings.get(f"ai_{kind}"), dict) else {}
    plat_name = str(slot.get("platform") or "").strip()
    if plat_name:
        p = _ai_platforms(settings).get(plat_name)
        if p:
            return {"engine": _KIND_ENGINE.get(kind, "agnes"),
                    "base": p["base"], "key": p["key"],
                    "model": str(slot.get("model") or "").strip()}
    eng = str(slot.get("engine") or "").strip().lower()
    return {"engine": eng, "base": str(slot.get("api_base") or "").strip(),
            "key": str(slot.get("api_key") or "").strip(),
            "model": str(slot.get("model") or "").strip()}


def oss_config(settings: dict) -> dict:
    return {
        "endpoint": str(settings.get("oss_endpoint") or ""),
        "bucket_name": str(settings.get("oss_bucket") or ""),
        "access_key_id": str(settings.get("oss_access_key_id") or ""),
        "access_key_secret": str(settings.get("oss_access_key_secret") or ""),
        "public_base": str(settings.get("oss_public_base") or ""),
    }
```

- [ ] **Step 3: 写 `draft_images.py`(worker 的 DataStore)**

Create `packages/ozon_common/src/ozon_common/draft_images.py`,内容 = worker `store.py` 的 `DataStore` 类及其依赖,但改用 ozon_common 的 db/jsonio:
```python
"""gen_jobs / draft_images 数据访问(worker 出图链路用)。"""

from __future__ import annotations

import json
from typing import Any

from ozon_common.db import make_conn
from ozon_common.jsonio import loads_json, utc_now_iso

USER_ID = 1  # worker 固定读取 admin 用户 settings


class DataStore:
    def __init__(self) -> None:
        self.conn = make_conn()

    def close(self) -> None:
        self.conn.close()

    def get_settings(self) -> dict:
        out = {}
        for uid in (0, USER_ID):
            rows = self.conn.execute(
                "SELECT `key`, `value` FROM settings WHERE user_id=?", (uid,)
            ).fetchall()
            for r in rows:
                v = r["value"]
                if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
                    try:
                        out[r["key"]] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        out[r["key"]] = v
                else:
                    out[r["key"]] = v
        return out

    def get_draft(self, draft_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return None
        return self._row_to_draft(row)

    def _row_to_draft(self, row) -> dict:
        dimg_rows = self.conn.execute(
            "SELECT url, type FROM draft_images WHERE draft_id=? ORDER BY position",
            (row["id"],),
        ).fetchall()
        images = [r["url"] for r in dimg_rows]
        image_types = {r["url"]: r["type"] for r in dimg_rows if r["type"]}
        source_raw = loads_json(row["source_raw_json"], {}) if "source_raw_json" in row.keys() else {}
        if image_types:
            source_raw["image_types"] = image_types
        elif "image_types" not in source_raw:
            source_raw["image_types"] = {}
        return {
            "id": row["id"],
            "source_platform": row["source_platform"],
            "source_url": row["source_url"],
            "source_title": row["source_title"],
            "ozon_title": row["ozon_title"],
            "description": row["description"],
            "category_id": row["category_id"],
            "type_id": row["type_id"] if "type_id" in row.keys() else "",
            "images": images,
            "source_raw": source_raw,
            "images_json": loads_json(row["images_json"], []) if "images_json" in row.keys() else [],
        }

    def add_draft_image(self, draft_id: int, url: str, *, type: str = "",
                        source: str = "generated") -> int:
        now = utc_now_iso()
        row = self.conn.execute(
            "SELECT GREATEST(IFNULL(MAX(position), -1), -1) + 1 AS next_pos"
            " FROM draft_images WHERE draft_id=?",
            (draft_id,),
        ).fetchone()
        pos = int(row["next_pos"]) if row else 0
        cur = self.conn.execute(
            "INSERT INTO draft_images (draft_id, position, url, type, source, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (draft_id, pos, str(url), str(type or ""), str(source), now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_gen_job(self, job_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM gen_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def update_gen_job(self, job_id: int, patch: dict) -> dict | None:
        keys = [k for k in patch if k != "id"]
        if not keys:
            return self.get_gen_job(job_id)
        now = utc_now_iso()
        sets = [f"{k}=?" for k in keys]
        vals = [patch[k] for k in keys]
        sets.append("updated_at=?")
        vals.append(now)
        vals.append(job_id)
        self.conn.execute(f"UPDATE gen_jobs SET {', '.join(sets)} WHERE id=?", tuple(vals))
        self.conn.commit()
        return self.get_gen_job(job_id)

    def set_gen_job_status(self, job_id: int, status: str) -> None:
        self.conn.execute("UPDATE gen_jobs SET status=?, updated_at=? WHERE id=?",
                          (str(status), utc_now_iso(), job_id))
        self.conn.commit()

    def create_gen_job_images(self, job_id: int, slots: list[dict]) -> None:
        now = utc_now_iso()
        for s in slots:
            self.conn.execute(
                "INSERT INTO gen_job_images (job_id, slot_id, label, status, updated_at)"
                " VALUES (?,?,?,?,?)",
                (job_id, str(s.get("slot_id") or ""), str(s.get("label") or ""), "pending", now),
            )
        self.conn.commit()

    def get_gen_job_images(self, job_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM gen_job_images WHERE job_id=? ORDER BY id ASC", (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def set_gen_job_image_status(self, image_id: int, status: str, url: str | None = None,
                                 error: str | None = None) -> None:
        now = utc_now_iso()
        self.conn.execute(
            "UPDATE gen_job_images SET status=?, url=?, error=?, updated_at=? WHERE id=?",
            (str(status), url or None, error or None, now, image_id),
        )
        self.conn.commit()

    def count_gen_job_images_by_status(self, job_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) c FROM gen_job_images WHERE job_id=? GROUP BY status",
            (job_id,),
        ).fetchall()
        counts: dict[str, int] = {}
        for r in rows:
            counts[str(r["status"])] = int(r["c"])
        return counts
```

- [ ] **Step 4: 导入冒烟**

Run:
```bash
cd /e/personal/ozon-helper && uv run python -c "import ozon_common.jsonio, ozon_common.settings, ozon_common.draft_images; from ozon_common.settings import ai_config, oss_config; from ozon_common.draft_images import DataStore; print('ozon_common kernel ok')"
```
Expected: `ozon_common kernel ok`。

- [ ] **Step 5: ruff + 提交**

```bash
cd /e/personal/ozon-helper && python -m ruff check --select I --fix packages/ozon_common && git add -A && git commit -m "refactor(common): 抽出 store 内核 jsonio/settings/draft_images

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `ozon_api` 包化

**Files:**
- Move: `ozon_api/` → `packages/ozon_api/src/ozon_api/`
- Create: `packages/ozon_api/pyproject.toml`

- [ ] **Step 1: git mv 整个 ozon_api**

Run:
```bash
cd /e/personal/ozon-helper
mkdir -p packages/ozon_api/src
git mv ozon_api packages/ozon_api/src/ozon_api
ls packages/ozon_api/src/ozon_api | head
```
Expected: 列出 `client.py copy_flow.py ... __init__.py tests`。

- [ ] **Step 2: 写 pyproject(依赖按 ozon_api 实际所需)**

先看它依赖什么:
```bash
cd /e/personal/ozon-helper && grep -rhoE "^(import |from )[a-zA-Z0-9_]+" packages/ozon_api/src/ozon_api/*.py | sort -u | head -40
```
据结果(已知用到 requests/openai 等三方库)写 Create `packages/ozon_api/pyproject.toml`:
```toml
[project]
name = "ozon-api"
version = "0.1.0"
description = "Ozon Seller API 客户端与选品/定价流"
requires-python = ">=3.10"
dependencies = [
    # 按 Step 2 grep 结果补齐三方依赖,例如:
    # "requests>=2.31",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
(把 grep 出的非标准库三方包逐一加入 dependencies。标准库不写。)

- [ ] **Step 3: ozon_api 内部导入自检**

Run:
```bash
cd /e/personal/ozon-helper && grep -rnE "from ozon_api|import ozon_api|from \." packages/ozon_api/src/ozon_api/*.py | head
```
内部互引若是 `from ozon_api.client import` 形式可保留(包名没变)。确认无 `from backend`/`from ozon-listing-webui` 之类跨包引用。

- [ ] **Step 4: 冒烟 + 提交**

Run:
```bash
cd /e/personal/ozon-helper && uv sync 2>&1 | tail -2 && uv run python -c "import ozon_api; from ozon_api.client import OzonSellerClient; print('ozon_api ok')"
```
Expected: `ozon_api ok`。
```bash
git add -A && git commit -m "refactor(api): ozon_api 包化迁入 packages/ozon_api

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `webui` app —— 迁移 + 重命名 + 重接共享导入

**Files:**
- Move: `ozon-listing-webui/backend/` → `apps/webui/src/webui/`
- Move: `ozon-listing-webui/run_api.py` → `apps/webui/src/webui/server.py`
- Move: `ozon-listing-webui/tests/` → `apps/webui/tests/`
- Create: `apps/webui/pyproject.toml`
- Modify: 全量 `backend.` → `webui.`;共享模块导入 → `ozon_common.`/`ozon_api.`

> 注意:此 Task 改动面最大,务必每步后跑基线测试。`backend/{db,oss,mq,gen_image,image_plan}.py` 已在 Task 2 移走,此处 `backend/` 不再含这 5 个文件。

- [ ] **Step 1: 物理迁移目录**

Run:
```bash
cd /e/personal/ozon-helper
mkdir -p apps/webui/src
git mv ozon-listing-webui/backend apps/webui/src/webui
git mv ozon-listing-webui/run_api.py apps/webui/src/webui/server.py
git mv ozon-listing-webui/tests apps/webui/tests
ls apps/webui/src/webui | head
```
Expected: 列出 `main.py app_service.py store.py ... server.py __init__.py`。

- [ ] **Step 2: 重接「共享基础设施」导入到 ozon_common**

webui 内原来 `from backend.{db,oss,mq,gen_image,image_plan} import` 现在要指向 `ozon_common`:
```bash
cd /e/personal/ozon-helper
FILES=$(git ls-files 'apps/webui/src/webui/*.py' 'apps/webui/tests/*.py')
for m in db oss mq gen_image image_plan; do
  sed -i "s/from backend\.$m import/from ozon_common.$m import/g; s/from backend\.$m/from ozon_common.$m/g; s/import backend\.$m\b/import ozon_common.$m/g" $FILES
done
grep -rn "backend\.\(db\|oss\|mq\|gen_image\|image_plan\)" apps/webui || echo "共享基础设施导入已全部重接 ✓"
```

- [ ] **Step 3: 重接「store 内核」到 ozon_common(去 webui 内部重复)**

`backend/drafts.py`、`backend/settings_migrate.py` 各自定义了 `ai_config/oss_config/utc_now_iso/dumps_json/loads_json` 的本地副本。删除这些本地 def,改为从 ozon_common 导入。对这两个文件(现位于 `apps/webui/src/webui/{drafts,settings_migrate}.py`)操作:
1. 删除其中 `def ai_config`/`def oss_config`/`def _ai_platforms`/`def utc_now_iso`/`def dumps_json`/`def loads_json` 及 `_KIND_ENGINE` 的本地定义。
2. 在文件顶部 import 区加:
   ```python
   from ozon_common.jsonio import utc_now_iso, dumps_json, loads_json
   from ozon_common.settings import ai_config, oss_config
   ```
   (只导入该文件实际用到的名字。)

验证两文件不再本地定义这些符号:
```bash
cd /e/personal/ozon-helper && grep -nE "def (ai_config|oss_config|utc_now_iso|dumps_json|loads_json|_ai_platforms)\b" apps/webui/src/webui/drafts.py apps/webui/src/webui/settings_migrate.py || echo "本地副本已清除 ✓"
```
> 风险点:若 webui 旧本地实现与 ozon_common 版行为有差异,基线测试(`test_settings_migrate.py`/`test_drafts.py` 等)会暴露。出现 fail 时,以 ozon_common 版为准修正调用处,或在 ozon_common 版兼容旧行为(记录差异,勿静默)。

- [ ] **Step 4: 全量重命名 `backend` → `webui`**

```bash
cd /e/personal/ozon-helper
FILES=$(git ls-files 'apps/webui/src/webui/*.py' 'apps/webui/tests/*.py')
sed -i -E "s/\bfrom backend\./from webui./g; s/\bfrom backend import\b/from webui import/g; s/\bimport backend\.([a-z_]+)/import webui.\1/g; s/\bimport backend as\b/import webui as/g; s/^import backend$/import webui/g" $FILES
# server.py 里的 uvicorn 字符串引用
sed -i 's/"backend\.main:app"/"webui.main:app"/g' apps/webui/src/webui/server.py
grep -rn "\bbackend\b" apps/webui/src/webui apps/webui/tests | grep -vE "#|\"|'" | head
```
Expected: 末尾 grep 无 Python 代码层面的 `backend` 残留(注释/字符串里的中文「后端」不算)。逐条核对剩余命中。

- [ ] **Step 5: 写 webui 的 pyproject + 入口**

Create `apps/webui/pyproject.toml`:
```toml
[project]
name = "ozon-webui"
version = "0.1.0"
description = "Ozon 上品助手 Web 后端"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    "python-multipart>=0.0.9",
    "openpyxl>=3.1",
    "pillow>=10.0",
    "ozon-common",
    "ozon-api",
]

[project.scripts]
ozon-webui = "webui.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
确认 `server.py` 仍有 `def main()` 与 `if __name__ == "__main__": raise SystemExit(main())`(原 run_api.py 已有)。`server.py` 内原来 `ROOT = Path(__file__).resolve().parent` + `sys.path.insert` 的端口探测逻辑保留;由于改为包安装,`sys.path` 注入可删可留(留着无害)。

- [ ] **Step 6: 处理 webui 包内资源路径**

`app_service.py` 里有 `FRONTEND_DIST` 等基于 `__file__` 的路径常量,原来相对 `backend/` 定位 `frontend/dist`、`assets/`、`data/`。迁移后包根变为 `apps/webui/src/webui/`,而 `frontend/`、`data/` 将在 Task 7 落到 `apps/webui/`。检查并修正这些路径常量:
```bash
cd /e/personal/ozon-helper && grep -rnE "Path\(__file__\)|FRONTEND_DIST|/ \"assets\"|/ \"data\"|parent\.parent" apps/webui/src/webui/app_service.py apps/webui/src/webui/main.py | head
```
按新布局调整(例如 `frontend/dist` 从 `webui` 包向上到 `apps/webui/frontend/dist`:`Path(__file__).resolve().parents[2] / "frontend" / "dist"`)。`assets/` 若随包走(在 `webui/assets`)则用 `Path(__file__).resolve().parent / "assets"`。

- [ ] **Step 7: 基线测试(配置 pytest 能找到 webui 包)**

uv 环境下 webui 已 editable 安装,测试用 `from webui.x` 可解析。Run:
```bash
cd /e/personal/ozon-helper && uv run python -m pytest apps/webui/tests -q --ignore-glob='*_live.py' -p no:cacheprovider 2>&1 | tail -8
```
Expected: 通过数 ≥ Task 0 记录的基线 NNN(不下降)。出现 fail 按 Step 3/Step 6 风险点定位修正。

- [ ] **Step 8: ruff + 提交**

```bash
cd /e/personal/ozon-helper && python -m ruff check --select I --fix apps/webui && git add -A && git commit -m "refactor(webui): 迁入 apps/webui + backend→webui 重命名 + 重接 ozon_common/ozon_api

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `image_worker` app —— 删副本 + 重接导入

**Files:**
- Move: `ozon-image-worker/worker.py` → `apps/image_worker/src/image_worker/worker.py`
- Delete: `ozon-image-worker/{db,oss,mq,gen_image,image_plan,store}.py`
- Create: `apps/image_worker/pyproject.toml`、`apps/image_worker/src/image_worker/__init__.py`

- [ ] **Step 1: 建包 + 迁 worker.py**

Run:
```bash
cd /e/personal/ozon-helper
mkdir -p apps/image_worker/src/image_worker
printf '"""Ozon AI 出图 worker。"""\n' > apps/image_worker/src/image_worker/__init__.py
git mv ozon-image-worker/worker.py apps/image_worker/src/image_worker/worker.py
```

- [ ] **Step 2: 删除 6 个复制模块**

Run:
```bash
cd /e/personal/ozon-helper
for m in db oss mq gen_image image_plan store; do git rm ozon-image-worker/$m.py; done
ls ozon-image-worker
```
Expected: `ozon-image-worker/` 现仅剩 `Dockerfile requirements.txt __pycache__`(requirements/Dockerfile 在 Task 7 处理或迁移)。

- [ ] **Step 3: 重接 worker.py 导入到 ozon_common**

worker.py 原导入(平级裸导入):
```python
from gen_image import (...)
from image_plan import build_image_plan
from mq import consume_gen_jobs
from oss import OssClient
from store import DataStore, ai_config, oss_config
```
改为:
```bash
cd /e/personal/ozon-helper
W=apps/image_worker/src/image_worker/worker.py
sed -i -E \
  -e "s/^from gen_image import/from ozon_common.gen_image import/" \
  -e "s/^from image_plan import/from ozon_common.image_plan import/" \
  -e "s/^from mq import/from ozon_common.mq import/" \
  -e "s/^from oss import/from ozon_common.oss import/" \
  $W
```
`store` 那行要拆分(DataStore 来自 draft_images,ai_config/oss_config 来自 settings)。手动把:
```python
from store import DataStore, ai_config, oss_config
```
改为:
```python
from ozon_common.draft_images import DataStore
from ozon_common.settings import ai_config, oss_config
```
验证无裸导入残留:
```bash
grep -nE "^from (gen_image|image_plan|mq|oss|store|db) import" $W || echo "worker 导入已全部重接 ✓"
```

- [ ] **Step 4: 写 image_worker 的 pyproject + 入口**

Create `apps/image_worker/pyproject.toml`:
```toml
[project]
name = "ozon-image-worker"
version = "0.1.0"
description = "Ozon AI 出图 worker(消费 RabbitMQ → 出图 → OSS)"
requires-python = ">=3.10"
dependencies = [
    "ozon-common",
]

[project.scripts]
ozon-worker = "image_worker.worker:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
(worker 只依赖 ozon-common,pika/pymysql/oss2/openai 由 ozon-common 透传。)

- [ ] **Step 5: 导入冒烟**

Run:
```bash
cd /e/personal/ozon-helper && uv sync 2>&1 | tail -2 && uv run --package ozon-image-worker python -c "import image_worker.worker; print('worker import ok')"
```
Expected: `worker import ok`(import 阶段不连 MySQL/MQ;`main()` 才连,故 import 应成功)。

- [ ] **Step 6: ruff + 提交**

```bash
cd /e/personal/ozon-helper && python -m ruff check --select I --fix apps/image_worker && git add -A && git commit -m "refactor(worker): 删 6 个复制模块,导入改 ozon_common,迁入 apps/image_worker

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 资产/配置迁移 + Docker + 收尾验证

**Files:**
- Move: `ozon-listing-webui/{frontend,deploy,data,scripts,启动后端.bat,README.md,requirements.txt}` → `apps/webui/`
- Move: 散落游离脚本 `ozon-listing-webui/{fetch_*,compare_listings,grab_ozon_video}.py` → `apps/webui/scripts/`
- Modify: 根 `Dockerfile`、新 `apps/image_worker/Dockerfile`、`apps/webui/启动后端.bat`
- Delete: 空壳 `ozon-listing-webui/`、`ozon-image-worker/`(若已空)

- [ ] **Step 1: 迁移 webui 资产目录**

Run:
```bash
cd /e/personal/ozon-helper
for d in frontend deploy data scripts; do
  [ -e ozon-listing-webui/$d ] && git mv ozon-listing-webui/$d apps/webui/$d
done
for f in 启动后端.bat README.md requirements.txt; do
  [ -e ozon-listing-webui/$f ] && git mv "ozon-listing-webui/$f" "apps/webui/$f"
done
# 游离脚本归入 scripts/
mkdir -p apps/webui/scripts
for f in $(git ls-files 'ozon-listing-webui/*.py'); do git mv "$f" "apps/webui/scripts/$(basename $f)"; done
ls ozon-listing-webui 2>/dev/null || echo "ozon-listing-webui 已空"
```
> 注:`data/` 已被 .gitignore(运行时数据),`git mv` 可能只动被跟踪部分;未跟踪的 `data/` 内容用普通 `mv` 补迁:`[ -d ozon-listing-webui/data ] && mv ozon-listing-webui/data/* apps/webui/data/ 2>/dev/null`。`scratch/`(已忽略)同理按需 `mv`。

- [ ] **Step 2: 清理空壳目录**

Run:
```bash
cd /e/personal/ozon-helper
rmdir ozon-listing-webui 2>/dev/null; rmdir ozon-image-worker 2>/dev/null
# 若非空,列出残留人工确认
[ -d ozon-listing-webui ] && echo "残留:" && ls -A ozon-listing-webui
[ -d ozon-image-worker ] && echo "残留:" && ls -A ozon-image-worker
```
残留若是 `__pycache__`/`.venv`/被忽略物,直接删:`rm -rf ozon-listing-webui ozon-image-worker`(确认无被跟踪文件后)。同时删掉 Task 0 之前各自建的旧 `.venv`(已被根 venv 取代)。

- [ ] **Step 3: 校准前端构建路径引用**

`apps/webui/frontend/vite.config.js` 等若硬编码了后端路径/代理目标,核对:
```bash
cd /e/personal/ozon-helper && grep -rnE "backend|ozon-listing-webui|\.\./" apps/webui/frontend/vite.config.js apps/webui/frontend/package.json 2>/dev/null | head
```
代理目标是 `127.0.0.1:<port>` 一般无需改;若有相对路径指向后端源码则修正。

- [ ] **Step 4: 重写 worker Dockerfile(uv 多阶段,上下文=仓库根)**

Create `apps/image_worker/Dockerfile`:
```dockerfile
# 构建上下文 = 仓库根(需带上 packages/ozon_common)
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
WORKDIR /app

# 先拷清单装依赖(利用层缓存)
COPY pyproject.toml uv.lock ./
COPY packages/ozon_common/pyproject.toml packages/ozon_common/
COPY apps/image_worker/pyproject.toml apps/image_worker/
RUN uv sync --package ozon-image-worker --no-dev --frozen --no-install-project

# 再拷源码
COPY packages/ozon_common packages/ozon_common
COPY apps/image_worker apps/image_worker
RUN uv sync --package ozon-image-worker --no-dev --frozen

CMD ["uv", "run", "--package", "ozon-image-worker", "ozon-worker"]
```

- [ ] **Step 5: 重写根 Dockerfile(webui,uv,上下文=仓库根)**

Modify 根 `Dockerfile` 为:
```dockerfile
# Ozon 上品助手 webui 镜像。构建上下文 = 仓库根。
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    WEBUI_HOST=0.0.0.0 \
    WEBUI_PORT=8585
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/ozon_common/pyproject.toml packages/ozon_common/
COPY packages/ozon_api/pyproject.toml packages/ozon_api/
COPY apps/webui/pyproject.toml apps/webui/
RUN uv sync --package ozon-webui --no-dev --frozen --no-install-project

COPY packages packages
COPY apps/webui apps/webui
RUN uv sync --package ozon-webui --no-dev --frozen

EXPOSE 8585
CMD ["uv", "run", "--package", "ozon-webui", "ozon-webui"]
```
(前端 dist 须已本地构建好,随 `apps/webui/frontend` 进镜像。)

- [ ] **Step 6: 改启动脚本**

`apps/webui/启动后端.bat` 内容改为(保留中文提示):
```bat
@echo off
cd /d %~dp0..\..
uv run ozon-webui %*
```
(`.bat` 在 `apps/webui/`,`..\..` 回到仓库根再 `uv run`。)

- [ ] **Step 7: 全仓收尾验证**

Run(逐条):
```bash
cd /e/personal/ozon-helper
uv sync 2>&1 | tail -2
uv run python -m pytest apps/webui/tests -q --ignore-glob='*_live.py' -p no:cacheprovider 2>&1 | tail -6
uv run python -c "import webui.main, image_worker.worker, ozon_api.client; print('all imports ok')"
python -m ruff check --select I packages apps 2>&1 | tail -3
```
Expected:
- pytest 通过数 ≥ 基线 NNN;
- `all imports ok`;
- ruff `All checks passed!`。

- [ ] **Step 8: worker 镜像精简校验(确认不含 fastapi)**

Run:
```bash
cd /e/personal/ozon-helper && uv run --package ozon-image-worker python -c "import importlib.util as u; print('fastapi present:', u.find_spec('fastapi') is not None)"
```
说明:根单一 venv 里 fastapi 是存在的(webui 也在同环境)。此步仅逻辑校验 worker 依赖闭包;真实精简由 Docker 的 `--package ozon-image-worker` 解析保证。可选:`docker build -f apps/image_worker/Dockerfile -t ozon-worker-test .` 后 `docker run --rm ozon-worker-test python -c "import importlib.util as u; print(u.find_spec('fastapi'))"` 应为 `None`。

- [ ] **Step 9: 更新文档与提交**

更新根 `README.md`(或新建)简述新结构与跑法:`uv sync`、`uv run ozon-webui`、`uv run ozon-worker`。然后:
```bash
cd /e/personal/ozon-helper && git add -A && git commit -m "build: 迁移 webui 资产 + 重写 Docker(uv)+ 启动脚本,完成 monorepo 重构

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 10: 更新 memory(可选)**

把「项目已迁为 uv workspace 四包结构、跑法 uv run ozon-webui/ozon-worker」更新进 `MEMORY.md` 相关条目(如 `mysql-docker-deploy.md` 的部署步骤涉及路径,需同步)。

---

## Self-Review 记录

- **Spec 覆盖**:§3 四包结构→Task 1/2/4/5/6;§4 共享边界→Task 2(基础设施)+Task 3(内核)+Task 5 Step 3(webui 去重),并显式记录「webui Store 不收敛」的精化;§5 入口→Task 5 Step 5、Task 6 Step 4;§6 单一 venv→Task 2 Step 6;§7 Docker→Task 7 Step 4/5;§8 迁移步骤→Task 0–7 一一对应;§9 验证闸门→各 Task 的基线测试/冒烟/ruff。
- **占位符**:无 TBD/TODO;ozon_api 依赖列表需 Task 4 Step 2 用 grep 结果补齐(已给出方法,非占位)。
- **签名一致性**:`make_conn`(ozon_common.db 别名)与 worker 用法一致;`consume_gen_jobs` 统一 4 参;`DataStore`/`ai_config`/`oss_config` 命名贯穿 Task 3/6 一致。
- **已知风险**:webui `drafts.py`/`settings_migrate.py` 旧本地 helper 若与 ozon_common 版有行为差→Task 5 Step 3 由基线测试兜底;app_service 资源路径→Task 5 Step 6 专项校准。
