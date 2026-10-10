# AI Category-Gated Generation Design

## Context

The current workbench has a backend `category_recognition` pipeline step, but the main UI still presents "AI generated content" as the first user-facing action. Some backend paths also keep category recognition inside text generation, so the user does not get a clear stop point to review or correct the Ozon category before downstream content and attributes are generated.

Category is a hard dependency for Ozon listing quality: required attributes, attribute dictionaries, brand resolution, and category-dependent type fields all depend on `category_id` and `type_id`. The workflow should make that dependency explicit in both UI and backend behavior.

## Goals

- Split AI listing work into visible ordered stages: understand/prep, category selection, then content and attributes.
- Let users review and manually correct AI-selected categories before generated content or attributes run.
- Enforce the category dependency on the server, not only by disabling UI controls.
- Preserve source-platform differences so WB does not pay for unnecessary vision understanding, while 1688 can still use understanding before category choice.
- Keep the change compatible with existing pipeline task tracking and text job polling.

## Non-Goals

- Redesign the full publish pipeline or image generation flow.
- Replace the category selector component.
- Change Ozon category matching prompts or category-tree indexing unless needed for the gating behavior.
- Automatically publish or apply generated proposals without the existing confirmation behavior.

## Platform Rules

### 1688

The intended dependency chain is:

1. Understand product data and images when understanding is missing.
2. Recognize the Ozon category from the enriched profile.
3. Generate content and fill attributes using the confirmed category.

For 1688 drafts, category recognition may trigger understanding first, following the existing `recognize_category` behavior. Content generation and attribute filling must not proceed unless the draft already has `category_id` and `type_id`.

### Wildberries

WB category recognition should stay text-first and title-focused. WB already carries structured product and category signals, and prior behavior intentionally avoids automatic vision understanding for WB category recognition.

The intended chain is:

1. Recognize category from WB title and structured signals.
2. User reviews or corrects the selected category.
3. Generate content and fill attributes using the confirmed category.

WB content generation must not call category recognition implicitly. If the category is missing, it returns a clear blocking error.

### Ozon and Other Sources

If a draft already has `category_id` and `type_id`, content and attribute generation may run against that category. If either field is missing, generation is blocked until the user selects or recognizes a category.

## Backend Design

Add a single shared category gate near the service layer, for example `_require_category_for_generation(draft, action)`, that returns normalized integer or string category IDs or raises a clear `ValueError`. The message should be user-facing Chinese and explain that the user must select or recognize an Ozon category before generating content.

Apply this gate to all backend entry points that generate category-dependent output:

- `ai_generate(draft_id)`
- `ai_fill_attributes(draft_id)`
- `map_attributes(draft_id)` before it routes to AI fill or rule mapping when the route requires Ozon attributes
- text job submission or execution for `ai_text`
- pipeline retry for the `ai_text`, `attribute_mapping`, and `attribute_ai_fill` steps

Category recognition itself remains allowed without an existing category. Understanding also remains allowed independently.

`ai_generate` should stop choosing a category as part of content generation. It should use the draft's current confirmed `category_id/type_id` and a locked category root built from the current category path or resolved leaf. If the category is missing, it returns the gate error and does not call the LLM.

The text worker pipeline should no longer be the only path that silently performs `understand -> category -> copy -> attrs` in one opaque job. The backend should expose and track those as separate dependency steps. If a legacy `generate-all` request is still used, it should fail fast when category is missing instead of recognizing and continuing invisibly.

## Frontend Design

Update the workbench cards to show category as a first-class step before content generation. The main sequence becomes:

1. Understand/prep
2. Choose category
3. Generate content
4. Images
5. Rich content
6. Publish

The category card runs the existing `category_recognition` backend step. The content card runs `ai_text` only when the current draft has a confirmed category or the pipeline reports category recognition as done. If category is missing, the content card is locked and explains that the user must select or recognize a category first.

Manual correction happens through the existing detail category selector. After the user edits `category_id/type_id`, the pipeline should refresh so the category step becomes done and downstream content unlocks.

## Error Handling

- Missing category errors should be HTTP 400 for direct API calls.
- Pipeline task runs should record the same user-facing error when a gated step is attempted.
- Frontend cards should render the backend error in the card reason area, not as a silent no-op.
- If AI category recognition fails, downstream steps remain locked until the user manually chooses a category.

## Testing

Backend tests:

- `ai_generate` returns an error and does not call the LLM when category is missing.
- `ai_generate` uses the existing draft category and does not call `recognize_category` implicitly for WB.
- `ai_fill_attributes` and `map_attributes` block when category is missing.
- pipeline retry for content and attributes records a failed task or returns a clear 400-style error when category is missing.
- category recognition remains runnable when category is missing.

Text pipeline tests:

- legacy `generate-all` cannot start or cannot execute category-dependent generation without a confirmed category.
- task progress and errors still sync to `task_runs`.

Frontend tests:

- the workbench renders the category step before content.
- clicking category calls `category_recognition`.
- content is locked when category is missing.
- content unlocks when the server pipeline reports `category_recognition` done or the draft has category fields.

## Rollout Notes

This is a behavior change: users must explicitly run or choose category before content generation. It should reduce wasted AI calls and make wrong categories fixable before attributes and copy are produced.

Existing drafts with already-filled categories continue to work. Existing drafts without categories will require one extra category step before content generation.
