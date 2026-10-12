# Ozon SKU Product Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a user to import one product from the current Ozon store by numeric SKU, edit it as a local draft, and publish changes back to the original product without cross-store duplicates or silent overwrites.

**Architecture:** Extend the existing Seller API client with SKU lookup, move Ozon-to-draft synchronization into a focused `OzonSyncMixin`, and preserve the current adapter and publish pipeline. Reuse the existing `drafts` table with a store-scoped synthetic source URL and a remote snapshot in `source_raw.ozon_sync`; expose preview/apply endpoints and a Workbench dialog.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy Core, pytest/unittest, Vue 3, Pinia, Element Plus, Vitest.

## Global Constraints

- Use `python -m uv`; do not assume `uv` is on `PATH`.
- Do not add a new product-library table or database migration.
- Do not silently import sibling variants.
- Preserve the original `offer_id` and existing publish preflight/polling behavior.
- Scope every lookup and write by current user and `store_client_id`.
- Preserve non-empty local editable fields unless the user explicitly selects the remote field.
- Never include Seller API keys in responses, logs, or tests.
- Preserve unrelated existing workspace changes; stage only task files for each commit.

---

## File Structure

- Modify `packages/ozon_api/src/ozon_api/client.py`: accept numeric SKU identifiers in product-info lookup.
- Modify `packages/ozon_api/src/ozon_api/tests/test_seller_client.py`: verify identifier payload selection.
- Modify `apps/webui/src/webui/ozon_client_adapter.py`: expose one-product SKU lookup using the shared client.
- Create `apps/webui/src/webui/services/_ozon_sync.py`: own SKU import, diff calculation, selective apply, store-scoped full sync, and draft normalization.
- Modify `apps/webui/src/webui/services/_publish.py`: remove the migrated Ozon pull implementation while retaining publishing.
- Modify `apps/webui/src/webui/app_service.py`: compose `OzonSyncMixin` into `App`.
- Modify `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py`: add store-scoped Ozon identity lookup.
- Modify `apps/webui/src/webui/store.py`: expose the repository lookup.
- Modify `apps/webui/src/webui/models.py`: define SKU import/sync request models.
- Create `apps/webui/src/webui/routers/ozon_products.py`: expose SKU preview/apply and full sync routes.
- Modify `apps/webui/src/webui/routers/warehouse.py`: keep `/api/ozon/pull` as a compatibility wrapper.
- Modify `apps/webui/src/webui/main.py`: register the new router.
- Modify `apps/webui/tests/test_ozon_pull.py`: test mapping reuse, idempotency, safe merge, store isolation, partial failures, and compatibility.
- Modify `apps/webui/tests/test_api.py`: test HTTP validation and response codes.
- Modify `apps/webui/frontend/src/api.js`: add import/apply/sync calls.
- Create `apps/webui/frontend/src/components/workbench/OzonImportDialog.vue`: SKU input, progress, warning and conflict UI.
- Create `apps/webui/frontend/src/components/workbench/OzonImportDialog.test.js`: component behavior tests.
- Modify `apps/webui/frontend/src/views/Workbench.vue`: mount the dialog and open the imported draft.
- Modify `apps/webui/frontend/src/views/workbench.test.js`: integration test for the Workbench entry point.

---

### Task 1: Seller API SKU lookup

**Files:**
- Modify: `packages/ozon_api/src/ozon_api/client.py:377-385`
- Modify: `packages/ozon_api/src/ozon_api/tests/test_seller_client.py`
- Modify: `apps/webui/src/webui/ozon_client_adapter.py:157-171`

**Interfaces:**
- Produces: `OzonSellerClient.get_products_info(*, offer_ids=None, product_ids=None, skus=None) -> dict[str, Any]`
- Produces: `get_ozon_info_by_skus(settings: dict, skus: list[int]) -> dict[str, dict]`, keyed by string SKU.

- [ ] **Step 1: Write failing client and adapter tests**

```python
def test_get_products_info_can_query_skus(self) -> None:
    transport = FakeTransport()
    client = OzonSellerClient("123", "secret", transport=transport)
    client.get_products_info(skus=[4998185789])
    self.assertEqual(transport.calls[0]["json"], {"sku": [4998185789]})

def test_get_products_info_rejects_mixed_identifiers(self) -> None:
    client = OzonSellerClient("123", "secret", transport=FakeTransport())
    with self.assertRaises(ValueError):
        client.get_products_info(offer_ids=["A"], skus=[1])
```

