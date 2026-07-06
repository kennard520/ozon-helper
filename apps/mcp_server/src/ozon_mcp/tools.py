from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import re
import tempfile
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from mcp.types import CallToolResult, ImageContent, TextContent
from ozon_common.oss import OssClient
from ozon_mcp.runtime import (
    call_tool,
    compact_draft,
    default_user_id,
    draft_ids_for_scope,
    fail,
    ok,
    run_as_user,
    unwrap_draft,
    variant_group_from_draft,
)

CHATGPT_TOOL_NAMES = frozenset(
    {
        "health",
        "list_drafts",
        "get_draft",
        "get_draft_images_for_review",
        "get_variant_group",
        "chatgpt_get_product_context",
        "chatgpt_get_next_variant_work_item",
        "chatgpt_save_variant_features",
        "chatgpt_save_understanding",
        "chatgpt_save_listing",
        "chatgpt_save_image_plan",
        "chatgpt_save_rich_content",
        "chatgpt_attach_image_url",
        "create_chatgpt_image_tasks",
        "list_chatgpt_image_tasks",
        "get_next_chatgpt_image_task",
        "openai_generate_product_image",
        "update_draft",
        "search_category",
        "get_category_attributes",
        "search_attribute_values",
        "check_required",
        "get_ozon_analytics_context",
        "chatgpt_save_optimization_notes",
        "product_status",
        "publish_preflight",
        "publish_preview",
    }
)

_IMAGE_TARGET_KEY = "mcp_chatgpt_image_target"
_IMAGE_TASK_INDEX_KEY = "mcp_chatgpt_image_task_index"
_IMAGE_TASKS_SOURCE_KEY = "chatgpt_image_tasks"
_OPTIMIZATION_NOTES_KEY = "mcp_chatgpt_optimization_notes"
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _result_draft_id(result: dict[str, Any], fallback: int) -> int:
    draft = unwrap_draft(result.get("draft") if isinstance(result, dict) else None)
    try:
        return int((draft or {}).get("id") or fallback)
    except (TypeError, ValueError):
        return int(fallback)


