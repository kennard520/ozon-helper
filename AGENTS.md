# AGENTS.md

This file provides guidance to Qoder (qoder.com) when working with code in this repository.

## Build, Test, and Development Commands

`uv` may not be on PATH — always use `python -m uv`. From the repo root:

```bash
python -m uv sync                                                          # install workspace
python -m uv run --package ozon-webui ozon-webui                           # run backend (auto port / 8585)
python -m uv run --package ozon-mcp ozon-mcp                              # run MCP server (port 8586)
python -m uv run --package ozon-image-worker ozon-worker                   # run image worker (needs RabbitMQ)
python -m uv run python -m pytest apps/webui/tests packages --ignore-glob='*_live.py' -q   # all backend tests
python -m uv run python -m pytest apps/webui/tests/test_drafts.py -q      # single test file
python -m uv run python -m pytest apps/webui/tests/test_drafts.py::test_name -q            # single test
python -m uv run python -m pytest apps/webui/tests packages -k "keyword" -q               # filter by keyword
```

Frontend (`apps/webui/frontend/`):

```bash
npm install
npm run dev      # vite dev server (proxy /api, /media to backend)
npm run build    # produces dist/ (served by FastAPI as SPA)
npm run test     # vitest
```

Extension tests: `cd ozon-seller-helper-ext && npm test` (Vitest).

Quick local start (Windows): `.\start-local.ps1` — loads `.env.local`, syncs deps, builds frontend if missing, starts backend.

Alembic migrations (MySQL only, requires `OZON_MYSQL_*` env vars):

```bash
python -m uv run alembic upgrade head          # apply migrations
python -m uv run alembic revision --autogenerate -m "description"   # generate new migration
```

**Deploy**: run Alembic migrations on existing MySQL before deploying — `create_all` adds tables, not columns. See `apps/webui/deploy/DEPLOY.md`.

## Architecture

This is a **uv workspace monorepo** with 4 Python packages + 1 browser extension + 1 Vue frontend:

| Package | Path | Role |
|---|---|---|
| `ozon-webui` | `apps/webui/` | FastAPI backend + Vue3 SPA (main application) |
| `ozon-mcp` | `apps/mcp_server/` | MCP server (streamable-HTTP, port 8586) exposing tools for ChatGPT integration |
| `ozon-image-worker` | `apps/image_worker/` | RabbitMQ consumer: AI image generation → OSS upload → DB update |
| `ozon-common` | `packages/ozon_common/` | Shared kernel: DAL (SQLAlchemy Core + Repository), OSS, MQ, gen_image, text_pipeline |
| `ozon-api` | `packages/ozon_api/` | Ozon Seller API client, pricing/filtering flows, competition probes |
| Extension | `ozon-seller-helper-ext/` | Chromium MV3: in-page scraping on Ozon/1688/WB/PDD, pushes parsed data to backend |

### Backend Application Layer (`apps/webui/src/webui/`)

The backend uses a **Mixin Facade** pattern (result of strangling a former god-class):

- `main.py` — assembles FastAPI app, middleware (CORS for chrome-extension, user-context ContextVar, request-scoped DB session), includes routers, mounts SPA static files.
- `app_service.py` — `class App(AuthMixin, SettingsMixin, CategoryMixin, DraftMixin, PublishMixin, AiCardMixin, AiImageMixin, AiVideoMixin, GalleryMixin, ExtMixin, GenJobMixin, PricingMixin, WarehouseMixin, TextJobMixin, PipelineMixin)`. Thin facade: only `__init__` (creates Store, Catalog) + re-exports.
- `services/_*.py` — domain logic lives in these mixins. Cross-domain calls via `self.` (same instance).
- `routers/*.py` — thin APIRouter endpoints that delegate to `app_instance.APP.<method>()`.
- `app_instance.py` — holds the `APP` singleton. **Routers must use `app_instance.APP` (live attribute lookup), never `from webui.app_instance import APP`** (import-time binding breaks on test reload).