Add an adapter test with a stub client returning `{"items": [{"sku": 4998185789, "offer_id": "A"}]}` and assert the helper returns `{"4998185789": item}`.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `python -m uv run python -m pytest packages/ozon_api/src/ozon_api/tests/test_seller_client.py apps/webui/tests/test_ozon_pull.py -q`

Expected: FAIL because `skus` and `get_ozon_info_by_skus` do not exist.

- [ ] **Step 3: Implement identifier selection and adapter batching**

```python
def get_products_info(self, *, offer_ids=None, product_ids=None, skus=None):
    supplied = sum(bool(x) for x in (offer_ids, product_ids, skus))
    if supplied > 1:
        raise ValueError("offer_ids, product_ids and skus are mutually exclusive")
    if offer_ids:
        payload = {"offer_id": [str(x) for x in offer_ids]}
    elif product_ids:
        payload = {"product_id": [int(x) for x in product_ids]}
    elif skus:
        payload = {"sku": [int(x) for x in skus]}
    else:
        payload = {"offer_id": []}
    return self.request("/v3/product/info/list", payload)
```

In the adapter, batch up to 1000 SKUs per call and key returned items by `str(item["sku"])`.

- [ ] **Step 4: Run tests and commit**

Run: `python -m uv run python -m pytest packages/ozon_api/src/ozon_api/tests/test_seller_client.py apps/webui/tests/test_ozon_pull.py -q`

Expected: PASS.

Commit: `git commit -m "feat(api): support product lookup by Ozon SKU"`

---

### Task 2: Store-scoped Ozon draft identity

**Files:**
- Modify: `packages/ozon_common/src/ozon_common/dal/repositories/draft_repo.py`
- Modify: `apps/webui/src/webui/store.py`
- Modify: `apps/webui/tests/test_ozon_pull.py`

**Interfaces:**
- Produces: `DraftRepo.find_ozon_draft(*, user_id: int, store_client_id: str, sku: str, product_id: int | None, offer_id: str) -> dict | None`
- Produces: matching `Store.find_ozon_draft(...)` wrapper using the current user.

- [ ] **Step 1: Write failing identity tests**

Create two drafts with the same `offer_id` and SKU but different `store_client_id`. Assert each store lookup returns its own row. Add a legacy row using `source_url="ozon://product/A"` and assert lookup by `product_id` or store-scoped `offer_id` adopts it.

```python
found = store.find_ozon_draft(
    store_client_id="C-2", sku="4998185789", product_id=222, offer_id="A"
)
self.assertEqual(found["store_client_id"], "C-2")
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `python -m uv run python -m pytest apps/webui/tests/test_ozon_pull.py -q`

Expected: FAIL with missing `find_ozon_draft`.

- [ ] **Step 3: Implement one scoped query**

Use `and_(D.c.user_id == user_id, D.c.store_client_id == store_client_id, or_(...))`, matching `source_offer_id == sku`, `source_url == f"ozon://product/{sku}"`, `ozon_product_id == product_id`, or `offer_id == offer_id`. Order by `D.c.id.desc()` and reuse `_row_to_draft`.

- [ ] **Step 4: Run tests and commit**

Run: `python -m uv run python -m pytest apps/webui/tests/test_ozon_pull.py packages/ozon_common/tests/test_draft_repo.py -q`

Expected: PASS.

Commit: `git commit -m "fix(common): scope Ozon draft identity by store"`

---

### Task 3: Ozon sync service with preview and selective apply

**Files:**
- Create: `apps/webui/src/webui/services/_ozon_sync.py`
- Modify: `apps/webui/src/webui/services/_publish.py:509-623`
- Modify: `apps/webui/src/webui/app_service.py`
- Modify: `apps/webui/tests/test_ozon_pull.py`

**Interfaces:**
- Produces: `import_ozon_product_by_sku(sku: int, store_client_id: str, selected_fields: list[str] | None = None) -> dict`
- Produces: `sync_ozon_products(store_client_id: str, visibility: str = "ALL") -> dict`
- Preserves: `pull_ozon_products(visibility="ALL", store_client_id=None)` compatibility wrapper.

- [ ] **Step 1: Write failing service tests**

Cover: first import, repeated import, non-destructive conflict preview, selective remote apply, current-store credentials, partial description/attribute warnings, and full-sync continuation after one item failure.

```python
preview = app.import_ozon_product_by_sku(4998185789, "C-1")
self.assertTrue(preview["created"])
self.assertEqual(preview["draft"]["source_offer_id"], "4998185789")