def _run_non_publish_pipeline(
    app,
    draft_id: int,
    *,
    image_target: int = 10,
    submit_image_job: bool = True,
    make_rich: bool = True,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def step(name: str, fn):
        try:
            result = fn()
            steps.append({"step": name, "ok": True, "result": result})
            return result
        except Exception as exc:  # noqa: BLE001 - workflow should report partial progress.
            item = {"step": name, "ok": False, "error": str(exc)}
            steps.append(item)
            errors.append(item)
            if not continue_on_error:
                raise
            return None

    step("understand", lambda: app.understand_draft(draft_id))
    listing = step("generate_listing", lambda: app.ai_generate(draft_id))
    if isinstance(listing, dict) and listing.get("mode") == "draft":
        step("apply_ai_proposal", lambda: app.apply_ai_proposal(draft_id))
    step("design_image_plan", lambda: app.design_image_plan(draft_id, target=image_target))
    if submit_image_job:
        step("submit_generate_images", lambda: app.submit_gen_job(draft_id, image_target))
    if make_rich:
        step("make_rich_content", lambda: app.make_rich_content(draft_id))
    required = step("check_required", lambda: app.required_check(draft_id, "ZH_HANS"))
    preflight = step("publish_preflight", lambda: app.publish_preflight(draft_id))
    pipeline = step("pipeline", lambda: app.draft_pipeline(draft_id))
    current = app.store.get_draft(draft_id)
    return {
        "ok": not errors,
        "draft_id": draft_id,
        "draft": compact_draft(current),
        "steps": steps,
        "errors": errors,
        "required": required,
        "preflight": preflight,
        "pipeline": pipeline,
        "note": "No publish action was executed.",
    }


def _draft_source_raw(draft: dict[str, Any] | None) -> dict[str, Any]:
    draft = unwrap_draft(draft)
    source_raw = (draft or {}).get("source_raw")
    return dict(source_raw) if isinstance(source_raw, dict) else {}


def _save_source_raw(app, draft_id: int, source_raw: dict[str, Any]) -> dict[str, Any]:
    result = app.update_draft(int(draft_id), {"source_raw": source_raw})
    return unwrap_draft(result) or app.store.get_draft(int(draft_id))


def _save_image_target(app, target: dict[str, Any]) -> dict[str, Any]:
    app.store.save_settings({_IMAGE_TARGET_KEY: target})
    return target


def _get_image_target(app) -> dict[str, Any]:
    target = (app.store.get_settings() or {}).get(_IMAGE_TARGET_KEY)
    return dict(target) if isinstance(target, dict) else {}


def _get_image_task_index(app) -> dict[str, Any]:
    index = (app.store.get_settings() or {}).get(_IMAGE_TASK_INDEX_KEY)
    return dict(index) if isinstance(index, dict) else {}


def _save_image_task_index(app, index: dict[str, Any]) -> dict[str, Any]:
    app.store.save_settings({_IMAGE_TASK_INDEX_KEY: index})
    return index


def _slug(value: Any, *, max_len: int = 28) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return (text or "slot")[:max_len].strip("-") or "slot"


def _variant_fingerprint(source_raw: dict[str, Any]) -> str:
    raw = str(source_raw.get("variant_group") or source_raw.get("variant_key") or "").strip()
    if not raw:
        return ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _task_file_name(draft_id: int, slot_id: str, seq: int, source_raw: dict[str, Any], ext: str = "png") -> str:
    variant = _variant_fingerprint(source_raw)
    variant_part = f"_v{variant}" if variant else ""
    token = uuid.uuid4().hex[:10]
    return f"ozon_d{int(draft_id)}{variant_part}_s{_slug(slot_id)}_{seq:03d}_{token}.{_slug(ext, max_len=8)}"


def _image_tasks(source_raw: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = source_raw.get(_IMAGE_TASKS_SOURCE_KEY)
    return [dict(t) for t in tasks] if isinstance(tasks, list) else []


def _set_image_tasks(source_raw: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    source_raw[_IMAGE_TASKS_SOURCE_KEY] = tasks


def _find_task(tasks: list[dict[str, Any]], *, task_id: str | None = None, filename: str | None = None) -> dict[str, Any] | None:
    filename_l = (filename or "").strip().lower()
    for task in tasks:
        if task_id and str(task.get("task_id") or "") == str(task_id):
            return task
        if filename_l and str(task.get("file_name") or "").strip().lower() == filename_l:
            return task
    return None


def _index_image_tasks(app, draft_id: int, tasks: list[dict[str, Any]]) -> None:
    index = _get_image_task_index(app)
    for task in tasks:
        file_name = str(task.get("file_name") or "").strip()
        if not file_name:
            continue
        index[file_name.lower()] = {
            "draft_id": int(draft_id),
            "task_id": str(task.get("task_id") or ""),
            "slot_id": str(task.get("slot_id") or ""),
            "image_type": str(task.get("image_type") or ""),
            "status": str(task.get("status") or ""),
            "updated_at": time.time(),
        }
    _save_image_task_index(app, index)


def _create_image_tasks_for_draft(
    app,
    draft_id: int,
    plan: list[dict[str, Any]],
    *,
    replace: bool = True,
    default_ext: str = "png",
) -> dict[str, Any]:
    draft = unwrap_draft(app.get_draft(int(draft_id)))
    if not draft:
        raise KeyError(f"draft {draft_id} not found")
    source_raw = _draft_source_raw(draft)
    existing = [] if replace else _image_tasks(source_raw)
    used_names = {str(t.get("file_name") or "").lower() for t in existing if t.get("file_name")}
    now = time.time()
    new_tasks: list[dict[str, Any]] = []
    start = len(existing) + 1
    for offset, item in enumerate(plan or [], start=start):
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or item.get("id") or item.get("slot") or f"slot_{offset:02d}")
        image_type = str(item.get("image_type") or item.get("type") or item.get("title") or slot_id)
        prompt = str(item.get("prompt") or item.get("image_prompt") or item.get("description") or "").strip()
        file_name = str(item.get("file_name") or "").strip()
        if not file_name:
            file_name = _task_file_name(int(draft_id), slot_id, offset, source_raw, default_ext)
        while file_name.lower() in used_names:
            file_name = _task_file_name(int(draft_id), slot_id, offset, source_raw, default_ext)
        used_names.add(file_name.lower())
        task_id = str(item.get("task_id") or f"img_{int(draft_id)}_{offset:03d}_{uuid.uuid4().hex[:10]}")
        new_tasks.append(
            {
                "task_id": task_id,
                "draft_id": int(draft_id),
                "variant_group": str(source_raw.get("variant_group") or ""),
                "slot_id": slot_id,
                "image_type": image_type,
                "prompt": prompt,
                "file_name": file_name,
                "status": "pending",
                "order": offset,
                "created_at": now,
                "updated_at": now,
                "source": "chatgpt",
            }
        )
    tasks = existing + new_tasks
    _set_image_tasks(source_raw, tasks)
    flow = source_raw.get("chatgpt_flow") if isinstance(source_raw.get("chatgpt_flow"), dict) else {}
    flow = dict(flow or {})
    flow.update({"status": "image_tasks_created", "updated_at": now})
    source_raw["chatgpt_flow"] = flow
    updated = _save_source_raw(app, int(draft_id), source_raw)
    _index_image_tasks(app, int(draft_id), tasks)
    return {
        "draft_id": int(draft_id),
        "created": len(new_tasks),
        "total": len(tasks),
        "tasks": tasks,
        "draft": compact_draft(updated),
    }


def _resolve_task_target(app, filename: str | None) -> dict[str, Any]:
    name = str(filename or "").strip().lower()
    if not name:
        return {}
    target = _get_image_task_index(app).get(name)
    return dict(target) if isinstance(target, dict) else {}


def _mark_image_task_uploaded(
    app,
    draft_id: int,
    *,
    task_id: str | None,
    filename: str | None,
    image_url: str,
    actual_filename: str | None = None,
) -> dict[str, Any]:
    draft = unwrap_draft(app.get_draft(int(draft_id)))
    source_raw = _draft_source_raw(draft)
    tasks = _image_tasks(source_raw)
    task = _find_task(tasks, task_id=task_id, filename=filename)
    if not task:
        return {"task_found": False}
    now = time.time()
    task["status"] = "uploaded"
    task["image_url"] = image_url
    task["uploaded_at"] = now
    task["actual_file_name"] = actual_filename or filename or task.get("file_name")
    task["updated_at"] = now
    if all(str(t.get("status") or "") in {"uploaded", "skipped"} for t in tasks):
        flow = source_raw.get("chatgpt_flow") if isinstance(source_raw.get("chatgpt_flow"), dict) else {}
        flow = dict(flow or {})
        flow.update({"status": "completed", "completed_at": now})
        source_raw["chatgpt_flow"] = flow
    _set_image_tasks(source_raw, tasks)
    _save_source_raw(app, int(draft_id), source_raw)
    _index_image_tasks(app, int(draft_id), tasks)
    return {"task_found": True, "task": task}


def _guess_ext(filename: str | None, content_type: str | None = None, default: str = "png") -> str:
    name = str(filename or "")
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in {"png", "jpg", "jpeg", "webp", "heic"}:
            return "jpg" if ext == "jpeg" else ext
    guessed = mimetypes.guess_extension(str(content_type or "").split(";", 1)[0].strip())
    if guessed:
        return guessed.lstrip(".").lower().replace("jpeg", "jpg")
    return default


def _write_temp_image(data: bytes, *, ext: str = "png") -> str:
    fd, path = tempfile.mkstemp(prefix="ozon-mcp-img-", suffix=f".{_slug(ext, max_len=8)}")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return path


def _download_image_url(url: str, *, timeout: int = 120) -> tuple[bytes, str]:
    req = urllib.request.Request(str(url), headers={"User-Agent": "ozon-mcp/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        data = resp.read()
        ext = _guess_ext(str(url).split("?", 1)[0], resp.headers.get("content-type"))
        return data, ext


def _image_mime(ext: str | None) -> str:
    ext = str(ext or "png").lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    if ext in {"png", "jpeg", "webp", "gif"}:
        return f"image/{ext}"
    return "image/png"


def _download_image_url_limited(url: str, *, timeout: int = 120, max_bytes: int = 5_000_000) -> tuple[bytes, str]:
    req = urllib.request.Request(str(url), headers={"User-Agent": "ozon-mcp/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"image is too large ({content_length} bytes)")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"image is too large (>{max_bytes} bytes)")
            chunks.append(chunk)
        ext = _guess_ext(str(url).split("?", 1)[0], resp.headers.get("content-type"))
        return b"".join(chunks), ext


def _read_image_src(app, src: str, *, max_bytes: int = 5_000_000) -> tuple[bytes, str]:
    text = str(src or "").strip()
    if not text:
        raise ValueError("empty image source")
    if text.startswith(("http://", "https://")):
        return _download_image_url_limited(text, max_bytes=max_bytes)
    path = _local_image_path(app, text)
    size = os.path.getsize(path)
    if size > max_bytes:
        raise ValueError(f"image is too large ({size} bytes)")
    with open(path, "rb") as handle:
        return handle.read(), _guess_ext(path)


def _direct_oss_url(url: str, settings: dict[str, Any]) -> str:
    try:
        from webui.media_rehost import public_oss_url  # noqa: PLC0415

        return public_oss_url(url, settings)
    except Exception:  # noqa: BLE001
        return str(url or "")


def _is_direct_or_public_oss_url(url: str, settings: dict[str, Any]) -> bool:
    u = str(url or "").strip()
    if not u:
        return False
    bucket = str((settings or {}).get("oss_bucket") or "").strip()
    endpoint = str((settings or {}).get("oss_endpoint") or "").strip().replace("https://", "").replace("http://", "").rstrip("/")
    public_base = str((settings or {}).get("oss_public_base") or "").strip().rstrip("/")
    direct_base = f"https://{bucket}.{endpoint}" if bucket and endpoint else ""
    return bool((public_base and u.startswith(public_base + "/")) or (direct_base and u.startswith(direct_base + "/")))


def _rewrite_urls(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_rewrite_urls(item, mapping) for item in value]
    if isinstance(value, dict):
        return {_rewrite_urls(k, mapping) if isinstance(k, str) else k: _rewrite_urls(v, mapping) for k, v in value.items()}
    return value


def _ensure_review_images_on_oss(app, draft: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from webui import media as _media  # noqa: PLC0415

    settings = app.store.get_settings() or {}
    oss = OssClient(settings, local_reader=_media.read_media_bytes)
    if not oss.configured():
        return entries, {"enabled": False, "reason": "OSS is not configured", "uploaded": 0, "failed": 0}

    mapping: dict[str, str] = {}
    uploaded = 0
    failed = 0
    out: list[dict[str, Any]] = []
    for entry in entries:
        original = str(entry.get("url") or "").strip()
        if not original:
            continue
        try:
            if _is_direct_or_public_oss_url(original, settings):
                oss_url = _direct_oss_url(original, settings)
            else:
                oss_url = _direct_oss_url(oss.upload_remote(original), settings)
                uploaded += int(oss_url != original)
            if oss_url != original:
                mapping[original] = oss_url
            out.append({**entry, "original_url": original, "url": oss_url, "review_source": "oss"})
        except Exception as exc:  # noqa: BLE001
            failed += 1
            out.append({**entry, "original_url": original, "review_source": "original", "oss_error": str(exc)})

    if mapping:
        source_raw = _rewrite_urls(_draft_source_raw(draft), mapping)
        images = [mapping.get(str(u), u) for u in list(draft.get("images") or [])]
        app.update_draft(int(draft["id"]), {"images": images, "source_raw": source_raw, "media_status": "done"})

    return out, {"enabled": True, "uploaded": uploaded, "failed": failed, "mapping": mapping}


def _local_image_path(app, src: str) -> str:
    if hasattr(app, "_local_image_path"):
        return app._local_image_path(src)
    data, ext = _download_image_url(src)
    return _write_temp_image(data, ext=ext)


def _attach_image_bytes(
    app,
    draft_id: int,
    data: bytes,
    *,
    filename: str = "generated.png",
    slot_id: str | None = None,
    image_type: str = "generated",
    task_id: str | None = None,
    file_name: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    if not data:
        raise ValueError("generated image data is empty")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ValueError("generated image is too large (>20MB)")
    ext = _guess_ext(filename)
    oss = OssClient(app.store.get_settings())
    if not oss.configured():
        raise RuntimeError("OSS is not configured")
    url = oss.upload_bytes(data, ext)
    draft = unwrap_draft(app.get_draft(int(draft_id)))
    if not draft:
        raise KeyError(f"draft {draft_id} not found")
    source_raw = _draft_source_raw(draft)
    images = list((draft or {}).get("images") or [])
    if url not in images:
        images.append(url)
    types = source_raw.get("image_types") if isinstance(source_raw.get("image_types"), dict) else {}
    types = dict(types or {})
    types[url] = image_type or "generated"
    source_raw["image_types"] = types
    if slot_id:
        slot_images = source_raw.get("slot_images") if isinstance(source_raw.get("slot_images"), dict) else {}
        slot_images = dict(slot_images or {})
        slot_images[str(slot_id)] = url
        source_raw["slot_images"] = slot_images
    generated = source_raw.get("chatgpt_generated_images") if isinstance(source_raw.get("chatgpt_generated_images"), list) else []
    generated = list(generated or [])
    generated.append(
        {
            "url": url,
            "slot_id": str(slot_id or ""),
            "image_type": image_type or "generated",
            "task_id": str(task_id or ""),
            "file_name": str(file_name or filename or ""),
            "prompt": str(prompt or ""),
            "created_at": time.time(),
        }
    )
    source_raw["chatgpt_generated_images"] = generated[-100:]
    try:
        app.store.add_draft_image(int(draft_id), url, type=image_type or "generated", source="chatgpt-api", in_gallery=1)
    except Exception:  # noqa: BLE001
        pass
    result = app.update_draft(int(draft_id), {"images": images, "source_raw": source_raw, "media_status": "done"})
    task_update = _mark_image_task_uploaded(
        app,
        int(draft_id),
        task_id=task_id or None,
        filename=file_name or filename,
        image_url=url,
        actual_filename=filename,
    )
    return {
        "url": url,
        "bytes": len(data),
        "slot_id": str(slot_id or ""),
        "image_type": image_type or "generated",
        "task_update": task_update,
        "draft": compact_draft(unwrap_draft(result)),
    }


def _analytics_dates(date_from: str | None, date_to: str | None, days: int = 14) -> tuple[str, str]:
    days = min(90, max(1, int(days or 14)))
    today = datetime.now(timezone(timedelta(hours=8))).date()
    end = today - timedelta(days=1)
    if date_to:
        end = datetime.strptime(str(date_to), "%Y-%m-%d").date()
    start = end - timedelta(days=days - 1)
    if date_from:
        start = datetime.strptime(str(date_from), "%Y-%m-%d").date()
    if start > end:
        start = end
    return start.isoformat(), end.isoformat()


def _all_store_settings(app, store_client_id: str | None) -> list[dict[str, Any]] | None:
    if store_client_id:
        return None
    stores = (app.store.get_settings() or {}).get("ozon_stores") or []
    if not isinstance(stores, list) or len(stores) < 2:
        return None
    out: list[dict[str, Any]] = []
    for store in stores:
        cid = str((store or {}).get("client_id") or "").strip()
        if not cid:
            continue
        try:
            out.append(app._settings_for_store(cid))
        except ValueError:
            continue
    return out or None


def _analytics_settings(app, store_client_id: str | None) -> dict[str, Any]:
    if store_client_id:
        return app._settings_for_store(store_client_id)
    return app.store.get_settings()


def _row_sku_key(row: dict[str, Any]) -> str:
    sku = str(row.get("sku") or "").strip()
    store = str(row.get("store") or "").strip()
    return f"{store}:{sku}" if store and store != "all" else sku


def _compact_dashboard(result: dict[str, Any], *, top_skus: int) -> dict[str, Any]:
    rows = list(result.get("rows") or [])[: max(1, min(100, int(top_skus or 20)))]
    return {
        "store": result.get("store"),
        "date_from": result.get("date_from"),
        "date_to": result.get("date_to"),
        "degraded": bool(result.get("degraded")),
        "grand_total": result.get("grand_total") or {},
        "top_rows": rows,
        "top_sku_keys": [_row_sku_key(r) for r in rows],
    }


def _compact_traffic(result: dict[str, Any], *, sku_keys: set[str], max_rows: int = 500) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in result.get("rows") or []:
        item = dict(row)
        key = _row_sku_key(item)
        if sku_keys and key not in sku_keys and str(item.get("sku") or "") not in sku_keys:
            continue
        rows.append(item)
        if len(rows) >= max_rows:
            break
    return {
        "store": result.get("store"),
        "date_from": result.get("date_from"),
        "date_to": result.get("date_to"),
        "rows": rows,
        "truncated": len(rows) >= max_rows,
    }


def _compact_keywords(result: dict[str, Any], *, sku_keys: set[str], per_sku_limit: int = 10) -> dict[str, Any]:
    by_sku = result.get("by_sku") or {}
    compact: dict[str, list[dict[str, Any]]] = {}
    for key, items in by_sku.items():
        key_s = str(key)
        plain_sku = key_s.split(":", 1)[-1]
        if sku_keys and key_s not in sku_keys and plain_sku not in sku_keys:
            continue
        compact[key_s] = list(items or [])[: max(1, min(30, int(per_sku_limit or 10)))]
    return {
        "store": result.get("store"),
        "date_from": result.get("date_from"),
        "date_to": result.get("date_to"),
        "requested_date_from": result.get("requested_date_from"),
        "requested_date_to": result.get("requested_date_to"),
        "date_adjusted": bool(result.get("date_adjusted")),
        "by_sku": compact,
    }


def _draft_sku(app, draft: dict[str, Any] | None, store_client_id: str | None) -> str:
    if not draft:
        return ""
    source_raw = _draft_source_raw(draft)
    for key in ("sku", "ozon_sku", "product_sku"):
        value = str(source_raw.get(key) or draft.get(key) or "").strip()
        if value:
            return value
    offer_id = str(draft.get("offer_id") or "").strip()
    if not offer_id:
        return ""
    try:
        from webui.ozon_client_adapter import get_ozon_info  # noqa: PLC0415

        info = get_ozon_info(_analytics_settings(app, store_client_id), [offer_id]).get(offer_id) or {}
        return str(info.get("sku") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _save_variant_features(app, draft_id: int, features: dict[str, Any]) -> dict[str, Any]:
    draft = unwrap_draft(app.get_draft(int(draft_id)))
    if not draft:
        raise KeyError(f"draft {draft_id} not found")
    source_raw = _draft_source_raw(draft)
    data = dict(features or {})
    source_raw["features"] = data
    source_raw["understanding"] = data
    workflow = source_raw.get("workflow_status") if isinstance(source_raw.get("workflow_status"), dict) else {}
    workflow = dict(workflow or {})
    workflow["features"] = {"status": "done", "source": "chatgpt", "updated_at": time.time()}
    source_raw["workflow_status"] = workflow
    patch = {"source_raw": source_raw}
    try:
        patch.update(app._autofill_from_understanding(draft, data))
    except Exception:  # noqa: BLE001
        pass
    result = app.update_draft(int(draft_id), patch)
    return {"draft_id": int(draft_id), "draft": compact_draft(unwrap_draft(result))}


def _variant_work_status(draft: dict[str, Any]) -> dict[str, Any]:
    source_raw = _draft_source_raw(draft)
    generated_images = source_raw.get("chatgpt_generated_images") if isinstance(source_raw.get("chatgpt_generated_images"), list) else []
    slot_images = source_raw.get("slot_images") if isinstance(source_raw.get("slot_images"), dict) else {}
    attrs = draft.get("attributes") or []
    listing_missing = [
        name
        for name, done in {
            "ozon_title": bool(str(draft.get("ozon_title") or "").strip()),
            "description": bool(str(draft.get("description") or "").strip()),
            "category_id": bool(str(draft.get("category_id") or "").strip()),
            "type_id": bool(str(draft.get("type_id") or "").strip()),
            "attributes": bool(attrs),
        }.items()
        if not done
    ]
    return {
        "features": bool(source_raw.get("features") or source_raw.get("understanding")),
        "listing": not listing_missing,
        "image_plan": bool(source_raw.get("image_plan")),
        "images": bool(generated_images or slot_images),
        "rich_content": bool(source_raw.get("rich_content_json")),
        "missing": {"listing": listing_missing},
    }


def _stage_done(status: dict[str, Any], stage: str) -> bool:
    if stage == "any":
        return all(bool(status.get(key)) for key in ("features", "listing", "image_plan", "images", "rich_content"))
    return bool(status.get(stage))


def _next_variant_action(status: dict[str, Any], stage: str) -> dict[str, str]:
    if stage == "features" or (stage == "any" and not status["features"]):
        return {
            "tool": "chatgpt_save_variant_features",
            "description": "First call get_draft_images_for_review for this draft_id to visually inspect product and detail images, then generate variant-specific product features and save them with this tool.",
        }
    if stage == "listing" or (stage == "any" and not status["listing"]):
        missing = ", ".join((status.get("missing") or {}).get("listing") or [])
        return {
            "tool": "chatgpt_save_listing",
            "description": "Generate and save title, description, category_id, type_id, category_path, attributes, and commercial fields for this single variant."
            + (f" Missing now: {missing}." if missing else ""),
        }
    if stage == "image_plan" or (stage == "any" and not status["image_plan"]):
        return {
            "tool": "chatgpt_save_image_plan",
            "description": "Save the image plan for this single variant before generating images.",
        }
    if stage == "images" or (stage == "any" and not status["images"]):
        return {
            "tool": "openai_generate_product_image",
            "description": "Use the synchronous image API for this single variant; do not use download image tasks for multi-variant loops.",
        }
    if stage == "rich_content" or (stage == "any" and not status["rich_content"]):
        return {
            "tool": "chatgpt_save_rich_content",
            "description": "Save rich content JSON for this single variant.",
        }
    return {"tool": "product_status", "description": "This variant has no pending stage for the requested filter."}


def register_tools(mcp, *, include_tools: set[str] | frozenset[str] | None = None) -> None:
    def tool():
        def _decorator(fn):
            if include_tools is None or fn.__name__ in include_tools:
                return mcp.tool()(fn)
            return fn

        return _decorator

    @tool()
    def health() -> dict[str, Any]:
        """Check ozon-helper MCP backend status and important configuration flags."""

        def _run(app):
            settings = app.store.get_settings() or {}
            return ok(
                {
                    "name": "ozon-helper",
                    "default_user_id": default_user_id(),
                    "configured": {
                        "ozon_api": bool(settings.get("ozon_client_id") and settings.get("ozon_api_key")),
                        "oss": bool(settings.get("oss_endpoint") and settings.get("oss_bucket")),
                        "ai_text": bool((settings.get("ai_text") or {}).get("key") or settings.get("agnes_api_key")),
                        "ai_image": bool((settings.get("ai_image") or {}).get("key") or settings.get("agnes_api_key")),
                        "ai_multimodal": bool((settings.get("ai_multimodal") or {}).get("key") or settings.get("agnes_api_key")),
                    },
                }
            )

        return call_tool(_run)
    @tool()
    def list_drafts(
        status: str = "all",
        page: int = 1,
        page_size: int = 10,
        store_client_id: str | None = None,
    ) -> dict[str, Any]:
        """List product drafts. Use this to find recent draft IDs before editing or generating content."""
        page = max(1, int(page or 1))
        page_size = min(50, max(1, int(page_size or 10)))

        def _run(app):
            result = app.list_drafts(status=status, page=page, page_size=page_size, store_client_id=store_client_id)
            drafts = result.get("drafts") or result.get("items") or []
            if isinstance(drafts, list):
                result = dict(result)
                result["drafts"] = [compact_draft(d) for d in drafts]
            return ok(result)

        return call_tool(_run)

    @tool()
    def get_draft(draft_id: int, compact: bool = True) -> dict[str, Any]:
        """Get a single draft. Set compact=false when the full stored draft is needed."""

        def _run(app):
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            return ok({"draft": compact_draft(draft) if compact else draft})

        return call_tool(_run)

    @tool()
    def get_draft_images_for_review(
        draft_id: int,
        indexes: list[int] | None = None,
        max_images: int = 12,
        max_bytes_per_image: int = 4_000_000,
        prefer_oss: bool = True,
    ) -> CallToolResult:
        """Return actual draft image content so ChatGPT can visually review Ozon image compliance. Prefer OSS URLs by default."""
        max_images = max(1, min(24, int(max_images or 12)))
        max_bytes_per_image = max(200_000, min(8_000_000, int(max_bytes_per_image or 4_000_000)))

        def _run(app) -> CallToolResult:
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            if not draft:
                raise KeyError(f"draft {draft_id} not found")
            source_raw = _draft_source_raw(draft)
            image_types = source_raw.get("image_types") if isinstance(source_raw.get("image_types"), dict) else {}
            raw_images = []
            for item in list((draft or {}).get("images") or []):
                raw_images.append({"url": item, "source": "images"} if not isinstance(item, dict) else {**item, "source": item.get("source") or "images"})
            for item in list((draft or {}).get("materials") or []):
                raw_images.append({"url": item, "source": "materials"} if not isinstance(item, dict) else {**item, "source": item.get("source") or "materials"})
            entries: list[dict[str, Any]] = []
            seen: set[str] = set()
            for pos, item in enumerate(raw_images):
                url = str(item.get("url") if isinstance(item, dict) else item or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                entries.append(
                    {
                        "index": pos,
                        "url": url,
                        "type": str((image_types or {}).get(url) or (item.get("type") if isinstance(item, dict) else "") or ""),
                        "source": str(item.get("source") if isinstance(item, dict) else "" or ""),
                    }
                )
            if indexes:
                wanted = {int(i) for i in indexes}
                entries = [entry for entry in entries if int(entry["index"]) in wanted]
            entries = entries[:max_images]
            oss_status: dict[str, Any] = {"enabled": False}
            if prefer_oss and entries:
                entries, oss_status = _ensure_review_images_on_oss(app, draft, entries)

            content: list[TextContent | ImageContent] = [
                TextContent(
                    type="text",
                    text=(
                        f"Draft {draft_id} image review payload. "
                        "Visually inspect the following images for Chinese text, watermarks, logos, unsafe claims, "
                        "wrong product, bad cropping, and Ozon listing compliance."
                    ),
                )
            ]
            meta_images: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for entry in entries:
                try:
                    data, ext = _read_image_src(app, entry["url"], max_bytes=max_bytes_per_image)
                    mime = _image_mime(ext)
                    content.append(
                        TextContent(
                            type="text",
                            text=(
                                f"Image #{entry['index']} type={entry.get('type') or 'unknown'} "
                                f"source={entry.get('review_source') or 'original'} url={entry['url']}"
                            ),
                        )
                    )
                    content.append(ImageContent(type="image", data=base64.b64encode(data).decode("ascii"), mimeType=mime))
                    meta_images.append({**entry, "mime_type": mime, "bytes": len(data), "included": True})
                except Exception as exc:  # noqa: BLE001
                    error = {**entry, "included": False, "error": str(exc)}
                    errors.append(error)
                    meta_images.append(error)

            if not meta_images:
                content.append(TextContent(type="text", text="No images were found or selected for this draft."))

            return CallToolResult(
                content=content,
                structuredContent={
                    "ok": not errors,
                    "draft_id": int(draft_id),
                    "image_count": len(raw_images),
                    "returned_count": len([img for img in meta_images if img.get("included")]),
                    "images": meta_images,
                    "oss": oss_status,
                    "errors": errors,
                },
                isError=False,
            )

        try:
            return run_as_user(_run)
        except Exception as exc:  # noqa: BLE001
            return CallToolResult(
                content=[TextContent(type="text", text=f"Failed to load draft images: {exc}")],
                structuredContent={"ok": False, "draft_id": int(draft_id), "error": str(exc)},
                isError=True,
            )

    @tool()
    def get_variant_group(draft_id: int) -> dict[str, Any]:
        """Get all variants in the selected draft's variant group."""

        def _run(app):
            result = app.variant_group_siblings(int(draft_id))
            return ok(result)

        return call_tool(_run)

    @tool()
    def chatgpt_get_product_context(
        draft_id: int,
        scope: Literal["group", "single"] = "group",
        include_full: bool = True,
    ) -> dict[str, Any]:
        """Read product data for ChatGPT itself to analyze. This does not run backend AI or workers."""

        def _one(app, did: int) -> dict[str, Any]:
            draft = unwrap_draft(app.get_draft(int(did)))
            if not draft:
                raise KeyError(f"draft {did} not found")
            data = draft if include_full else compact_draft(draft)
            out = {"draft_id": did, "draft": data}
            cat = int(str(draft.get("category_id") or "0") or 0)
            typ = int(str(draft.get("type_id") or "0") or 0)
            if cat and typ:
                try:
                    out["category_attributes"] = app.category_attributes(cat, typ, "ZH_HANS")
                except Exception as exc:  # noqa: BLE001
                    out["category_attributes_error"] = str(exc)
            return out

        def _run(app):
            if scope == "single":
                return ok(_one(app, int(draft_id)))
            base = unwrap_draft(app.get_draft(int(draft_id)))
            group = variant_group_from_draft(base)
            if not group:
                return ok({"variant_group": "", "count": 1, "items": [_one(app, int(draft_id))]})
            siblings = app.variant_group_siblings(int(draft_id))
            items = [_one(app, int(v.get("id"))) for v in (siblings.get("variants") or [])]
            return ok({"variant_group": group, "count": len(items), "items": items})

        return call_tool(_run)

    @tool()
    def chatgpt_get_next_variant_work_item(
        draft_id: int,
        stage: Literal["any", "features", "listing", "image_plan", "images", "rich_content"] = "features",
        include_full: bool = True,
    ) -> dict[str, Any]:
        """Get the next variant that still needs ChatGPT work. Multi-variant processing should loop over this tool."""

        def _run(app):
            group, ids = draft_ids_for_scope(app, int(draft_id), "group")
            items: list[dict[str, Any]] = []
            selected: dict[str, Any] | None = None
            for did in ids:
                draft = unwrap_draft(app.get_draft(int(did)))
                if not draft:
                    continue
                status = _variant_work_status(draft)
                item = {
                    "draft_id": int(did),
                    "status": status,
                    "done": _stage_done(status, stage),
                    "draft": draft if include_full else compact_draft(draft),
                }
                items.append(item)
                if selected is None and not item["done"]:
                    selected = item
            if selected is None:
                return ok(
                    {
                        "draft_id": int(draft_id),
                        "variant_group": group,
                        "stage": stage,
                        "done": True,
                        "count": len(items),
                        "items": items,
                        "message": "All variants are complete for the requested stage.",
                    }
                )
            action = _next_variant_action(selected["status"], stage)
            return ok(
                {
                    "draft_id": selected["draft_id"],
                    "requested_draft_id": int(draft_id),
                    "variant_group": group,
                    "stage": stage,
                    "done": False,
                    "item": selected,
                    "count": len(items),
                    "items": items,
                    "next_action": action["tool"],
                    "next_action_description": action["description"],
                    "loop_rule": "Process only this returned draft_id, call the next_action tool, then call chatgpt_get_next_variant_work_item again until done=true.",
                    "visual_rule": "Before feature, listing, image plan, or image generation work, call get_draft_images_for_review for the returned draft_id so product photos and detail images are actually visible to ChatGPT.",
                    "image_rule": "For images, call openai_generate_product_image synchronously for the returned draft_id. Do not use create_chatgpt_image_tasks/get_next_chatgpt_image_task for multi-variant loops.",
                }
            )

        return call_tool(_run)

    @tool()
    def chatgpt_save_variant_features(draft_id: int, features: dict[str, Any]) -> dict[str, Any]:
        """Save ChatGPT-generated variant features to one draft. Use this while looping multi-variant groups."""

        def _run(app):
            return ok(_save_variant_features(app, int(draft_id), features or {}))

        return call_tool(_run)

    @tool()
    def chatgpt_save_understanding(draft_id: int, understanding: dict[str, Any]) -> dict[str, Any]:
        """Save ChatGPT's own product understanding to the draft. This does not call backend multimodal AI."""

        def _run(app):
            return ok(_save_variant_features(app, int(draft_id), understanding or {}))

        return call_tool(_run)

    @tool()
    def chatgpt_save_listing(
        draft_id: int,
        ozon_title: str | None = None,
        description: str | None = None,
        category_id: int | None = None,
        type_id: int | None = None,
        category_path: str | None = None,
        attributes: list[dict[str, Any]] | None = None,
        brand_name: str | None = None,
        price: str | None = None,
        old_price: str | None = None,
        weight_g: int | None = None,
        length_mm: int | None = None,
        width_mm: int | None = None,
        height_mm: int | None = None,
    ) -> dict[str, Any]:
        """Save listing fields generated by ChatGPT itself. This does not call backend text AI."""
        patch: dict[str, Any] = {}
        for key, value in {
            "ozon_title": ozon_title,
            "description": description,
            "category_id": category_id,
            "type_id": type_id,
            "category_path": category_path,
            "attributes": attributes,
            "brand_name": brand_name,
            "price": price,
            "old_price": old_price,
            "weight_g": weight_g,
            "length_mm": length_mm,
            "width_mm": width_mm,
            "height_mm": height_mm,
        }.items():
            if value is not None:
                patch[key] = value

        def _run(app):
            result = app.update_draft(int(draft_id), patch)
            return ok({"draft_id": int(draft_id), "draft": compact_draft(unwrap_draft(result)), "saved_fields": sorted(patch)})

        return call_tool(_run)

    @tool()
    def chatgpt_save_image_plan(draft_id: int, plan: list[dict[str, Any]]) -> dict[str, Any]:
        """Save an image plan designed by ChatGPT itself. This does not generate images."""

        def _run(app):
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            source_raw = _draft_source_raw(draft)
            source_raw["image_plan"] = list(plan or [])
            updated = _save_source_raw(app, int(draft_id), source_raw)
            return ok({"draft_id": int(draft_id), "count": len(plan or []), "draft": compact_draft(updated)})

        return call_tool(_run)

    @tool()
    def chatgpt_save_rich_content(draft_id: int, rich_content_json: dict[str, Any]) -> dict[str, Any]:
        """Save Ozon rich content JSON designed by ChatGPT itself. This does not publish."""

        def _run(app):
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            source_raw = _draft_source_raw(draft)
            source_raw["rich_content_json"] = dict(rich_content_json or {})
            workflow = source_raw.get("workflow_status") if isinstance(source_raw.get("workflow_status"), dict) else {}
            workflow = dict(workflow or {})
            workflow["rich"] = {"status": "done", "source": "chatgpt"}
            source_raw["workflow_status"] = workflow
            updated = _save_source_raw(app, int(draft_id), source_raw)
            return ok({"draft_id": int(draft_id), "draft": compact_draft(updated)})

        return call_tool(_run)

    @tool()
    def chatgpt_attach_image_url(
        draft_id: int,
        image_url: str,
        image_type: str = "generated",
        slot_id: str | None = None,
    ) -> dict[str, Any]:
        """Attach an externally generated image URL to a draft. Use after ChatGPT/user provides a reachable image URL."""

        def _run(app):
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            source_raw = _draft_source_raw(draft)
            images = list((draft or {}).get("images") or [])
            url = str(image_url or "").strip()
            if not url:
                raise ValueError("image_url required")
            if url not in images:
                images.append(url)
            types = source_raw.get("image_types") if isinstance(source_raw.get("image_types"), dict) else {}
            types = dict(types or {})
            types[url] = image_type or "generated"
            source_raw["image_types"] = types
            if slot_id:
                slot_images = source_raw.get("slot_images") if isinstance(source_raw.get("slot_images"), dict) else {}
                slot_images = dict(slot_images or {})
                slot_images[str(slot_id)] = url
                source_raw["slot_images"] = slot_images
            result = app.update_draft(int(draft_id), {"images": images, "source_raw": source_raw})
            return ok({"draft_id": int(draft_id), "draft": compact_draft(unwrap_draft(result)), "image_url": url})

        return call_tool(_run)

    @tool()
    def set_chatgpt_image_target(
        draft_id: int,
        slot_id: str = "main",
        image_type: str = "涓诲浘",
        clear_after_upload: bool = True,
        task_id: str | None = None,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the current local-download target for ChatGPT images. Use before generating/downloading an image."""

        def _run(app):
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            if not draft:
                raise KeyError(f"draft {draft_id} not found")
            target = {
                "draft_id": int(draft_id),
                "slot_id": str(slot_id or "main"),
                "image_type": str(image_type or "涓诲浘"),
                "task_id": str(task_id or ""),
                "file_name": str(file_name or ""),
                "clear_after_upload": bool(clear_after_upload),
                "created_at": time.time(),
                "draft": compact_draft(draft),
            }
            _save_image_target(app, target)
            return ok({"target": target, "message": "Now download the ChatGPT image; the local watcher will upload it to this draft/task."})

        return call_tool(_run)

    @tool()
    def get_chatgpt_image_target() -> dict[str, Any]:
        """Get the current local-download target for ChatGPT images."""

        def _run(app):
            return ok({"target": _get_image_target(app)})

        return call_tool(_run)

    @tool()
    def clear_chatgpt_image_target() -> dict[str, Any]:
        """Clear the current local-download target for ChatGPT images."""

        def _run(app):
            _save_image_target(app, {})
            return ok({"target": {}})

        return call_tool(_run)

    @tool()
    def create_chatgpt_image_tasks(
        draft_id: int,
        plan: list[dict[str, Any]],
        scope: Literal["single", "group"] = "single",
        replace: bool = True,
        default_ext: str = "png",
    ) -> dict[str, Any]:
        """Create DB-backed ChatGPT image tasks with unique file_name values for one draft or all variants in its group."""

        def _run(app):
            group, ids = draft_ids_for_scope(app, int(draft_id), scope)
            results = [
                _create_image_tasks_for_draft(app, did, plan or [], replace=bool(replace), default_ext=default_ext)
                for did in ids
            ]
            return ok(
                {
                    "draft_id": int(draft_id),
                    "scope": scope,
                    "variant_group": group,
                    "draft_ids": ids,
                    "created": sum(int(r.get("created") or 0) for r in results),
                    "total": sum(int(r.get("total") or 0) for r in results),
                    "results": results,
                    "tasks": results[0].get("tasks") if len(results) == 1 else [],
                    "next_action": "get_next_chatgpt_image_task",
                }
            )

        return call_tool(_run)

    @tool()
    def list_chatgpt_image_tasks(draft_id: int, scope: Literal["single", "group"] = "single") -> dict[str, Any]:
        """List DB-backed ChatGPT image tasks for one draft or all variants in its group."""

        def _run(app):
            group, ids = draft_ids_for_scope(app, int(draft_id), scope)
            counts: dict[str, int] = {}
            results: list[dict[str, Any]] = []
            for did in ids:
                draft = unwrap_draft(app.get_draft(int(did)))
                source_raw = _draft_source_raw(draft)
                tasks = _image_tasks(source_raw)
                local_counts: dict[str, int] = {}
                for task in tasks:
                    status = str(task.get("status") or "unknown")
                    local_counts[status] = local_counts.get(status, 0) + 1
                    counts[status] = counts.get(status, 0) + 1
                results.append(
                    {
                        "draft_id": int(did),
                        "flow": source_raw.get("chatgpt_flow") if isinstance(source_raw.get("chatgpt_flow"), dict) else {},
                        "counts": local_counts,
                        "tasks": tasks,
                    }
                )
            return ok(
                {
                    "draft_id": int(draft_id),
                    "scope": scope,
                    "variant_group": group,
                    "draft_ids": ids,
                    "counts": counts,
                    "results": results,
                    "tasks": results[0].get("tasks") if len(results) == 1 else [],
                }
            )

        return call_tool(_run)

    @tool()
    def get_next_chatgpt_image_task(
        draft_id: int,
        set_target: bool = True,
        scope: Literal["single", "group"] = "single",
    ) -> dict[str, Any]:
        """Get the next pending ChatGPT image task from one draft or its whole group and optionally set it as current upload target."""

        def _run(app):
            group, ids = draft_ids_for_scope(app, int(draft_id), scope)
            selected_did = None
            selected_task = None
            selected_draft = None
            selected_source_raw: dict[str, Any] = {}
            selected_tasks: list[dict[str, Any]] = []
            for did in ids:
                draft = unwrap_draft(app.get_draft(int(did)))
                source_raw = _draft_source_raw(draft)
                tasks = _image_tasks(source_raw)
                pending = [t for t in tasks if str(t.get("status") or "pending") in {"pending", "failed"}]
                if pending:
                    selected_did = int(did)
                    selected_task = sorted(pending, key=lambda t: int(t.get("order") or 0))[0]
                    selected_draft = draft
                    selected_source_raw = source_raw
                    selected_tasks = tasks
                    break
                if tasks and all(str(t.get("status") or "") in {"uploaded", "skipped"} for t in tasks):
                    flow = source_raw.get("chatgpt_flow") if isinstance(source_raw.get("chatgpt_flow"), dict) else {}
                    flow = dict(flow or {})
                    flow.update({"status": "completed", "completed_at": time.time()})
                    source_raw["chatgpt_flow"] = flow
                    _save_source_raw(app, int(did), source_raw)
            if selected_did is None or selected_task is None:
                return ok(
                    {
                        "draft_id": int(draft_id),
                        "scope": scope,
                        "variant_group": group,
                        "draft_ids": ids,
                        "done": True,
                        "task": None,
                        "message": "No pending image tasks.",
                    }
                )
            draft = selected_draft
            if not draft:
                raise KeyError(f"draft {selected_did} not found")
            source_raw = selected_source_raw
            tasks = selected_tasks
            task = selected_task
            target: dict[str, Any] = {}
            if set_target:
                now = time.time()
                task["status"] = "waiting_download"
                task["updated_at"] = now
                _set_image_tasks(source_raw, tasks)
                flow = source_raw.get("chatgpt_flow") if isinstance(source_raw.get("chatgpt_flow"), dict) else {}
                flow = dict(flow or {})
                flow.update({"status": "image_generating", "updated_at": now})
                source_raw["chatgpt_flow"] = flow
                _save_source_raw(app, int(selected_did), source_raw)
                _index_image_tasks(app, int(selected_did), tasks)
                target = {
                    "draft_id": int(selected_did),
                    "slot_id": str(task.get("slot_id") or "main"),
                    "image_type": str(task.get("image_type") or "generated"),
                    "task_id": str(task.get("task_id") or ""),
                    "file_name": str(task.get("file_name") or ""),
                    "clear_after_upload": True,
                    "created_at": now,
                    "draft": compact_draft(draft),
                }
                _save_image_target(app, target)
            return ok(
                {
                    "draft_id": int(selected_did),
                    "requested_draft_id": int(draft_id),
                    "scope": scope,
                    "variant_group": group,
                    "draft_ids": ids,
                    "done": False,
                    "task": task,
                    "target": target,
                    "download_file_name": task.get("file_name"),
                    "message": "Generate this image in ChatGPT, then save/download it with download_file_name when possible.",
                }
            )

        return call_tool(_run)

    @tool()
    def openai_generate_product_image(
        draft_id: int,
        prompt: str,
        mode: Literal["auto", "create", "edit"] = "auto",
        model: str | None = None,
        size: str = "1024x1536",
        quality: str | None = None,
        output_format: Literal["png", "jpeg", "webp"] = "png",
        background: str | None = None,
        n: int = 1,
        reference_urls: list[str] | None = None,
        reference_image_indexes: list[int] | None = None,
        reference_images_base64: list[str] | None = None,
        mask_url: str | None = None,
        mask_base64: str | None = None,
        slot_id: str | None = None,
        image_type: str = "generated",
        task_id: str | None = None,
        file_name: str | None = None,
        attach_to_gallery: bool = True,
        append_ozon_rules: bool = True,
    ) -> dict[str, Any]:
        """OpenAI-like image generation/editing for ChatGPT. Generated images are uploaded to OSS and attached to the draft gallery."""

        def _run(app):
            p = str(prompt or "").strip()
            if not p:
                raise ValueError("prompt required")
            draft = unwrap_draft(app.get_draft(int(draft_id)))
            if not draft:
                raise KeyError(f"draft {draft_id} not found")
            count = min(4, max(1, int(n or 1)))
            fmt = (output_format or "png").lower()
            ext = "jpg" if fmt == "jpeg" else fmt
            refs = [str(u or "").strip() for u in (reference_urls or []) if str(u or "").strip()]
            draft_images = list((draft or {}).get("images") or [])
            for idx in reference_image_indexes or []:
                try:
                    i = int(idx)
                except (TypeError, ValueError):
                    continue
                if 0 <= i < len(draft_images):
                    refs.append(str(draft_images[i]))
            refs = list(dict.fromkeys(refs))
            tmp_paths: list[str] = []
            try:
                for src in refs:
                    tmp_paths.append(_local_image_path(app, src))
                for i, raw in enumerate(reference_images_base64 or []):
                    b64 = str(raw or "").strip()
                    if not b64:
                        continue
                    if "," in b64 and b64.lower().startswith("data:"):
                        b64 = b64.split(",", 1)[1]
                    tmp_paths.append(_write_temp_image(base64.b64decode(b64, validate=True), ext="png"))
                mask_path = None
                if mask_url:
                    mask_path = _local_image_path(app, str(mask_url))
                    tmp_paths.append(mask_path)
                if mask_base64:
                    b64 = str(mask_base64 or "").strip()
                    if "," in b64 and b64.lower().startswith("data:"):
                        b64 = b64.split(",", 1)[1]
                    mask_path = _write_temp_image(base64.b64decode(b64, validate=True), ext="png")
                    tmp_paths.append(mask_path)
                actual_mode = str(mode or "auto").lower()
                if actual_mode == "auto":
                    actual_mode = "edit" if tmp_paths and any(path != mask_path for path in tmp_paths) else "create"
                if actual_mode == "edit" and not [path for path in tmp_paths if path != mask_path]:
                    raise ValueError("edit mode requires reference_urls, reference_image_indexes, or reference_images_base64")

                from ozon_common.gen_image import (  # noqa: PLC0415
                    NON_PRODUCT_RULE,
                    OZON_RU_RULE,
                    create_image,
                    edit_image,
                    images_from_response,
                )

                final_prompt = p
                if append_ozon_rules:
                    final_prompt = f"{p}\n\n{NON_PRODUCT_RULE}\n{OZON_RU_RULE}"
                cfg = app._gen_image_cfg(app.store.get_settings()) if hasattr(app, "_gen_image_cfg") else None
                if cfg is None:
                    from ozon_common.gen_image import GenImageConfig  # noqa: PLC0415

                    cfg = GenImageConfig()
                if model:
                    cfg.model = str(model)
                if actual_mode == "create":
                    response = create_image(
                        cfg,
                        final_prompt,
                        n=count,
                        size=size or "1024x1536",
                        quality=quality,
                        output_format=fmt,
                        background=background,
                    )
                else:
                    image_paths = [path for path in tmp_paths if path != mask_path]
                    response = edit_image(
                        cfg,
                        final_prompt,
                        image_paths,
                        mask_path=mask_path,
                        n=count,
                        size=size or "1024x1536",
                        quality=quality,
                        output_format=fmt,
                        background=background,
                    )
                image_bytes = images_from_response(response)
                if not image_bytes:
                    raise RuntimeError("image API returned no images")
                attached: list[dict[str, Any]] = []
                for index, data in enumerate(image_bytes):
                    filename = file_name or f"openai-image-{int(time.time())}-{index}.{ext}"
                    if attach_to_gallery:
                        attached.append(
                            _attach_image_bytes(
                                app,
                                int(draft_id),
                                data,
                                filename=filename,
                                slot_id=slot_id,
                                image_type=image_type,
                                task_id=task_id,
                                file_name=file_name,
                                prompt=p,
                            )
                        )
                    else:
                        oss = OssClient(app.store.get_settings())
                        if not oss.configured():
                            raise RuntimeError("OSS is not configured")
                        attached.append({"url": oss.upload_bytes(data, ext), "bytes": len(data)})
                latest = unwrap_draft(app.get_draft(int(draft_id)))
                return ok(
                    {
                        "draft_id": int(draft_id),
                        "mode": actual_mode,
                        "model": cfg.model,
                        "size": size,
                        "count": len(attached),
                        "images": attached,
                        "draft": compact_draft(latest),
                        "next_actions": [
                            "Review returned image URLs. If the result is not good, call openai_generate_product_image again with an improved prompt and reference_image_indexes/reference_urls."
                        ],
                    }
                )
            finally:
                for path in tmp_paths:
                    try:
                        if path and os.path.exists(path):
                            os.remove(path)
                    except OSError:
                        pass

        return call_tool(_run)

    @tool()
    def upload_chatgpt_downloaded_image(
        image_base64: str,
        filename: str = "chatgpt.png",
        draft_id: int | None = None,
        slot_id: str | None = None,
        image_type: str | None = None,
        task_id: str | None = None,
        clear_target: bool | None = None,
    ) -> dict[str, Any]:
        """Upload a locally downloaded ChatGPT image to OSS and attach it to the current or provided draft target."""

        def _run(app):
            target = _get_image_target(app)
            file_target = _resolve_task_target(app, filename)
            did = int(draft_id or target.get("draft_id") or file_target.get("draft_id") or 0)
            if did <= 0:
                raise ValueError("No draft target. Call get_next_chatgpt_image_task/set_chatgpt_image_target first, pass draft_id, or use a known task file_name.")
            tid = str(task_id or target.get("task_id") or file_target.get("task_id") or "")
            task_file_name = str(target.get("file_name") or filename or "")
            sid = str(slot_id or target.get("slot_id") or file_target.get("slot_id") or "main")
            typ = str(image_type or target.get("image_type") or file_target.get("image_type") or "generated")
            raw = str(image_base64 or "").strip()
            if "," in raw and raw.lower().startswith("data:"):
                raw = raw.split(",", 1)[1]
            data = base64.b64decode(raw, validate=True)
            if not data:
                raise ValueError("image data is empty")
            if len(data) > _MAX_UPLOAD_BYTES:
                raise ValueError("image is too large (>20MB)")
            ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
            if not ext:
                guessed = mimetypes.guess_extension(mimetypes.guess_type(filename)[0] or "") or ".png"
                ext = guessed.lstrip(".")
            oss = OssClient(app.store.get_settings())
            if not oss.configured():
                raise RuntimeError("OSS is not configured")
            url = oss.upload_bytes(data, ext)
            draft = unwrap_draft(app.get_draft(did))
            source_raw = _draft_source_raw(draft)
            images = list((draft or {}).get("images") or [])
            if url not in images:
                images.append(url)
            types = source_raw.get("image_types") if isinstance(source_raw.get("image_types"), dict) else {}
            types = dict(types or {})
            types[url] = typ
            source_raw["image_types"] = types
            slot_images = source_raw.get("slot_images") if isinstance(source_raw.get("slot_images"), dict) else {}
            slot_images = dict(slot_images or {})
            slot_images[sid] = url
            source_raw["slot_images"] = slot_images
            try:
                app.store.add_draft_image(did, url, type=typ, source="chatgpt", in_gallery=1)
            except Exception:  # noqa: BLE001
                pass
            result = app.update_draft(did, {"images": images, "source_raw": source_raw, "media_status": "done"})
            task_update = _mark_image_task_uploaded(
                app,
                did,
                task_id=tid or None,
                filename=task_file_name or filename,
                image_url=url,
                actual_filename=filename,
            )
            should_clear = bool(target.get("clear_after_upload")) if clear_target is None else bool(clear_target)
            if should_clear:
                _save_image_target(app, {})
            return ok(
                {
                    "draft_id": did,
                    "slot_id": sid,
                    "image_type": typ,
                    "url": url,
                    "task_id": tid,
                    "task_update": task_update,
                    "draft": compact_draft(unwrap_draft(result)),
                    "target_cleared": should_clear,
                }
            )

        return call_tool(_run)

    @tool()
    def create_draft_from_parsed(
        url: str,
        source_platform: str = "1688",
        data: dict[str, Any] | None = None,
        store_client_id: str | None = None,
        schema_version: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a draft from already parsed product data and image URLs."""
        parsed = dict(data or {})
        parsed["source_platform"] = source_platform
        if store_client_id:
            parsed["store_client_id"] = store_client_id
        payload = {"url": url, "schema_version": schema_version or "mcp.v1", "data": parsed}
        if store_client_id:
            payload["store_client_id"] = store_client_id

        def _run(app):
            result = app.ext_collect_parsed(payload)
            created = result.get("created") or []
            draft_id = created[0].get("id") if created and isinstance(created[0], dict) else None
            result["draft_id"] = draft_id
            result["next_actions"] = ["understand_draft", "generate_listing", "design_image_plan"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def update_draft(draft_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        """Patch draft fields such as title, description, price, dimensions, category, or attributes."""

        def _run(app):
            result = app.update_draft(int(draft_id), dict(patch or {}))
            draft = unwrap_draft(result)
            return ok({"draft_id": int(draft_id), "draft": compact_draft(draft)})

        return call_tool(_run)

    @tool()
    def understand_draft(draft_id: int, force: bool = False) -> dict[str, Any]:
        """Run multimodal product understanding for a draft and cache structured facts."""

        def _run(app):
            result = app.understand_draft(int(draft_id), force=bool(force))
            result["next_actions"] = ["generate_listing", "design_image_plan", "check_required"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def recommend_draft(draft_id: int) -> dict[str, Any]:
        """Recommend the next processing path for a draft based on source and cached understanding."""

        def _run(app):
            return ok(app.recommend(int(draft_id)))

        return call_tool(_run)

    @tool()
    def generate_listing(
        draft_id: int,
        mode: Literal["full", "copy", "category", "attributes", "async_full"] = "full",
    ) -> dict[str, Any]:
        """Generate Ozon listing content. full drafts category, text, and attributes; copy only writes title/description/tags."""

        def _run(app):
            if mode == "copy":
                result = app.ai_copy(int(draft_id))
            elif mode == "category":
                result = app.recognize_category(int(draft_id))
            elif mode == "attributes":
                result = app.ai_fill_attributes(int(draft_id))
            elif mode == "async_full":
                result = app.submit_text_job(int(draft_id))
                result["poll_tool"] = "get_text_job_status"
            else:
                result = app.ai_generate(int(draft_id))
            result["draft_id"] = int(draft_id)
            result["next_actions"] = ["apply_ai_proposal", "check_required", "design_image_plan"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def get_text_job_status(job_id: int) -> dict[str, Any]:
        """Get status for an asynchronous listing/text generation job."""

        def _run(app):
            return ok(app.get_text_job_status(int(job_id)))

        return call_tool(_run)

    @tool()
    def apply_ai_proposal(draft_id: int) -> dict[str, Any]:
        """Apply the current AI proposal to the draft after the user has accepted it."""

        def _run(app):
            result = app.apply_ai_proposal(int(draft_id))
            result["draft"] = compact_draft(result.get("draft"))
            result["next_actions"] = ["check_required", "publish_preview"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def search_category(q: str, limit: int = 20) -> dict[str, Any]:
        """Search local/Ozon category cache by Chinese or Russian category text."""
        limit = min(100, max(1, int(limit or 20)))

        def _run(app):
            return ok(app.search_category(q, limit=limit))

        return call_tool(_run)

    @tool()
    def get_category_attributes(cat: int, type_id: int, language: str = "ZH_HANS") -> dict[str, Any]:
        """Get Ozon attributes for a category/type pair."""

        def _run(app):
            return ok(app.category_attributes(int(cat), int(type_id), language))

        return call_tool(_run)

    @tool()
    def search_attribute_values(
        cat: int,
        type_id: int,
        attr: int,
        q: str = "",
        language: str = "ZH_HANS",
    ) -> dict[str, Any]:
        """Search dictionary values for an Ozon attribute."""

        def _run(app):
            return ok(app.brand_search(int(cat), int(type_id), int(attr), q, language))

        return call_tool(_run)

    @tool()
    def check_required(draft_id: int, language: str = "ZH_HANS") -> dict[str, Any]:
        """Check required Ozon fields and attributes before publishing."""

        def _run(app):
            return ok(app.required_check(int(draft_id), language))

        return call_tool(_run)

    @tool()
    def get_ozon_analytics_context(
        store_client_id: str | None = None,
        draft_id: int | None = None,
        sku: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        days: int = 14,
        sections: list[str] | None = None,
        top_skus: int = 20,
        keyword_limit: int = 10,
    ) -> dict[str, Any]:
        """Get compact Ozon store/SKU analytics for ChatGPT optimization.

        sections can include dashboard, trends, and keywords. If draft_id or sku
        is given, trend/keyword data is filtered to that SKU when possible.
        """
        wanted = {str(s).strip().lower() for s in (sections or ["dashboard"]) if str(s).strip()}
        wanted = wanted or {"dashboard"}
        allowed = {"dashboard", "trends", "traffic", "keywords"}
        unknown = sorted(wanted - allowed)
        if unknown:
            return fail(f"unsupported analytics sections: {', '.join(unknown)}", kind="bad_request")
        if "traffic" in wanted:
            wanted.add("trends")
        try:
            df, dt = _analytics_dates(date_from, date_to, days)
        except ValueError:
            return fail("date_from/date_to must use YYYY-MM-DD", kind="bad_request")

        def _run(app):
            from webui.services import analytics_service  # noqa: PLC0415

            target_draft = None
            target_sku = str(sku or "").strip()
            target_store = str(store_client_id or "").strip() or None
            if draft_id:
                target_draft = unwrap_draft(app.get_draft(int(draft_id)))
                if not target_draft:
                    raise KeyError(f"draft {draft_id} not found")
                target_store = target_store or str(target_draft.get("store_client_id") or "").strip() or None
                target_sku = target_sku or _draft_sku(app, target_draft, target_store)

            settings_list = _all_store_settings(app, target_store)
            if settings_list:
                dashboard = analytics_service.dashboard_all(settings_list, df, dt)
            else:
                dashboard = analytics_service.dashboard(_analytics_settings(app, target_store), df, dt)

            if target_sku:
                rows = [r for r in dashboard.get("rows") or [] if str(r.get("sku") or "") == target_sku]
                dashboard = {**dashboard, "rows": rows}

            compact_dashboard = _compact_dashboard(dashboard, top_skus=top_skus)
            sku_keys = set(compact_dashboard["top_sku_keys"])
            if target_sku:
                sku_keys.add(target_sku)
                if target_store:
                    sku_keys.add(f"{target_store}:{target_sku}")

            out: dict[str, Any] = {
                "ok": True,
                "store_client_id": target_store or "all",
                "draft": compact_draft(target_draft) if target_draft else None,
                "target_sku": target_sku,
                "date_from": df,
                "date_to": dt,
                "sections": sorted(wanted),
                "dashboard": compact_dashboard,
                "notes": [
                    "Use this data to analyze exposure, sessions, cart conversion, orders, revenue, stock, keyword coverage, and trend changes.",
                    "Ozon keyword analytics may be date-adjusted because product query details lag regular analytics.",
                ],
            }

            if "trends" in wanted:
                if settings_list:
                    traffic = analytics_service.traffic_all(settings_list, df, dt)
                else:
                    traffic = analytics_service.traffic(_analytics_settings(app, target_store), df, dt)
                out["trends"] = _compact_traffic(traffic, sku_keys=sku_keys)

            if "keywords" in wanted:
                if settings_list:
                    keywords = analytics_service.keywords_all(settings_list, df, dt)
                else:
                    keywords = analytics_service.keywords(_analytics_settings(app, target_store), df, dt)
                out["keywords"] = _compact_keywords(keywords, sku_keys=sku_keys, per_sku_limit=keyword_limit)

            return out

        return call_tool(_run)

    @tool()
    def chatgpt_save_optimization_notes(
        notes: dict[str, Any],
        draft_id: int | None = None,
        store_client_id: str | None = None,
    ) -> dict[str, Any]:
        """Save ChatGPT's store/listing optimization analysis without publishing."""
        if not isinstance(notes, dict):
            return fail("notes must be a JSON object", kind="bad_request")

        def _run(app):
            item = {
                "draft_id": int(draft_id) if draft_id else None,
                "store_client_id": str(store_client_id or ""),
                "notes": notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if draft_id:
                draft = unwrap_draft(app.get_draft(int(draft_id)))
                if not draft:
                    raise KeyError(f"draft {draft_id} not found")
                source_raw = _draft_source_raw(draft)
                history = source_raw.get("chatgpt_optimization_notes")
                history = list(history) if isinstance(history, list) else []
                history.append(item)
                source_raw["chatgpt_optimization_notes"] = history[-50:]
                updated = _save_source_raw(app, int(draft_id), source_raw)
                return ok({"saved": item, "draft": compact_draft(updated)})

            settings = app.store.get_settings() or {}
            history = settings.get(_OPTIMIZATION_NOTES_KEY)
            history = list(history) if isinstance(history, list) else []
            history.append(item)
            app.store.save_settings({_OPTIMIZATION_NOTES_KEY: history[-100:]})
            return ok({"saved": item, "count": len(history[-100:])})

        return call_tool(_run)

    @tool()
    def get_image_plan(draft_id: int, force: bool = False) -> dict[str, Any]:
        """Get the current image plan and slot status for a draft."""

        def _run(app):
            return ok(app.image_plan(int(draft_id), force=bool(force)))

        return call_tool(_run)

    @tool()
    def make_rich_content(draft_id: int, image_indexes: list[int] | None = None) -> dict[str, Any]:
        """Generate Ozon rich content JSON from draft images. This does not publish."""

        def _run(app):
            result = app.make_rich_content(int(draft_id), image_indexes=image_indexes)
            result["draft"] = compact_draft(result.get("draft"))
            result["next_actions"] = ["check_required", "publish_preview"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def run_draft_non_publish_pipeline(
        draft_id: int,
        image_target: int = 10,
        submit_image_job: bool = True,
        make_rich: bool = True,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        """Run the full draft workflow except publishing: understand, listing, attributes, image plan/job, rich content, checks."""
        image_target = min(15, max(1, int(image_target or 10)))

        def _run(app):
            return _run_non_publish_pipeline(
                app,
                int(draft_id),
                image_target=image_target,
                submit_image_job=bool(submit_image_job),
                make_rich=bool(make_rich),
                continue_on_error=bool(continue_on_error),
            )

        return call_tool(_run)

    @tool()
    def run_variant_group_non_publish_pipeline(
        draft_id: int,
        image_target: int = 10,
        submit_image_job: bool = True,
        make_rich: bool = True,
        continue_on_error: bool = True,
    ) -> dict[str, Any]:
        """Run the full non-publish workflow for every variant in the selected draft's group."""
        image_target = min(15, max(1, int(image_target or 10)))

        def _run(app):
            base = unwrap_draft(app.get_draft(int(draft_id)))
            group = variant_group_from_draft(base)
            if not group:
                single = _run_non_publish_pipeline(
                    app,
                    int(draft_id),
                    image_target=image_target,
                    submit_image_job=bool(submit_image_job),
                    make_rich=bool(make_rich),
                    continue_on_error=bool(continue_on_error),
                )
                return ok({"variant_group": "", "count": 1, "results": [single], "note": "Draft has no variant group."})
            siblings = app.variant_group_siblings(int(draft_id))
            variants = siblings.get("variants") or []
            results = []
            for item in variants:
                did = int(item.get("id"))
                results.append(
                    _run_non_publish_pipeline(
                        app,
                        did,
                        image_target=image_target,
                        submit_image_job=bool(submit_image_job),
                        make_rich=bool(make_rich),
                        continue_on_error=bool(continue_on_error),
                    )
                )
            return ok(
                {
                    "variant_group": group,
                    "count": len(results),
                    "results": results,
                    "note": "No publish action was executed.",
                }
            )

        return call_tool(_run)

    @tool()
    def design_image_plan(draft_id: int, target: int = 10) -> dict[str, Any]:
        """Use AI to design an Ozon product image plan for the draft."""
        target = min(15, max(1, int(target or 10)))

        def _run(app):
            result = app.design_image_plan(int(draft_id), target=target)
            result["next_actions"] = ["generate_plan_slot", "submit_generate_images"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def generate_plan_slot(draft_id: int, slot_id: str) -> dict[str, Any]:
        """Generate one image for a specific image-plan slot and place it in candidates."""

        def _run(app):
            result = app.generate_plan_slot(int(draft_id), str(slot_id))
            result["next_actions"] = ["apply_image_candidates", "get_image_plan"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def generate_image(
        draft_id: int,
        mode: str = "text2img",
        prompt: str = "",
        source_url: str | None = None,
        reference_urls: list[str] | None = None,
        size: str | None = None,
        as_main: bool = False,
    ) -> dict[str, Any]:
        """Generate a single product image candidate from a prompt and optional references."""

        def _run(app):
            result = app.ai_generate_image(
                int(draft_id),
                mode=mode,
                prompt=prompt,
                source_url=source_url,
                reference_urls=reference_urls,
                size=size,
                as_main=bool(as_main),
            )
            result["next_actions"] = ["apply_image_candidates"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def submit_generate_images(draft_id: int, target: int = 10) -> dict[str, Any]:
        """Submit an asynchronous batch job to generate a full image set."""
        target = min(15, max(1, int(target or 10)))

        def _run(app):
            result = app.submit_gen_job(int(draft_id), target)
            result["poll_tool"] = "get_image_job_status"
            return ok(result)

        return call_tool(_run)

    @tool()
    def get_image_job_status(job_id: int) -> dict[str, Any]:
        """Get status for an asynchronous image generation job."""

        def _run(app):
            return ok(app.get_gen_job_status(int(job_id)))

        return call_tool(_run)

    @tool()
    def apply_image_candidates(draft_id: int, indices: list[int] | None = None) -> dict[str, Any]:
        """Move generated image candidates into the official draft image gallery."""

        def _run(app):
            result = app.apply_image_candidates(int(draft_id), indices)
            result["next_actions"] = ["get_image_plan", "publish_preview"]
            return ok(result)

        return call_tool(_run)

    @tool()
    def process_product(
        draft_id: int,
        scope: Literal["group", "single"] = "group",
    ) -> dict[str, Any]:
        """One-click product processing, never publishing. Say: process draft 1018. Defaults to the whole variant group."""

        def _run(app):
            if scope == "single":
                return _run_non_publish_pipeline(
                    app,
                    int(draft_id),
                    image_target=10,
                    submit_image_job=True,
                    make_rich=True,
                    continue_on_error=True,
                )
            base = unwrap_draft(app.get_draft(int(draft_id)))
            group = variant_group_from_draft(base)
            if not group:
                single = _run_non_publish_pipeline(
                    app,
                    int(draft_id),
                    image_target=10,
                    submit_image_job=True,
                    make_rich=True,
                    continue_on_error=True,
                )
                return ok({"variant_group": "", "count": 1, "results": [single], "note": "Draft has no variant group. No publish action was executed."})
            siblings = app.variant_group_siblings(int(draft_id))
            results = []
            for item in siblings.get("variants") or []:
                results.append(
                    _run_non_publish_pipeline(
                        app,
                        int(item.get("id")),
                        image_target=10,
                        submit_image_job=True,
                        make_rich=True,
                        continue_on_error=True,
                    )
                )
            return ok({"variant_group": group, "count": len(results), "results": results, "note": "No publish action was executed."})

        return call_tool(_run)

    @tool()
    def product_status(draft_id: int, scope: Literal["group", "single"] = "group") -> dict[str, Any]:
        """Check processing status for one draft or its whole variant group."""

        def _run(app):
            if scope == "single":
                return ok({"draft_id": int(draft_id), "pipeline": app.draft_pipeline(int(draft_id))})
            base = unwrap_draft(app.get_draft(int(draft_id)))
            group = variant_group_from_draft(base)
            if not group:
                return ok({"variant_group": "", "items": [{"draft_id": int(draft_id), "pipeline": app.draft_pipeline(int(draft_id))}]})
            siblings = app.variant_group_siblings(int(draft_id))
            items = []
            for item in siblings.get("variants") or []:
                did = int(item.get("id"))
                items.append({"draft_id": did, "spec": item.get("spec"), "pipeline": app.draft_pipeline(did)})
            return ok({"variant_group": group, "count": len(items), "items": items})

        return call_tool(_run)

    @tool()
    def publish_preview(draft_id: int, store_client_id: str | None = None) -> dict[str, Any]:
        """Build the Ozon publish payload preview without sending it to Ozon."""

        def _run(app):
            return ok(app.publish_preview(int(draft_id), store_client_id))

        return call_tool(_run)

    @tool()
    def publish_preflight(draft_id: int) -> dict[str, Any]:
        """Run publish preflight checks and return blockers or warnings."""

        def _run(app):
            return ok(app.publish_preflight(int(draft_id)))

        return call_tool(_run)

    @tool()
    def publish_draft(draft_id: int, store_client_id: str | None = None, confirm: bool = False) -> dict[str, Any]:
        """Publish a draft to Ozon. Set confirm=true only after the user explicitly approves publishing."""
        if not confirm:
            return fail(
                "publish_draft requires confirm=true after explicit user approval. Use publish_preview first.",
                draft_id=int(draft_id),
                next_actions=["publish_preview", "publish_preflight"],
            )

        def _run(app):
            return ok(app.publish(int(draft_id), store_client_id))

        return call_tool(_run)
