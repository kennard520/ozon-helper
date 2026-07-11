# Workbench Group Publish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the duplicate workbench single-variant publish button with one variant-group publish action while retaining the pipeline's current-variant publish action.

**Architecture:** `VariantGroupBar` renders and emits the group action; `Workbench` wires it to `useDraftBatchOps`. The composable confirms and calls the existing `api.publishGroup`, owns loading/result state, and refreshes drafts; the backend remains unchanged.

**Tech Stack:** Vue 3, Pinia, Element Plus, Vitest, existing FastAPI group-publish endpoint.

## Global Constraints

- Render exactly one group-publish button in the variant-group header.
- Keep `PipelinePanel`'s `publish-one` current-variant action unchanged.
- Remove the standalone publish bar above `PipelinePanel`.
- Ignore duplicate group-publish clicks while a request is running.
- Confirm group size and target store before publishing.
- Reuse `api.publishGroup(groupKey, storeClientId)` without backend changes.

---

### Task 1: Group Publish Operation and Workbench UI

**Files:**
- Modify: `apps/webui/frontend/src/composables/useDraftBatchOps.js`
- Modify: `apps/webui/frontend/src/composables/batchops.test.js`
- Modify: `apps/webui/frontend/src/components/workbench/VariantGroupBar.vue`
- Modify: `apps/webui/frontend/src/components/workbench/VariantGroupBar.test.js`
- Modify: `apps/webui/frontend/src/views/Workbench.vue`
- Modify: `apps/webui/frontend/src/views/workbench.test.js`

**Interfaces:**
- Consumes: `api.publishGroup(groupKey, storeClientId)` and workbench `groupKey`/`variantCount`.
- Produces: `doPublishGroup(groupKey, variantCount)`, `groupPublishing`, `groupPublishResult`, and `VariantGroupBar` event `publish-group`.

- [ ] **Step 1: Write failing operation tests**

Extend the API mock with `publishGroup`. Assert confirmation text includes the
group count, the API receives group/store, state prevents a second concurrent
call, success refreshes drafts, cancellation makes no call, and rejection calls
`ElMessage.error`:

```js
api.publishGroup.mockResolvedValue({ published: 2, failed: 1, skipped: 1, results: [] })
const pending = ops.doPublishGroup('G-1', 4)
await pending
expect(api.publishGroup).toHaveBeenCalledWith('G-1', 'store-1')
expect(store.loadDrafts).toHaveBeenCalled()
expect(ops.groupPublishResult.value).toMatchObject({ published: 2, failed: 1, skipped: 1 })
```

- [ ] **Step 2: Run operation tests and verify RED**

Run: `npm.cmd test -- src/composables/batchops.test.js`

Expected: FAIL because `doPublishGroup` and group state do not exist.

- [ ] **Step 3: Implement the operation**

Add `groupPublishing = ref(false)` and `groupPublishResult = ref(null)`. Implement:

```js
async function doPublishGroup(groupKey, variantCount) {
  if (!groupKey || groupPublishing.value) return
  const targetStore = selectedStore.value || String(store.settings.ozon_client_id || '')
  try {
    await confirmFn.value(`确认发布整组 ${variantCount} 个变体到当前目标店铺？`, '发布整组')
  } catch { return }
  groupPublishing.value = true
  groupPublishResult.value = null
  try {
    const result = await api.publishGroup(groupKey, targetStore)
    groupPublishResult.value = result
    await store.loadDrafts()
    return result
  } catch (err) {
    ElMessage.error(`整组发布失败：${(err && err.message) || err}`)
    return null
  } finally {
    groupPublishing.value = false
  }
}
```

Export the function and state from the composable.

- [ ] **Step 4: Run operation tests and verify GREEN**

Run: `npm.cmd test -- src/composables/batchops.test.js`

Expected: PASS.

- [ ] **Step 5: Write failing component and integration tests**

Assert `VariantGroupBar` renders one `.vgb-publish` button labeled with the
variant count, emits `publish-group`, and disables for empty/loading states.
Update `Workbench` test to assert the old `.wb-publish-bar` is absent, the group
event calls `doPublishGroup`, and `PipelinePanel` retains `publish-one`.

- [ ] **Step 6: Run UI tests and verify RED**

Run: `npm.cmd test -- src/components/workbench/VariantGroupBar.test.js src/views/workbench.test.js`

Expected: FAIL because the group button/event wiring is absent and the old bar remains.

- [ ] **Step 7: Implement the UI wiring**

Add props `publishing` and a header button to `VariantGroupBar`:

```vue
<el-button class="vgb-publish" type="primary" size="small"
  :loading="publishing" :disabled="!wb.groupKey || !wb.variantCount || publishing"
  @click="emit('publish-group')">
  发布整组（{{ wb.variantCount }} 个变体）
</el-button>
```

In `Workbench`, remove `.wb-publish-bar`, pass `ops.groupPublishing` to
`VariantGroupBar`, wire `@publish-group="ops.doPublishGroup(wb.groupKey,
wb.variantCount)"`, and leave `PipelinePanel @publish-one` unchanged.

- [ ] **Step 8: Verify targeted and full frontend suites**

Run:

```powershell
npm.cmd test -- src/composables/batchops.test.js src/components/workbench/VariantGroupBar.test.js src/views/workbench.test.js src/components/workbench/pipeline-panel.test.js
npm.cmd test
npm.cmd run build
```

Expected: all tests pass and Vite build exits 0.

- [ ] **Step 9: Commit**

```powershell
git add apps/webui/frontend/src/composables/useDraftBatchOps.js apps/webui/frontend/src/composables/batchops.test.js apps/webui/frontend/src/components/workbench/VariantGroupBar.vue apps/webui/frontend/src/components/workbench/VariantGroupBar.test.js apps/webui/frontend/src/views/Workbench.vue apps/webui/frontend/src/views/workbench.test.js docs/superpowers/plans/2026-07-11-workbench-group-publish.md
git commit -m "feat(app): add workbench group publish action"
```