app.store.update_draft(preview["draft"]["id"], {"ozon_title": "Local title"})
conflict = app.import_ozon_product_by_sku(4998185789, "C-1")
self.assertEqual(conflict["draft"]["ozon_title"], "Local title")
self.assertIn("ozon_title", {x["field"] for x in conflict["conflicts"]})

applied = app.import_ozon_product_by_sku(
    4998185789, "C-1", selected_fields=["ozon_title"]
)
self.assertEqual(applied["draft"]["ozon_title"], "Remote title")
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m uv run python -m pytest apps/webui/tests/test_ozon_pull.py -q`

Expected: FAIL because `OzonSyncMixin` is absent.

- [ ] **Step 3: Implement the focused mixin**

Implement constants for protected fields and helpers `_remote_draft_by_sku`, `_diff_editable_fields`, `_sync_snapshot`, `_normalize_ozon_draft`, and `_merge_pulled_into_existing`. Use `self._settings_for_store(store_client_id)` before every Seller API call and set:

```python
draft.update({
    "store_client_id": scid,
    "source": "ozon",
    "source_platform": "ozon",
    "source_offer_id": str(sku),
    "source_url": f"ozon://product/{sku}",
    "status": "published",
})
```

Store the remote snapshot under `source_raw["ozon_sync"]` with `sku`, `synced_at`, `info`, `attributes`, `description`, and `variant_warning`. For existing drafts, always refresh identity/snapshot fields, fill empty editable fields, and apply only names listed in `selected_fields`.

Move the existing full-pull functions from `_publish.py` into the new mixin and make the old method delegate with its original argument order.

- [ ] **Step 4: Run service and publish regression tests**

Run: `python -m uv run python -m pytest apps/webui/tests/test_ozon_pull.py apps/webui/tests/test_publish_preview.py apps/webui/tests/test_publish_group.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `git commit -m "feat(app): add store-scoped Ozon SKU sync service"`

---

### Task 4: FastAPI routes and compatibility endpoint

**Files:**
- Modify: `apps/webui/src/webui/models.py`
- Create: `apps/webui/src/webui/routers/ozon_products.py`
- Modify: `apps/webui/src/webui/routers/warehouse.py`
- Modify: `apps/webui/src/webui/main.py`
- Modify: `apps/webui/tests/test_api.py`

**Interfaces:**
- Produces: `POST /api/ozon-products/import-by-sku`
- Produces: `POST /api/ozon-products/sync`
- Preserves: `POST /api/ozon/pull`

- [ ] **Step 1: Write failing HTTP tests**

```python
r = client.post("/api/ozon-products/import-by-sku", json={
    "sku": 4998185789, "store_client_id": "C-1"
})
self.assertEqual(r.status_code, 200)

r = client.post("/api/ozon-products/import-by-sku", json={
    "sku": 0, "store_client_id": "C-1"
})
self.assertEqual(r.status_code, 422)
```

Also assert missing SKU maps to 404, store configuration errors map to 400, and the compatibility endpoint forwards `store_client_id`.

- [ ] **Step 2: Run and confirm route failure**

Run: `python -m uv run python -m pytest apps/webui/tests/test_api.py -q`

Expected: FAIL with 404 for the new route.

- [ ] **Step 3: Implement models and routes**

Define Pydantic models with `sku: int = Field(gt=0)`, non-empty `store_client_id`, optional `selected_fields`, and `visibility="ALL"`. Catch `KeyError` from a missing SKU as HTTP 404; convert credential/configuration `ValueError` to HTTP 400; do not return exception internals containing credentials.

- [ ] **Step 4: Run tests and commit**

Run: `python -m uv run python -m pytest apps/webui/tests/test_api.py apps/webui/tests/test_ozon_pull.py -q`

Expected: PASS.

Commit: `git commit -m "feat(app): expose Ozon SKU import endpoints"`

---

### Task 5: SKU import dialog