**Monkeypatch compatibility**: mixins call patchable module-level names (`build_client`, `publish_items`, `OssClient`, etc.) via `import webui.app_service as _app_svc; _app_svc.X(...)` so tests can `monkeypatch.setattr("webui.app_service.X", ...)`.

**Adding code**: new endpoint → add to domain router (or new `routers/<domain>.py` + `main.py` include). New business logic → add to corresponding mixin in `services/`. Pure helpers → `services/_helpers.py`.

### Data Access Layer (`packages/ozon_common/src/ozon_common/dal/`)

- `schema.py` — all tables as SQLAlchemy Core `Table` objects (no ORM models). Fidelity guarded by `test_schema_fidelity.py`.
- `engine.py` — engine factory: uses MySQL if `OZON_MYSQL_HOST` env is set, otherwise SQLite (WAL mode).
- `session.py` — request-scoped session via ContextVar + `session_scope()` context manager. HTTP middleware opens/closes per request; non-request contexts (tests, worker) self-open via `_in_scope()` in Store.
- `repositories/` — Repository pattern (one per aggregate: `draft_repo`, `gen_job_repo`, `wallet_repo`, etc.). Repos use `current_session()` from the ambient ContextVar.

### Store (`apps/webui/src/webui/store.py`)

`Store` is the legacy data-access facade used by App mixins. It delegates to DAL repositories via lazy-import helpers (`_draft_repo()`, `_gen_job_repo()`, etc.) and wraps them in `_in_scope()` for session management. Multi-user isolation via `current_user_id` ContextVar (set by HTTP middleware from JWT).

### Image Worker (`apps/image_worker/`)

Consumes jobs from RabbitMQ (`ozon_common.mq.consume_gen_jobs`), builds an image plan per draft, generates images concurrently (ThreadPoolExecutor, `GEN_CONCURRENCY`), uploads to OSS, writes results to `draft_images` table. Also has `text_worker.py` for AI text generation jobs.

### Browser Extension (`ozon-seller-helper-ext/`)

MV3, no build step (plain JS). Content scripts parse product pages (1688, Ozon, WB, PDD) in-page and push structured data to backend via `POST /api/ext/collect-parsed`. `common/bridge.js` discovers backend on `127.0.0.1` candidate ports. `background.js` handles alarms, badge, and message routing.

### Frontend (`apps/webui/frontend/`)

Vue 3 + Pinia + Vue Router + Element Plus. Built with Vite; `dist/` is served by FastAPI as SPA catch-all. Key stores: `stores/workbench.js` (draft editing state machine), `stores/app.js` (global settings/auth). Composables in `composables/` (pipeline, batch ops, analytics, attributes).

## Coding Style & Naming Conventions

Python: `snake_case` modules/tests, line-length 120, ruff with isort (`known-first-party = ozon_common, ozon_api, webui, image_worker, ozon_mcp`). JavaScript: lower-case descriptive (`parse-1688.js`). Vue components: `PascalCase.vue`. Keep user-facing Chinese text intact; use English identifiers for code.

## Testing Guidelines

Name Python tests `test_*.py`, JS tests `*.test.js`. Fixtures under nearest `tests/fixtures/`. Smoke tests (`smoke_*_live.py`) require live credentials — exclude from default runs (`--ignore-glob='*_live.py'`).

## Product Documentation

Each functional module has a living doc in `docs/product/<module>.md` (workbench, analytics, fulfillment, stores, warehouses, material-gallery, performance-api). **Any feature change must update the corresponding doc in the same commit.** These are "current truth" docs, distinct from one-time specs in `docs/superpowers/`.

## Commit & Pull Request Guidelines

Conventional Commits with scopes: `feat(app):`, `fix(ext):`, `docs(spec):`. Scopes: `app`, `ext`, `api`, `spec`. PRs: summary, test commands run, screenshots for UI changes, migration/credential notes.

## Security & Configuration

Do not commit Ozon API keys, cookies, seller credentials, database snapshots, or generated archives. Treat `products.db`, `ozon-listing-webui/data/`, local `_*.json`, and captured HTML as sensitive. Secrets via environment variables; document required values in deploy notes.
