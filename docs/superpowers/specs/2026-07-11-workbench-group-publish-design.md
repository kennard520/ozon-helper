# Workbench Group Publish Design

## Goal

Make publishing intent unambiguous in the workbench:

- Publish the entire variant group from one button in the variant-group header.
- Keep the pipeline action for publishing only the current variant.
- Remove the duplicate single-variant publish button above the pipeline.

## Interaction

`VariantGroupBar` shows one primary action on the right side of its heading:
`发布整组（N 个变体）`. The action is disabled when no group or variants are
loaded and shows a loading state while publishing.

Clicking it opens a confirmation containing the group size and target store.
After confirmation, the frontend calls the existing `api.publishGroup(group,
storeClientId)` endpoint. The result reports published, failed, and skipped
items; the draft list and variant group are refreshed afterward.

The standalone publish bar currently rendered above `PipelinePanel` is removed.
`PipelinePanel` retains its existing `publish-one` event and remains the sole
entry point for publishing the current variant.

## Ownership

`VariantGroupBar` owns only presentation and emits `publish-group`.
`Workbench` wires the event to the publishing operation. `useDraftBatchOps`
owns confirmation, API execution, loading state, result formatting, and refresh.
The existing backend group-publish API is reused without schema changes.

## Error Handling

- User cancellation performs no API call.
- Duplicate clicks are ignored while a group publish is running.
- API failures show an actionable error and keep the current group visible.
- Partial results show published, failed, and skipped counts.

## Tests

- The variant-group header renders exactly one group-publish button with count.
- The button emits `publish-group` and respects disabled/loading states.
- Workbench removes the duplicate top publish button and wires the group event.
- Pipeline current-variant publishing remains unchanged.
- The group operation confirms, calls `api.publishGroup` with group/store, and
  refreshes state; cancellation and API failures are covered.
