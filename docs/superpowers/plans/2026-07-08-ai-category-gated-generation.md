# AI Category-Gated Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ozon category selection a visible and server-enforced dependency before AI content and attribute generation.

**Architecture:** Add a shared service-layer category gate, use the draft's confirmed category for `ai_generate`, and expose category as a separate frontend pipeline card before content. Keep `recognize_category` and `understand_draft` independently runnable so 1688 can understand before category while WB stays title-first.

**Tech Stack:** FastAPI routers, Python service mixins, image worker text jobs, Vue 3 workbench components, Pinia/composable pipeline state, pytest, Vitest.

## Global Constraints

- Backend must block category-dependent generation when `category_id` or `type_id` is missing.
- Category recognition remains allowed without a category.
- Understanding remains allowed without a category.
- 1688 may run understanding before category recognition.
- WB category recognition stays text-first and must not implicitly run vision understanding.
- `ai_generate` must not implicitly call `recognize_category`.
- Direct API failures for missing category should be user-facing and return 400 where possible.
- Existing user-facing Chinese UI copy should remain Chinese in implementation files.
- Existing dirty workspace changes must not be reverted.

---

## File Structure

- Modify `apps/webui/src/webui/services/_ai_card.py`: add the shared category gate and apply it to `ai_generate`, `ai_fill_attributes`, and `map_attributes`.
- Modify `apps/webui/src/webui/services/_textjob.py`: block `generate-all`/`ai_text` submission when category is missing.
- Modify `apps/webui/src/webui/services/_pipeline.py`: add an `understand` pipeline step, make category/content dependencies visible, and route retry for `understand`.
- Modify `apps/image_worker/src/image_worker/text_worker.py`: protect worker execution from legacy queued jobs with missing category.
- Modify `apps/webui/frontend/src/composables/usePipeline.js`: add `understand` and `category` frontend workflow steps and dependency locking.
- Modify `apps/webui/frontend/src/components/workbench/PipelinePanel.vue`: render six cards with category before content and use backend step mappings.
- Modify tests in `apps/webui/tests/test_ai_card.py`, `apps/webui/tests/test_textjob.py`, `apps/webui/tests/test_task_pipeline.py`, `apps/webui/frontend/src/composables/pipeline.test.js`, and `apps/webui/frontend/src/components/workbench/pipeline-panel.test.js`.

## Task 1: Backend Category Gate

**Files:**
- Modify: `apps/webui/src/webui/services/_ai_card.py`
- Test: `apps/webui/tests/test_ai_card.py`

**Interfaces:**
- Produces: `AiCardMixin._require_category_for_generation(draft: dict, action: str = "生成内容") -> tuple[int, int]`
- Produces: `AiCardMixin._locked_category_roots_for_draft(draft: dict, cat: int, typ: int) -> list[dict]`
- Consumes: existing `_to_int`, `store.get_draft`, `store.update_draft`, `generate_card`

- [ ] **Step 1: Write failing backend tests**

Add tests that assert:

```python
def test_ai_generate_missing_category_blocks_without_llm(self):
    # Create draft without category_id/type_id.
    # Monkeypatch webui.ai_card.generate_card to raise AssertionError if called.
    # POST /api/drafts/{id}/ai-generate returns 400 and the error mentions category.

def test_ai_generate_wb_uses_existing_category_without_recognize(self):
    # Create WB draft with category_id/type_id.
    # app.recognize_category raises AssertionError if called.
    # webui.ai_card.generate_card receives a one-leaf locked category_roots list.
```

Run: `python -m uv run python -m pytest apps/webui/tests/test_ai_card.py -q`
Expected: new tests fail because `ai_generate` still selects or recognizes category internally.

- [ ] **Step 2: Implement the gate**

Add these methods to `AiCardMixin`:

```python
    def _require_category_for_generation(self, draft: dict, action: str = "生成内容") -> tuple[int, int]:
        cat = _to_int((draft or {}).get("category_id"))
        typ = _to_int((draft or {}).get("type_id"))
        if not cat or not typ:
            raise ValueError(f"请先选择或识别 Ozon 分类，再{action}")
        return cat, typ

    def _locked_category_roots_for_draft(self, draft: dict, cat: int, typ: int) -> list[dict]:
        path = str((draft or {}).get("category_path") or "").strip()
        parts = [p.strip() for p in path.split(" / ") if p.strip()]
        if not parts:
            parts = [str((draft or {}).get("source_title") or (draft or {}).get("ozon_title") or "Selected").strip() or "Selected"]
        if len(parts) == 1:
            return [{"category_name": parts[0], "description_category_id": cat, "type_id": typ}]
        root: dict = {"category_name": parts[0], "children": []}
        cur = root
        for name in parts[1:-1]:
            node = {"category_name": name, "children": []}
            cur["children"] = [node]
            cur = node
        cur["children"] = [{"category_name": parts[-1], "description_category_id": cat, "type_id": typ}]
        return [root]
```

- [ ] **Step 3: Apply the gate**

In `ai_generate`, call `_require_category_for_generation(draft, "生成内容")` before building prompts, remove implicit WB `recognize_category`, and pass `_locked_category_roots_for_draft(draft, cat, typ)` to `generate_card`.

In `ai_fill_attributes`, replace the current `return {"error": ...}` missing-category branch with the shared gate so direct routes become HTTP 400.

In `map_attributes`, remove the implicit WB `recognize_category` call and call the gate before category-dependent mapping.

- [ ] **Step 4: Verify**

Run: `python -m uv run python -m pytest apps/webui/tests/test_ai_card.py -q`
Expected: tests pass or only unrelated existing dirty-workspace failures remain.

## Task 2: Text Job and Pipeline Gating

