# State Machines

## Draft

```mermaid
stateDiagram-v2
  [*] --> draft
  draft --> media_pending: media upload required
  draft --> ready: required content present
  ready --> media_pending: media becomes pending
  media_pending --> ready: media uploaded
  ready --> publishing: user publishes
  media_pending --> publishing: not allowed
  publishing --> published: Ozon imported
  publishing --> failed: Ozon rejects
  publishing --> skipped: Ozon skips update
  failed --> ready: user edits or retries
  published --> ready: user edits local draft
```

Draft validation risks do not block publish. They are shown as warnings with `field`, `step`, and `fix_action`. Technical prerequisites still block execution when the system cannot submit a payload, for example media still uploading, missing RUB rate for RUB contracts, missing OSS fallback, billing failure, or payload construction failure.

## Task Run

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> running
  running --> done
  running --> failed
  running --> cancel_requested
  cancel_requested --> cancelled
  cancel_requested --> failed: timeout or worker failure
  queued --> failed: timeout
  running --> failed: timeout
  failed --> queued: retry creates new run
  done --> [*]
  failed --> [*]
  skipped --> [*]
  cancelled --> [*]
```

`task_runs` is the unified task index. Draft-scoped tasks use `draft_id`; global sync tasks may use `draft_id = null`.

Covered task types include:

- `ai_text`
- `ai_image`
- `media_rehost`
- `category_recognition`
- `attribute_mapping`
- `attribute_ai_fill`
- `translate`
- `rich_content`
- `publish`
- `warehouse_sync`
- `fbs_pull`
- `ozon_product_pull`

Active tasks are `queued`, `running`, `submitted`, `designing`, and `cancel_requested`. Pipeline retry returns the active task instead of submitting a duplicate. Stale active tasks are marked `failed` with a timeout error when Pipeline state is loaded.

## Publish

```mermaid
stateDiagram-v2
  [*] --> preview
  preview --> confirm: warnings shown
  preview --> blocked: technical error
  confirm --> media_rehost
  media_rehost --> billing
  billing --> ozon_submit
  ozon_submit --> ozon_poll
  ozon_poll --> published
  ozon_poll --> failed
  ozon_poll --> skipped
```

Preflight warnings are advisory. The user can continue after confirmation. Technical errors stop before `ozon_submit`.

## Pipeline

Pipeline step states:

- `pending`
- `running`
- `warning`
- `blocked`
- `failed`
- `done`
- `skipped`
- `cancelled`

`warning` means the user can continue. `blocked` means the system cannot execute the next operation yet. The Workbench uses `pipeline.next` to offer the next runnable or retryable action.
