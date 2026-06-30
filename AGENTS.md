# Repository Guidelines

## Project Structure & Module Organization

This is a **uv workspace monorepo**. `apps/webui/` is the FastAPI + Vue application: backend code in `src/webui/` (`main.py` = assembly + `routers/`; `app_service.py` = thin `App` facade composing `services/` domain mixins), frontend in `frontend/src/`, deploy notes in `deploy/`, Python tests in `tests/`. `apps/image_worker/` is the AI image-generation worker. `packages/ozon_common/` holds the data layer (SQLAlchemy Core + Repository/UoW + Alembic) and shared infra; `packages/ozon_api/` is the Ozon Seller API client. `ozon-seller-helper-ext/` is the Chromium MV3 extension (`common/` parsing, `content/`, `popup/`, Vitest `tests/`). `docs/` holds specs/plans and product docs; avoid committing generated output or private data.

## Build, Test, and Development Commands

`uv` may not be on PATH — use `python -m uv`. From the repo root:

```bash
python -m uv sync                                              # install workspace
python -m uv run --package ozon-webui ozon-webui              # run backend (auto port / 8585)
python -m uv run python -m pytest apps/webui/tests packages --ignore-glob='*_live.py' -q   # backend tests (714)
```

Run the Vue app from `apps/webui/frontend/`:

```bash
npm install
npm run dev      # vite dev (proxy /api, /media to backend)
npm run build    # produces dist/ (served by FastAPI)
npm run test     # vitest
```

Run extension tests from `ozon-seller-helper-ext/` with `npm test`. Deploy (Docker + MySQL) per `apps/webui/deploy/DEPLOY.md` — **run Alembic migrations on existing MySQL before deploying** (`create_all` adds tables, not columns).

## Coding Style & Naming Conventions

Use existing local style. Python modules and tests use `snake_case`; JavaScript files use lower-case descriptive names such as `parse-1688.js`, while Vue components should remain `PascalCase.vue`. Prefer small, focused functions near related domain code. Keep user-facing Chinese text intact, and use clear English identifiers for code, commands, and environment variables.

## Testing Guidelines

Name Python tests `test_*.py` and JavaScript tests `*.test.js`. Place fixtures under the nearest `tests/fixtures/` directory. Add or update targeted tests for API behavior, parser changes, pricing/listing logic, extension bridge behavior, and frontend state utilities. Smoke tests named `smoke_*_live.py` may require external credentials or live services; do not treat them as default offline checks.

## Commit & Pull Request Guidelines

Git history follows Conventional Commit-style messages with scopes, for example `feat(ext): ...`, `fix(app): ...`, and `docs(spec): ...`. Keep commits focused and mention the affected area (`app`, `ext`, `api`, or `spec`). Pull requests should include a summary, test commands run, linked issue or spec when relevant, screenshots for UI changes, and notes about migrations, credentials, or data-file impacts.

## Security & Configuration Tips

Do not commit Ozon API keys, cookies, seller credentials, database snapshots, or generated archives. Treat `products.db`, `ozon-listing-webui/data/`, local `_*.json`, and captured HTML files as sensitive unless explicitly sanitized. Prefer environment variables for secrets and document required values in deployment notes rather than source files.
