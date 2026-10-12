# Performance Campaign Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent Ozon Performance “广告活动” page for viewing campaign products and running guarded batch add/remove or Search Promo enable/disable operations.

**Architecture:** Add a dedicated Performance API client, service, and FastAPI router. Add a standalone Vue route and page that calls the new endpoints, keeps write actions behind preview + confirmation, and leaves Analytics untouched.

**Tech Stack:** FastAPI, Python stdlib urllib transport, pytest, Vue 3, Vue Router, Pinia, Element Plus, Vitest.

## Global Constraints

- The page is a standalone top-level route, not a tab under Analytics.
- Performance API credentials are separate from Seller API credentials.
- Do not expose `performance_client_secret`; return only `performance_client_secret_saved`.
- Only implement two write categories: ordinary campaign product add/remove, and Search Promo product enable/disable.
- Do not implement whole-campaign activate/deactivate.
- Every write operation requires preview before commit.
- Return per item success/failure results.
- Follow existing repo style and keep existing dirty worktree changes untouched.

---

### Task 1: Settings Support For Performance Credentials

**Files:**
- Modify: `apps/webui/src/webui/services/_settings.py`
- Modify: `apps/webui/src/webui/models.py`
- Modify: `apps/webui/frontend/src/views/Settings.vue`
- Test: `apps/webui/tests/test_settings_api.py`

**Interfaces:**
- Produces settings keys: `performance_client_id`, `performance_client_secret`.
- Produces public state keys: `performance_client_id`, `performance_client_secret_saved`.

- [ ] **Step 1: Write failing backend settings test**

Add assertions to settings tests that saving `performance_client_id` and `performance_client_secret` persists them, and that `/api/state` returns `performance_client_secret_saved: true` without returning the secret.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m uv run python -m pytest apps/webui/tests/test_settings_api.py -q`

- [ ] **Step 3: Implement backend settings fields**

Add optional fields to `SettingsIn`, whitelist the two keys in `save_settings`, and expose safe state fields in `state()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m uv run python -m pytest apps/webui/tests/test_settings_api.py -q`

- [ ] **Step 5: Add frontend settings inputs**

Add Performance API section in `Settings.vue` with client id and secret inputs. Include secret only when user types a non-empty value.

### Task 2: Performance API Client

**Files:**
- Create: `packages/ozon_api/src/ozon_api/performance.py`
- Modify: `packages/ozon_api/src/ozon_api/__init__.py`
- Test: `packages/ozon_api/src/ozon_api/tests/test_performance_client.py`

**Interfaces:**
- Produces `OzonPerformanceClient(client_id, client_secret, base_url=..., timeout=..., transport=...)`.
- Produces methods: `list_campaigns()`, `campaign_products(campaign_id)`, `add_campaign_products(campaign_id, items)`, `delete_campaign_products(campaign_id, items)`, `search_promo_products(payload)`, `enable_search_promo(items)`, `disable_search_promo(items)`.

- [ ] **Step 1: Write failing client tests**

Test token request, bearer header reuse, GET query request, POST JSON request, and HTTP error propagation with a fake transport.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m uv run python -m pytest packages/ozon_api/src/ozon_api/tests/test_performance_client.py -q`

- [ ] **Step 3: Implement minimal client**

