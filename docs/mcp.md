# ozon-helper MCP server

`apps/mcp_server` exposes the existing `webui.app_service.App` workflow as MCP tools for ChatGPT Apps or other MCP clients.

## Run locally

```bash
python -m uv sync --package ozon-mcp
python -m uv run --package ozon-mcp ozon-mcp
```

For the ChatGPT-facing minimal tool surface:

```bash
python -m uv run --package ozon-mcp ozon-mcp-chatgpt
```

Defaults:

- MCP endpoint: `http://127.0.0.1:8586/mcp`
- User context: `OZON_MCP_USER_ID=1`
- Allowed HTTP Host headers: `127.0.0.1:*`, `localhost:*`, `[::1]:*`

Override for a server:

```bash
set OZON_MCP_HOST=0.0.0.0
set OZON_MCP_PORT=8586
set OZON_MCP_USER_ID=1
set OZON_MCP_ALLOWED_HOSTS=mcp.example.com,127.0.0.1:*
python -m uv run --package ozon-mcp ozon-mcp
```

For ChatGPT, put Caddy/Nginx/Cloudflare Tunnel in front and expose HTTPS, for example:

```text
https://mcp.example.com/mcp -> http://127.0.0.1:8586/mcp
```

Current production URL:

```text
https://mcp.ryda.top:8443/mcp
```

`https://mcp.ryda.top/mcp` is kept configured on the server, but port 80/443 traffic for this domain may be blocked by the cloud provider until ICP/domain access filing is complete.

## First tool surface

The full internal MCP entrypoint is `ozon-mcp`. It keeps every workflow and fallback tool available:

- `health`
- `list_drafts`
- `get_draft`
- `create_draft_from_parsed`
- `update_draft`
- `understand_draft`
- `recommend_draft`
- `generate_listing`
- `get_text_job_status`
- `apply_ai_proposal`
- `search_category`
- `get_category_attributes`
- `search_attribute_values`
- `check_required`
- `get_image_plan`
- `design_image_plan`
- `generate_plan_slot`
- `generate_image`
- `submit_generate_images`
- `get_image_job_status`
- `apply_image_candidates`
- `publish_preview`
- `publish_preflight`
- `publish_draft`
- `set_chatgpt_image_target`
- `get_chatgpt_image_target`
- `clear_chatgpt_image_target`
- `create_chatgpt_image_tasks`
- `list_chatgpt_image_tasks`
- `get_next_chatgpt_image_task`
- `openai_generate_product_image`
- `upload_chatgpt_downloaded_image`

`publish_draft` requires `confirm=true`; use `publish_preview` and `publish_preflight` first.

## ChatGPT minimal tool surface

Use `ozon-mcp-chatgpt` for the ChatGPT website connector. It exposes only the tools ChatGPT should normally call, so it will not accidentally choose the old backend AI/worker image flow.

- `health`
- `list_drafts`
- `get_draft`
- `get_variant_group`
- `chatgpt_get_product_context`
- `chatgpt_get_next_variant_work_item`
- `chatgpt_save_variant_features`
- `chatgpt_save_understanding`
- `chatgpt_save_listing`
- `chatgpt_save_image_plan`
- `chatgpt_save_rich_content`
- `chatgpt_attach_image_url`
- `create_chatgpt_image_tasks`
- `list_chatgpt_image_tasks`
- `get_next_chatgpt_image_task`
- `openai_generate_product_image`
- `update_draft`
- `search_category`
- `get_category_attributes`
- `search_attribute_values`
- `check_required`
- `get_ozon_analytics_context`
- `chatgpt_save_optimization_notes`
- `product_status`
- `publish_preflight`
- `publish_preview`

Not exposed in this minimal entrypoint:

- Backend text/image AI tools: `understand_draft`, `generate_listing`, `design_image_plan`, `generate_image`, `generate_plan_slot`, `submit_generate_images`, `get_image_job_status`, `apply_image_candidates`, `make_rich_content`.
- One-click backend pipelines: `process_product`, `run_draft_non_publish_pipeline`, `run_variant_group_non_publish_pipeline`.
- Real publishing: `publish_draft`.

### Multi-variant ChatGPT loop

For products with `variant_group`, process one variant at a time. Do not generate one shared result and write it to the whole group.

Feature loop:

```json
{"draft_id": 1019, "stage": "features"}
```

Call `chatgpt_get_next_variant_work_item` repeatedly. For each returned `draft_id`, ChatGPT generates variant-specific product features and writes them back with:

```json
{"draft_id": 1020, "features": {"product_type": "...", "variant": "..."}}
```

using `chatgpt_save_variant_features`. Repeat until `done=true`.

Image loop:

```json
{"draft_id": 1019, "stage": "images"}
```

For each returned `draft_id`, call `openai_generate_product_image` synchronously. The tool uploads the image to OSS and attaches it to that exact variant draft. Do not use `create_chatgpt_image_tasks` / `get_next_chatgpt_image_task` for multi-variant ChatGPT processing.

### Store analytics for ChatGPT optimization

Use `get_ozon_analytics_context` when ChatGPT should analyze store/SKU performance before rewriting a listing or deciding what to optimize.

Typical store-level request:

```json
{
  "days": 14,
  "sections": ["dashboard", "keywords", "trends"],
  "top_skus": 20,
  "keyword_limit": 10
}
```

Typical single draft/SKU request:

```json
{
  "draft_id": 1019,
  "days": 30,
  "sections": ["dashboard", "keywords", "trends"]
}
```

The tool returns compact dashboard rows, optional per-day trend rows, and optional Ozon search-query data. ChatGPT can then call `chatgpt_save_optimization_notes` to save its analysis/recommendations without publishing.

## ChatGPT downloaded image watcher

Use this when ChatGPT web generates the image and the user clicks download.

```bash
python apps/mcp_server/scripts/watch_chatgpt_downloads.py --mcp-url http://110.42.226.37:8586/mcp
```

On Windows, run:

```bat
apps\mcp_server\scripts\start_chatgpt_download_watcher.bat
```

The watcher uses a dedicated folder:

```text
%USERPROFILE%\Downloads\ozon-chatgpt-images
```

Save ChatGPT-generated images into that folder, not the general Downloads folder.

Workflow:

1. In ChatGPT, save an image plan, then call `create_chatgpt_image_tasks`.
2. Call `get_next_chatgpt_image_task`; MCP sets the current target and returns a unique `file_name`.
3. Generate that image in ChatGPT web.
4. Download/save it into the watcher folder, using the returned `file_name` when possible.
5. The watcher uploads the image to OSS, attaches it to the draft slot, and marks the task `uploaded`.
6. Repeat `get_next_chatgpt_image_task` until it returns `done=true`.

## OpenAI-compatible image generation through MCP

Use `openai_generate_product_image` when ChatGPT should call the configured image API directly instead of using ChatGPT web download.

Typical arguments:

```json
{
  "draft_id": 1019,
  "prompt": "Professional Ozon product image, 3:4 vertical, white background, no text, no watermark...",
  "mode": "edit",
  "reference_image_indexes": [0],
  "slot_id": "main",
  "image_type": "主图",
  "size": "1024x1536",
  "n": 1
}
```

The tool calls the configured OpenAI-compatible image endpoint, uploads the result to OSS, attaches it to the draft gallery, updates `source_raw.slot_images`, and returns public image URLs for ChatGPT to review. If the image is not good, call the same tool again with an improved prompt or different `reference_urls` / `reference_image_indexes`.
