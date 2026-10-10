from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar

from webui.app_service import App
from webui.store import current_user_id

T = TypeVar("T")

_APP: App | None = None


def default_user_id() -> int:
    raw = os.environ.get("OZON_MCP_USER_ID") or "1"
    try:
        value = int(raw)
    except ValueError:
        return 1
    return value if value > 0 else 1


def get_app() -> App:
    global _APP
    if _APP is None:
        _APP = App()
        # Some existing helpers expect the process-wide webui singleton to exist.
        import webui.app_instance as app_instance  # noqa: PLC0415

        app_instance.APP = _APP
    return _APP


def run_as_user(fn: Callable[[App], T], *, user_id: int | None = None) -> T:
    token = current_user_id.set(user_id or default_user_id())
    try:
        return fn(get_app())
    finally:
        current_user_id.reset(token)


def ok(data: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": True}
    if data:
        body.update(data)
    body.update(extra)
    return body


def fail(message: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": False, "error": message}
    body.update(extra)
    return body


def call_tool(fn: Callable[[App], dict[str, Any]], *, user_id: int | None = None) -> dict[str, Any]:
    try:
        result = run_as_user(fn, user_id=user_id)
    except KeyError as exc:
        return fail(str(exc), kind="not_found")
    except ValueError as exc:
        return fail(str(exc), kind="bad_request")
    except RuntimeError as exc:
        return fail(str(exc), kind="runtime")
    except Exception as exc:  # noqa: BLE001 - tool boundary should return structured errors.
        return fail(str(exc), kind=exc.__class__.__name__)
    return result if isinstance(result, dict) else ok({"result": result})


def compact_draft(draft: dict[str, Any] | None) -> dict[str, Any] | None:
    draft = unwrap_draft(draft)
    if draft is None:
        return None
    keys = (
        "id",
        "source_url",
        "source_platform",
        "source_title",
        "ozon_title",
        "description",
        "category_id",
        "type_id",
        "brand_name",
        "price",
        "old_price",
        "cost_cny",
        "weight_g",
        "length_mm",
        "width_mm",
        "height_mm",
        "store_client_id",
        "media_status",
        "publish_status",
    )
    out = {k: draft.get(k) for k in keys if k in draft}
    images = draft.get("images") or draft.get("materials") or []
    if isinstance(images, list):
        out["image_count"] = len(images)
        out["images"] = images[:12]
    attrs = draft.get("attributes") or []
    if isinstance(attrs, list):
        out["attribute_count"] = len(attrs)
    if draft.get("ai_proposal"):
        out["has_ai_proposal"] = True
    return out


def unwrap_draft(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict) and isinstance(value.get("draft"), dict):
        return value["draft"]
    return value


def variant_group_from_draft(draft: dict[str, Any] | None) -> str:
    draft = unwrap_draft(draft)
    if not draft:
        return ""
    source_raw = draft.get("source_raw")
    if isinstance(source_raw, dict):
        return str(source_raw.get("variant_group") or "").strip()
    return ""


def draft_ids_for_scope(app: App, draft_id: int, scope: str = "single") -> tuple[str, list[int]]:
    draft = unwrap_draft(app.get_draft(int(draft_id)))
    if not draft:
        raise KeyError(f"draft {draft_id} not found")
    group = variant_group_from_draft(draft)
    if scope != "group" or not group:
        return group, [int(draft_id)]
    siblings = app.variant_group_siblings(int(draft_id))
    ids: list[int] = []
    for item in siblings.get("variants") or []:
        try:
            ids.append(int(item.get("id")))
        except (TypeError, ValueError):
            continue
    return group, ids or [int(draft_id)]