Use stdlib urllib-compatible transport shape already used by Seller client. Cache `access_token` until `expires_in - 60` seconds.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m uv run python -m pytest packages/ozon_api/src/ozon_api/tests/test_performance_client.py -q`

### Task 3: Backend Service And Router

**Files:**
- Create: `apps/webui/src/webui/services/performance_service.py`
- Create: `apps/webui/src/webui/routers/performance.py`
- Modify: `apps/webui/src/webui/main.py`
- Test: `apps/webui/tests/test_performance_service.py`
- Test: `apps/webui/tests/test_performance_router.py`

**Interfaces:**
- Produces `campaigns(settings) -> dict`.
- Produces `campaign_products(settings, campaign_id, campaign_type='') -> dict`.
- Produces `operation_preview(settings, payload) -> dict`.
- Produces `operation_commit(settings, payload) -> dict`.
- Produces API endpoints under `/api/performance`.

- [ ] **Step 1: Write failing service tests**

Test preview rejects unknown operations, preview normalizes items, ordinary remove calls `delete_campaign_products`, and Search Promo disable calls `disable_search_promo`.

- [ ] **Step 2: Run service tests to verify they fail**

Run: `python -m uv run python -m pytest apps/webui/tests/test_performance_service.py -q`

- [ ] **Step 3: Implement service**

Build client from `performance_client_id` and `performance_client_secret`; normalize campaign and product rows; execute per item and collect result rows.

- [ ] **Step 4: Run service tests to verify they pass**

Run: `python -m uv run python -m pytest apps/webui/tests/test_performance_service.py -q`

- [ ] **Step 5: Write failing router tests**

Test missing credentials produce 400 and happy path returns campaign data using monkeypatched service.

- [ ] **Step 6: Implement router and include it in `main.py`**

Follow analytics router style, using `store_client_id` query param.

- [ ] **Step 7: Run router tests**

Run: `python -m uv run python -m pytest apps/webui/tests/test_performance_router.py -q`

### Task 4: Frontend API, Route, And Page

**Files:**
- Modify: `apps/webui/frontend/src/api.js`
- Modify: `apps/webui/frontend/src/router/index.js`
- Modify: `apps/webui/frontend/src/layouts/AppLayout.vue`
- Create: `apps/webui/frontend/src/views/PerformanceCampaigns.vue`
- Test: `apps/webui/frontend/src/views/performance-campaigns.test.js`

**Interfaces:**
- Produces route `#/campaigns`.
- Produces API methods: `performanceCampaigns`, `performanceCampaignProducts`, `performanceOperationPreview`, `performanceOperationCommit`.

- [ ] **Step 1: Write failing frontend tests**

Mount `PerformanceCampaigns.vue` with mocked API. Assert it loads campaigns, loads products when selecting a campaign, filters product rows, and calls preview before commit.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/webui/frontend && npm run test -- performance-campaigns.test.js`

- [ ] **Step 3: Implement API helpers and route**

Add methods in `api.js`, route in `router/index.js`, and top-level nav item in `AppLayout.vue`.

- [ ] **Step 4: Implement page**

Use existing Element Plus style from Settings. Keep controls dense and operational: store select, refresh, activity table, product table, add dialog, confirm dialog, result summary.

- [ ] **Step 5: Run frontend test**

Run: `cd apps/webui/frontend && npm run test -- performance-campaigns.test.js`

### Task 5: Focused Verification

**Files:**
- No new source files expected.

**Interfaces:**
- Consumes all prior task outputs.

- [ ] **Step 1: Run backend targeted tests**

Run: `python -m uv run python -m pytest apps/webui/tests/test_performance_service.py apps/webui/tests/test_performance_router.py packages/ozon_api/src/ozon_api/tests/test_performance_client.py -q`

- [ ] **Step 2: Run frontend targeted tests**

Run: `cd apps/webui/frontend && npm run test -- performance-campaigns.test.js`

- [ ] **Step 3: Run syntax/static sanity**

Run: `python -m uv run python -m pytest apps/webui/tests/test_settings_api.py -q`

- [ ] **Step 4: Inspect diff**

Run: `git diff -- docs/superpowers/specs/2026-07-08-performance-campaign-management-design.md docs/superpowers/plans/2026-07-08-performance-campaign-management.md packages/ozon_api/src/ozon_api/performance.py apps/webui/src/webui/services/performance_service.py apps/webui/src/webui/routers/performance.py apps/webui/frontend/src/views/PerformanceCampaigns.vue`