**Files:**
- Modify: `apps/webui/frontend/src/api.js`
- Create: `apps/webui/frontend/src/components/workbench/OzonImportDialog.vue`
- Create: `apps/webui/frontend/src/components/workbench/OzonImportDialog.test.js`

**Interfaces:**
- Consumes: `api.importOzonBySku(sku, store_client_id, selected_fields)`.
- Emits: `imported` with `{ draft, created, warnings }`.

- [ ] **Step 1: Write failing component tests**

Mount with Element Plus controls stubbed. Assert non-numeric input is rejected without an API call; valid input sends current store ID; created result emits `imported`; conflict result renders local/remote values; applying checked fields sends `selected_fields`.

```javascript
expect(api.importOzonBySku).toHaveBeenCalledWith('4998185789', 'C-1', undefined)
expect(wrapper.emitted('imported')[0][0].draft.id).toBe(42)
```

- [ ] **Step 2: Run and confirm failure**

Run from `apps/webui/frontend`: `npm test -- --run src/components/workbench/OzonImportDialog.test.js`

Expected: FAIL because the component and API method do not exist.

- [ ] **Step 3: Implement API calls and dialog state machine**

Add:

```javascript
importOzonBySku: (sku, store_client_id, selected_fields) => req(
  'POST', '/api/ozon-products/import-by-sku',
  { sku: Number(sku), store_client_id, ...(selected_fields ? { selected_fields } : {}) },
),
syncOzonProducts: (store_client_id, visibility = 'ALL') => req(
  'POST', '/api/ozon-products/sync', { store_client_id, visibility },
),
```

The dialog uses `idle/loading/conflicts/done/error` states, defaults every conflict checkbox to false, shows warnings, and disables submit when no current store is selected.

- [ ] **Step 4: Run tests and commit**

Run: `npm test -- --run src/components/workbench/OzonImportDialog.test.js`

Expected: PASS.

Commit: `git commit -m "feat(fe): add Ozon SKU import dialog"`

---

### Task 6: Workbench integration and end-to-end regression

**Files:**
- Modify: `apps/webui/frontend/src/views/Workbench.vue`
- Modify: `apps/webui/frontend/src/views/workbench.test.js`

**Interfaces:**
- Consumes: `OzonImportDialog` `imported` event.
- Produces: user-visible “从 Ozon 导入” entry point that refreshes drafts and selects the returned draft.

- [ ] **Step 1: Write failing Workbench integration test**

Stub `OzonImportDialog` with a button that emits `{draft:{id:42}}`. Assert clicking the toolbar entry opens it, then the event calls `store.loadDrafts()` and sets `store.selectedId = 42`.

- [ ] **Step 2: Run and confirm failure**

Run from `apps/webui/frontend`: `npm test -- --run src/views/workbench.test.js`

Expected: FAIL because the entry point is absent.

- [ ] **Step 3: Integrate the dialog**

Add a compact toolbar above the two-column Workbench grid with “从 Ozon 导入” as the primary import action and “同步当前店铺” as a secondary action inside the dialog. On `imported`, await `store.loadDrafts()`, set `store.selectedId`, and let the existing watcher load the right-side draft.

- [ ] **Step 4: Run frontend tests and build**

Run from `apps/webui/frontend`:

```bash
npm test
npm run build
```

Expected: all Vitest suites PASS and Vite build completes without errors.

- [ ] **Step 5: Run backend regression suite**

Run from repository root:

```bash
python -m uv run python -m pytest apps/webui/tests packages --ignore-glob='*_live.py' -q
```

Expected: all offline backend tests PASS.

- [ ] **Step 6: Review the final diff and commit**

Run:

```bash
git diff --check
git status --short
```

Verify only intended task files are staged. Commit: `git commit -m "feat(app): import and edit Ozon products by SKU"`

---

## Final Verification

- [ ] Start the backend with `python -m uv run --package ozon-webui ozon-webui`.
- [ ] In a configured store, import one real numeric Ozon SKU.
- [ ] Confirm the created draft contains the original `offer_id`, product ID, description, attributes and images.
- [ ] Change one Russian title or description field and run publish preview.
- [ ] Publish and verify the existing Ozon product is updated rather than duplicated.
- [ ] Import the same SKU again and confirm the same local draft is returned with local edits preserved.
- [ ] Switch stores and verify the same `offer_id` cannot select the previous store's draft.
