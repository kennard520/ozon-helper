from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from webui.drafts import dimension_warnings, validate_draft

STATUS_DRAFT = "draft"
STATUS_READY = "ready"
STATUS_INVALID = "invalid"
STATUS_MEDIA_PENDING = "media_pending"
STATUS_PUBLISHING = "publishing"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

EXPLICIT_STATUSES = {
    STATUS_DRAFT,
    STATUS_READY,
    STATUS_INVALID,
    STATUS_MEDIA_PENDING,
    STATUS_PUBLISHING,
    STATUS_PUBLISHED,
    STATUS_FAILED,
    STATUS_SKIPPED,
}

PRESERVE_WHEN_RECALCULATING = {
    STATUS_PUBLISHING,
    STATUS_PUBLISHED,
    STATUS_SKIPPED,
}


@dataclass(frozen=True)
class DraftCheck:
    severity: str
    label: str
    code: str = "draft_check"
    field: str = ""
    step: str = "details"
    fix_action: str = "review"

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "label": self.label,
            "message": self.label,
            "code": self.code,
            "field": self.field,
            "step": self.step,
            "fix_action": self.fix_action,
        }


def _classify_check(message: str, severity: str) -> DraftCheck:
    text = str(message or "")
    field = ""
    step = "details"
    code = "draft_check"
    fix_action = "review"
    if "标题" in text or "title" in text:
        field, step, code, fix_action = "ozon_title", "content", "title_risk", "edit_title"
    elif "描述" in text or "description" in text:
        field, step, code, fix_action = "description", "content", "description_risk", "edit_description"
    elif "category" in text or "类目" in text or "type_id" in text or "description_category_id" in text:
        field, step, code, fix_action = "category_id", "category_recognition", "category_risk", "select_category"
    elif "价格" in text or "售价" in text or "price" in text:
        field, step, code, fix_action = "price", "pricing", "price_risk", "edit_price"
    elif "库存" in text or "stock" in text:
        field, step, code, fix_action = "stock", "details", "stock_risk", "edit_stock"
    elif "图片" in text or "image" in text or "media" in text or "URL" in text:
        field, step, code, fix_action = "images", "media", "media_risk", "fix_media"
    elif "尺寸" in text or "重量" in text or "density" in text or "mm" in text:
        field, step, code, fix_action = "dimensions", "details", "dimension_risk", "edit_dimensions"
    elif "品牌" in text or "brand" in text:
        field, step, code, fix_action = "brand_name", "attributes", "brand_risk", "edit_brand"
    return DraftCheck(severity, text, code=code, field=field, step=step, fix_action=fix_action)


def derive_draft_status(
    draft: dict[str, Any],
    errors: list[str] | None = None,
    *,
    requested_status: str | None = None,
) -> str:
    """Return the canonical stored status for a draft."""
    if requested_status:
        status = str(requested_status).strip()
        if status:
            return status
    current = str(draft.get("status") or "").strip()
    if current in PRESERVE_WHEN_RECALCULATING:
        return current
    if str(draft.get("media_status") or "done").strip() == "pending":
        return STATUS_MEDIA_PENDING
    if errors:
        return STATUS_INVALID
    return STATUS_READY


def build_draft_checks(draft: dict[str, Any]) -> list[DraftCheck]:
    checks: list[DraftCheck] = []
    for error in validate_draft(draft):
        checks.append(_classify_check(error, "error"))
    for warning in dimension_warnings(draft):
        checks.append(_classify_check(warning, "warn"))
    if str(draft.get("media_status") or "done") == "pending":
        checks.append(DraftCheck(
            "error",
            "media is still uploading",
            code="media_pending",
            field="images",
            step="media",
            fix_action="wait_media_upload",
        ))
    return checks


def blocking_errors(checks: list[DraftCheck]) -> list[str]:
    return [c.label for c in checks if c.severity == "error"]


def warning_messages(checks: list[DraftCheck]) -> list[str]:
    return [c.label for c in checks if c.severity in {"warn", "verify"}]
