# Repository Guidelines

## Project Structure & Module Organization

This repository contains an Ozon listing helper split into three parts. `ozon-listing-webui/` is the FastAPI + Vue application: backend code lives in `backend/`, frontend code in `frontend/src/`, deployment notes in `deploy/`, scripts in `scripts/`, and Python tests in `tests/`. `ozon-seller-helper-ext/` is the Chromium MV3 extension, with shared parsing and bridge logic in `common/`, content scripts in `content/`, popup UI in `popup/`, and Vitest tests in `tests/`. `ozon_api/` is a lightweight Python Ozon Seller API client with its own `tests/`. `docs/`, `outputs/`, and local data files are supporting artifacts; avoid committing generated output or private data.

## Build, Test, and Development Commands

Run backend setup and API locally from `ozon-listing-webui/`:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
python run_api.py
```

Run the Vue app from `ozon-listing-webui/frontend/`:

```bash
npm install
npm run dev
npm run build
npm run test
```

Run extension tests from `ozon-seller-helper-ext/` with `npm test` or `npm run test:watch`. Run Python tests with `python -m unittest discover -s tests` inside `ozon-listing-webui/` or `ozon_api/`.

## Coding Style & Naming Conventions

Use existing local style. Python modules and tests use `snake_case`; JavaScript files use lower-case descriptive names such as `parse-1688.js`, while Vue components should remain `PascalCase.vue`. Prefer small, focused functions near related domain code. Keep user-facing Chinese text intact, and use clear English identifiers for code, commands, and environment variables.

## Testing Guidelines

Name Python tests `test_*.py` and JavaScript tests `*.test.js`. Place fixtures under the nearest `tests/fixtures/` directory. Add or update targeted tests for API behavior, parser changes, pricing/listing logic, extension bridge behavior, and frontend state utilities. Smoke tests named `smoke_*_live.py` may require external credentials or live services; do not treat them as default offline checks.

## Commit & Pull Request Guidelines

Git history follows Conventional Commit-style messages with scopes, for example `feat(ext): ...`, `fix(app): ...`, and `docs(spec): ...`. Keep commits focused and mention the affected area (`app`, `ext`, `api`, or `spec`). Pull requests should include a summary, test commands run, linked issue or spec when relevant, screenshots for UI changes, and notes about migrations, credentials, or data-file impacts.

## Security & Configuration Tips

Do not commit Ozon API keys, cookies, seller credentials, database snapshots, or generated archives. Treat `products.db`, `ozon-listing-webui/data/`, local `_*.json`, and captured HTML files as sensitive unless explicitly sanitized. Prefer environment variables for secrets and document required values in deployment notes rather than source files.
