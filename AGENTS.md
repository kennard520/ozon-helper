# Repository Guidelines

## Project Structure & Module Organization

This is a **uv workspace monorepo**. `apps/webui/` is the FastAPI + Vue application: backend code in `src/webui/` (`main.py` = assembly + `routers/`; `app_service.py` = thin `App` facade composing `services/` domain mixins), frontend in `frontend/src/`, deploy notes in `deploy/`, Python tests in `tests/`. `apps/image_worker/` is the AI image-generation worker. `packages/ozon_common/` holds the data layer (SQLAlchemy Core + Repository/UoW + Alembic) and shared infra; `packages/ozon_api/` is the Ozon Seller API client. The full upstream Ozon Seller API OpenAPI 3.0 spec (v2.1, 483 paths, ~2300 schemas) is vendored at `ozon-seller-api-openapi.json` at the repo root — refresh it from https://docs.ozon.ru/api/seller/swagger.json (requires a real browser to pass Ozon's antibot JS challenge). `ozon-seller-helper-ext/` is the Chromium MV3 extension (`common/` parsing, `content/`, `popup/`, Vitest `tests/`). `docs/` holds specs/plans and product docs; avoid committing generated output or private data.

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
## Skill Usage Guide

Project-specific Skills live in .agents/skills/ (scout, ozon-profit-calculator, ozon-card, ozon-desc, ozon-product-kit, ozon-stats, oss-upload, ozon-help-sync, ozon-skill-router). For any Ozon business task, route global Doubao Skills per .agents/skills/ozon-skill-router/SKILL.md (e.g. sheet for CSV/report work, doubao-data-analysis for metric attribution, doubao-visualization for charts, doubao-creative-design for product images). Full integration matrix: docs/skill-integration.md. Note: profit calculation covers Ozon commission + logistics only — do not attach tax/compliance Skills.

## Ozon Scraping / Anti-bot Notes

Ozon product HTML pages block plain HTTP clients (requests / Invoke-WebRequest) with 403 at the TLS-fingerprint level -- adding Chrome headers or pre-warming cookies does **not** help. Use the project-venv stealth browser instead:

```python
from cloakbrowser import launch_persistent_context
ctx = launch_persistent_context(
    user_data_dir=r"packages/ozon_api/src/ozon_api/data/.auth/ozon_profile",
    headless=True, locale="ru-RU", timezone="Europe/Moscow",
)
page = ctx.pages[0] if ctx.pages else ctx.new_page()
page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
# scroll to lazy-load images, then page.content()
```

Reusing the same `user_data_dir` persists antibot cookies across runs. After you have the HTML, product images live on `ir-*.ozonstatic.cn/s3/multimedia-*/wc{width}/{id}.jpg` (**not** `cdn*.ozone.ru`) -- the image CDN is public and downloadable with plain `requests` once you have the URL. Reference script: `packages/ozon_api/src/ozon_api/competition_probe.py`. Never commit scraped competitor HTML or image dumps; treat them as throwaway intermediates under `picks_output/`.