**Files:**
- Modify: `apps/webui/src/webui/services/_textjob.py`
- Modify: `apps/webui/src/webui/services/_pipeline.py`
- Modify: `apps/image_worker/src/image_worker/text_worker.py`
- Test: `apps/webui/tests/test_textjob.py`
- Test: `apps/webui/tests/test_task_pipeline.py`
- Test: `apps/image_worker/tests/test_text_worker.py`

**Interfaces:**
- Consumes: `_require_category_for_generation(draft, action)`
- Produces: pipeline step `understand` mapped to task type `understand`
- Produces: `pipeline_retry(draft_id, "understand")` calls `understand_draft(draft_id)`

- [ ] **Step 1: Write failing tests**

Add tests that assert:

```python
def test_post_generate_all_missing_category_returns_400(self):
    # Draft without category returns 400, not queued job.

def test_pipeline_includes_understand_before_category_and_content(self):
    # draft_pipeline steps order has understand, category_recognition, ai_text.

def test_pipeline_retry_understand_runs_understand_draft(self):
    # app.pipeline_retry(id, "understand") calls app.understand_draft(id).
```

Run: `python -m uv run python -m pytest apps/webui/tests/test_textjob.py apps/webui/tests/test_task_pipeline.py -q`
Expected: new tests fail.

- [ ] **Step 2: Gate text job submission**

In `TextJobMixin.submit_text_job`, after loading the draft and before creating a job, call:

```python
self._require_category_for_generation(draft, "生成内容")
```

Update `/generate-all` router handling so this specific `ValueError` returns 400 instead of 409. Keep duplicate active job errors as 409.

- [ ] **Step 3: Add visible understand pipeline step**

In `_STEP_TASK_TYPES`, add:

```python
"understand": "understand",
```

In `draft_pipeline`, insert an `understand` step before `category_recognition`, with fallback done from `flags["understand"]`.

In `pipeline_retry`, add:

```python
if step_id == "understand":
    return self._track_sync_pipeline_action(draft_id, "understand", lambda: self.understand_draft(draft_id))
```

- [ ] **Step 4: Worker legacy guard**

In `handle_text_job`, before `run_text_pipeline`, load the draft and fail the job if `category_id/type_id` is missing. Use the same Chinese error text as the web gate.

- [ ] **Step 5: Verify**

Run: `python -m uv run python -m pytest apps/webui/tests/test_textjob.py apps/webui/tests/test_task_pipeline.py apps/image_worker/tests/test_text_worker.py -q`
Expected: tests pass or only unrelated existing dirty-workspace failures remain.

## Task 3: Frontend Workflow Cards

**Files:**
- Modify: `apps/webui/frontend/src/composables/usePipeline.js`
- Modify: `apps/webui/frontend/src/components/workbench/PipelinePanel.vue`
- Test: `apps/webui/frontend/src/composables/pipeline.test.js`
- Test: `apps/webui/frontend/src/components/workbench/pipeline-panel.test.js`

**Interfaces:**
- Produces frontend step IDs: `understand`, `category`, `content`, `images`, `rich`, `publish`
- Maps `understand -> understand`, `category -> category_recognition`, `content -> ai_text`

- [ ] **Step 1: Write failing frontend tests**

Add tests that assert:

```javascript
expect(w.findAll('.pp-card').length).toBe(6)
expect(w.text()).toContain('理解/准备')
expect(w.text()).toContain('选择分类')
```

Add composable assertions:

```javascript
expect(pipe.stepLocked('content')).toBe(true) // when category false
await pipe.runStep('category')
expect(api.draftPipelineRetry).toHaveBeenCalledWith(2, 'category_recognition')
```

Run: `cd apps/webui/frontend; npm run test -- pipeline-panel.test.js pipeline.test.js`
Expected: new tests fail.

- [ ] **Step 2: Update workflow mapping**

In `usePipeline.js`, set:

```javascript
export const WF = [
  { id: 'understand', label: '理解/准备', eta: '~30s', dep: [] },
  { id: 'category', label: '选择分类', eta: '~30s', dep: ['understand'] },
  { id: 'content', label: 'AI 生成内容', eta: '~2min（后台）', dep: ['category'] },
  { id: 'images', label: '图集/出图', eta: '~2-3min', dep: ['content'] },
  { id: 'rich', label: '富文本', eta: '即时', dep: ['images'] },
  { id: 'publish', label: '发布', eta: '~30s', dep: ['content', 'images', 'rich'] },
]
```

Update `PIPELINE_STEP`:

```javascript
understand: 'understand',
category: 'category_recognition',
content: 'ai_text',
images: 'ai_image',
rich: 'rich_content',
publish: 'publish',
```

- [ ] **Step 3: Update card list**

In `PipelinePanel.vue`, render six cards with numbers 1-6 and backend mappings matching the composable. Keep existing visual style and card behavior.

- [ ] **Step 4: Verify**

Run: `cd apps/webui/frontend; npm run test -- pipeline-panel.test.js pipeline.test.js`
Expected: tests pass or only unrelated existing dirty-workspace failures remain.

## Task 4: Focused Verification

**Files:**
- No new code changes unless tests expose issues.

- [ ] **Step 1: Run targeted backend tests**

Run: `python -m uv run python -m pytest apps/webui/tests/test_ai_card.py apps/webui/tests/test_textjob.py apps/webui/tests/test_task_pipeline.py apps/image_worker/tests/test_text_worker.py -q`
Expected: PASS.

- [ ] **Step 2: Run targeted frontend tests**

Run: `cd apps/webui/frontend; npm run test -- pipeline-panel.test.js pipeline.test.js`
Expected: PASS.

- [ ] **Step 3: Check worktree**

Run: `git status --short`
Expected: shows modified implementation/test files plus pre-existing unrelated dirty files. Do not stage unrelated changes.
