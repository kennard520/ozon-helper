"""Text-generation worker for the ``ozon_text_jobs`` queue.

The worker intentionally does not import ``webui``. It assembles the minimal
DB/Ozon/AI dependencies locally and calls the common text-pipeline primitives.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ozon_api import OzonSellerClient
from ozon_common.dal.engine import engine_for
from ozon_common.dal.repositories.catalog_cache_repo import CatalogCacheRepo
from ozon_common.dal.repositories.draft_repo import DraftRepo
from ozon_common.dal.repositories.settings_repo import SettingsRepo
from ozon_common.dal.repositories.text_job_repo import TextJobRepo
from ozon_common.dal.session import bind_engine, session_scope
from ozon_common.jsonio import utc_now_iso
from ozon_common.mq import consume_text_jobs
from ozon_common.settings import ai_config
from ozon_common.text_pipeline.ai_card import (
    NO_BRAND,
    build_profile,
    category_override_from_profile,
    clean_hashtags,
    navigate_category,
)
from ozon_common.text_pipeline.card_gen import _SYS_ATTRS_PICK, _SYS_TITLE, _extract_json
from ozon_common.text_pipeline.pipeline import run_text_pipeline
from ozon_common.text_pipeline.understand import understand

log = logging.getLogger("ozon.text_worker")

_USER_ID = int(os.environ.get("TEXT_WORKER_USER_ID") or "1")
_MODEL_NAME_ATTR_ID = 9048
_BRAND_ATTR_ID = 85
_HASHTAGS_ATTR_ID = 23171
_TEXT_ATTR_OPTION_CAP = int(os.environ.get("TEXT_ATTR_OPTION_CAP") or "120")
_TEXT_ATTR_MAX_ITEMS = int(os.environ.get("TEXT_ATTR_MAX_ITEMS") or "60")


def _to_int(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _build_client(settings: dict) -> OzonSellerClient:
    cid = str(settings.get("ozon_client_id") or "").strip()
    key = str(settings.get("ozon_api_key") or "").strip()
    if not cid or not key:
        raise RuntimeError("请先配置 Ozon Client-Id 和 Api-Key")
    return OzonSellerClient(client_id=cid, api_key=key, timeout=60.0)


def _normalize_category_attrs(raw: object) -> list[dict]:
    result = raw.get("result") if isinstance(raw, dict) else raw
    out: list[dict] = []
    for a in result or []:
        if not isinstance(a, dict):
            continue
        aid = _to_int(a.get("id"))
        if not aid:
            continue
        out.append({
            "id": aid,
            "name": str(a.get("name") or ""),
            "description": str(a.get("description") or ""),
            "type": str(a.get("type") or ""),
            "is_required": bool(a.get("is_required")),
            "is_collection": bool(a.get("is_collection")),
            "dictionary_id": _to_int(a.get("dictionary_id")),
            "category_dependent": bool(a.get("category_dependent")),
            "is_aspect": bool(a.get("is_aspect")),
            "max_value_count": _to_int(a.get("max_value_count")),
        })
    return out


def _chat(settings: dict, system: str, user: str, images: list[str] | None = None, *, kind: str = "text") -> str:
    cfg = ai_config(settings, kind)
    base = (cfg.get("base") or "").strip().rstrip("/")
    key = (cfg.get("key") or "").strip()
    if cfg.get("engine") == "agnes" and not base:
        base = "https://apihub.agnes-ai.com"
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    if not key:
        raise RuntimeError(f"未配置 AI 引擎({kind})")
    model = (cfg.get("model") or "").strip() or ("agnes-2.0-flash" if cfg.get("engine") == "agnes" else "deepseek-v4-flash")
    content: object = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in images[:4]
        ]
    body = {
        "model": model,
        "temperature": 0.3,
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
    }
    if cfg.get("engine") == "agnes" or "agnes" in base.lower():
        body["chat_template_kwargs"] = {"enable_thinking": True}
    req = Request(
        base.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    retryable = {429, 500, 502, 503, 504}
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urlopen(req, timeout=180) as res:  # noqa: S310
                data = json.loads(res.read().decode("utf-8"))
            return str(data["choices"][0]["message"]["content"] or "").strip()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in retryable and attempt < 3:
                last = RuntimeError(f"AI HTTP {exc.code}: {detail}")
                time.sleep([0.8, 2, 4][attempt])
                continue
            raise RuntimeError(f"AI HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            if attempt < 3:
                last = exc
                time.sleep([0.8, 2, 4][attempt])
                continue
            raise RuntimeError(f"AI 连接失败: {exc}") from exc
    raise last or RuntimeError("AI 接口重试用尽")


def _settings(user_id: int = _USER_ID) -> dict:
    with session_scope():
        return SettingsRepo().get_settings(user_id)


def _get_draft(draft_id: int, user_id: int = _USER_ID) -> dict:
    with session_scope():
        draft = DraftRepo().get_draft(draft_id, user_id)
    if draft is None:
        raise RuntimeError(f"draft {draft_id} not found")
    return draft


def _validate_draft(draft: dict) -> list[str]:
    errors: list[str] = []
    if not str(draft.get("ozon_title") or "").strip():
        errors.append("Ozon俄语标题不能为空")
    if not str(draft.get("description") or "").strip():
        errors.append("描述不能为空")
    if not str(draft.get("category_id") or "").strip():
        errors.append("description_category_id 不能为空（在类目搜索里选）")
    if not str(draft.get("type_id") or "").strip():
        errors.append("type_id 不能为空（类目搜索里一起选）")
    try:
        if float(draft.get("price") or 0) <= 0:
            errors.append("售价必须大于0")
    except (TypeError, ValueError):
        errors.append("售价必须大于0")
    if _to_int(draft.get("stock")) < 0:
        errors.append("库存不能为负数")
    if not draft.get("images"):
        errors.append("至少需要1张图片URL")
    return errors


def _update_draft(draft_id: int, patch: dict, user_id: int = _USER_ID) -> dict:
    with session_scope():
        repo = DraftRepo()
        current = repo.get_draft(draft_id, user_id)
        if current is None:
            raise RuntimeError(f"draft {draft_id} not found")
        updated = {**current, **patch, "updated_at": utc_now_iso()}
        errors = _validate_draft(updated)
        status = "ready" if not errors else "invalid"
        return repo.update_draft(draft_id, updated, user_id=user_id, errors=errors, status=status, sync_images="images" in patch)


def _category_roots(settings: dict) -> list:
    with session_scope():
        cached = CatalogCacheRepo().load_catalog_tree("ZH_HANS")
    if cached is not None:
        return cached
    client = _build_client(settings)
    tree = client.get_category_tree(language="ZH_HANS")
    root = tree.get("result") or tree
    with session_scope():
        CatalogCacheRepo().save_catalog_tree("ZH_HANS", root)
    return root


def _category_attrs(settings: dict, cat: int, typ: int, language: str = "ZH_HANS") -> list[dict]:
    lang = language or "ZH_HANS"
    with session_scope():
        cached = CatalogCacheRepo().load_category_attrs(cat, typ, lang)
    if cached and "description" in cached[0] and "is_aspect" in cached[0] and "max_value_count" in cached[0]:
        return cached
    raw = _build_client(settings).get_category_attributes(cat, typ, language=lang)
    attrs = _normalize_category_attrs(raw)
    if attrs:
        with session_scope():
            CatalogCacheRepo().save_category_attrs(cat, typ, attrs, lang)
    return attrs


def _ensure_attr_values(settings: dict, cat: int, typ: int, aid: int, language: str = "RU") -> tuple[list[dict], bool]:
    with session_scope():
        cached = CatalogCacheRepo().load_attr_values(cat, typ, aid, language)
    if cached is not None:
        return cached
    try:
        out = _build_client(settings).get_attribute_values(cat, typ, aid, language=language, max_total=2000)
    except Exception:
        return ([], False)
    values = [] if out.get("oversized") else (out.get("values") or [])
    oversized = bool(out.get("oversized"))
    with session_scope():
        CatalogCacheRepo().save_attr_values(cat, typ, aid, values, oversized, language)
    return values, oversized


def _resolve_values(settings: dict, cat: int, typ: int, aid: int, texts: list[str], is_collection: bool) -> list[dict]:
    out: list[dict] = []
    seen: set[int] = set()
    client = _build_client(settings)
    for text in (texts if is_collection else texts[:1]):
        if len(str(text).strip()) < 2:
            continue
        try:
            resp = client.search_attribute_values(cat, typ, aid, str(text), limit=20, language="RU")
            res = resp.get("result") or []
        except Exception:
            res = []
        if not res:
            continue
        t = str(text).strip().lower()
        hit = next((r for r in res if str(r.get("value") or "").strip().lower() == t), res[0])
        vid = _to_int(hit.get("id") or hit.get("dictionary_value_id"))
        if vid and vid not in seen:
            seen.add(vid)
            out.append({"dictionary_value_id": vid, "value": str(hit.get("value") or text)})
    return out


def _resolve_image(url: str) -> str:
    u = str(url or "").strip()
    if u.startswith("/media/") and os.environ.get("TEXT_WORKER_MEDIA_BASE"):
        return os.environ["TEXT_WORKER_MEDIA_BASE"].rstrip("/") + u
    return u


def _attr_has_value(attr: dict) -> bool:
    values = attr.get("values") if isinstance(attr.get("values"), list) else []
    for v in values:
        if isinstance(v, dict) and (_to_int(v.get("dictionary_value_id")) > 0 or str(v.get("value") or "").strip()):
            return True
    return False


def _dedupe_attrs(attrs: list[dict]) -> list[dict]:
    order: list[int] = []
    by_id: dict[int, dict] = {}
    passthrough: list[dict] = []
    for raw in attrs or []:
        if not isinstance(raw, dict):
            continue
        aid = _to_int(raw.get("id"))
        if not aid:
            passthrough.append(raw)
            continue
        attr = {**raw, "id": aid}
        if aid not in by_id:
            order.append(aid)
            by_id[aid] = attr
            continue
        if _attr_has_value(attr) or not _attr_has_value(by_id[aid]):
            by_id[aid] = attr
    return passthrough + [by_id[aid] for aid in order]


def _run_understand(draft_id: int) -> dict:
    draft = _get_draft(draft_id)
    sr = dict(draft.get("source_raw") or {})
    cached = isinstance(sr.get("understanding"), dict) and bool(sr["understanding"])
    if not cached:
        settings = _settings(int(draft.get("user_id") or _USER_ID))
        u = understand(
            draft,
            lambda s, u, images: _chat(settings, s, u, images, kind="multimodal" if ai_config(settings, "multimodal").get("key") else "text"),
            resolve_image=_resolve_image,
        )
        sr["understanding"] = u
        _update_draft(draft_id, {"source_raw": sr}, int(draft.get("user_id") or _USER_ID))
    return {"ok": True, "cached": cached, "understanding": sr.get("understanding")}


def _run_category(draft_id: int) -> dict:
    draft = _get_draft(draft_id)
    user_id = int(draft.get("user_id") or _USER_ID)
    settings = _settings(user_id)
    raw = dict(draft.get("source_raw") or {})
    profile = build_profile(raw, understanding=raw.get("understanding"))
    roots = _category_roots(settings)
    nav = category_override_from_profile(roots, profile)
    if nav:
        log.info("[category draft=%s] deterministic override path=%s", draft_id, " / ".join(nav.get("path") or []))
    else:
        nav = navigate_category(roots, lambda s, u: _chat(settings, s, u), profile)
    if not nav or not nav.get("type_id"):
        return {"ok": False, "matched": False, "note": "AI 没识别出类别"}
    cat, typ = int(nav["description_category_id"]), int(nav["type_id"])
    path = " / ".join(nav.get("path") or [])
    updated = _update_draft(draft_id, {"category_id": str(cat), "type_id": str(typ), "category_path": path}, user_id)
    vg = str((updated.get("source_raw") or {}).get("variant_group") or "").strip()
    synced = 0
    if vg:
        with session_scope():
            siblings = DraftRepo().list_drafts_by_variant_group(vg)
        for sib in siblings:
            if int(sib["id"]) == int(draft_id):
                continue
            _update_draft(int(sib["id"]), {"category_id": str(cat), "type_id": str(typ), "category_path": path}, int(sib.get("user_id") or user_id))
            synced += 1
    return {"ok": True, "matched": True, "category_id": cat, "type_id": typ, "category_path": path, "group_synced": synced}


def _raw_for_copy(draft: dict) -> dict:
    raw = dict(draft.get("source_raw") or {})
    if not str(raw.get("title") or "").strip():
        raw["title"] = draft.get("source_title") or draft.get("ozon_title") or ""
    if not raw.get("params"):
        raw["params"] = raw.get("attributes") or (draft.get("attributes") if isinstance(draft.get("attributes"), list) else [])
    if not str(raw.get("description_text") or "").strip():
        raw["description_text"] = draft.get("description") or ""
    return raw


def _run_copy(draft_id: int) -> dict:
    draft = _get_draft(draft_id)
    user_id = int(draft.get("user_id") or _USER_ID)
    settings = _settings(user_id)
    raw = _raw_for_copy(draft)
    profile = build_profile(raw, understanding=raw.get("understanding"))
    body = _extract_json(_chat(settings, _SYS_TITLE, "Product:\n" + profile))
    attrs = list(draft.get("attributes") or []) if isinstance(draft.get("attributes"), list) else []
    tags_value = clean_hashtags(body.get("hashtags"))
    attrs = [a for a in attrs if not (isinstance(a, dict) and _to_int(a.get("id")) == _HASHTAGS_ATTR_ID)]
    if tags_value:
        attrs.append({"id": _HASHTAGS_ATTR_ID, "values": [{"value": tags_value}]})
    patch = {
        "ozon_title": str(body.get("ozon_title") or ""),
        "description": str(body.get("description") or ""),
        "attributes": attrs,
    }
    return {"ok": True, "draft": _update_draft(draft_id, patch, user_id)}


def _run_attrs(draft_id: int) -> dict:
    started = time.monotonic()
    draft = _get_draft(draft_id)
    user_id = int(draft.get("user_id") or _USER_ID)
    settings = _settings(user_id)
    cat, typ = _to_int(draft.get("category_id")), _to_int(draft.get("type_id"))
    if not cat or not typ:
        return {"ok": False, "error": "请先选好类目再自动填充"}
    raw = _raw_for_copy(draft)
    profile = build_profile(raw, understanding=raw.get("understanding"))
    all_attrs = [a for a in _category_attrs(settings, cat, typ, language="ZH_HANS") if _to_int(a.get("id")) != _BRAND_ATTR_ID]
    required = [a for a in all_attrs if a.get("is_required")]
    aspect = [a for a in all_attrs if a.get("is_aspect") and not a.get("is_required")]
    ordered = required + aspect + [a for a in all_attrs if not a.get("is_required") and not a.get("is_aspect")]
    brief: list[dict] = []
    opt_index: dict[int, dict[int, str]] = {}
    dict_fetches = 0
    for a in ordered[:_TEXT_ATTR_MAX_ITEMS]:
        aid = _to_int(a.get("id"))
        if not aid or aid == _HASHTAGS_ATTR_ID:
            continue
        important = bool(a.get("is_required") or a.get("is_aspect"))
        item = {
            "id": aid,
            "name": a.get("name"),
            "required": bool(a.get("is_required")),
            "is_aspect": bool(a.get("is_aspect")),
            "hint": str(a.get("description") or "")[:100],
        }
        if a.get("dictionary_id"):
            values: list[dict] = []
            oversized = False
            if important:
                dict_fetches += 1
                values, oversized = _ensure_attr_values(settings, cat, typ, aid, language="RU")
            if values and not oversized and len(values) <= _TEXT_ATTR_OPTION_CAP:
                opt_index[aid] = {_to_int(v.get("id")): str(v.get("value") or "") for v in values if _to_int(v.get("id"))}
                item["kind"] = "select_many" if a.get("is_collection") else "select_one"
                item["options"] = [{"id": vid, "value": val} for vid, val in opt_index[aid].items()]
                if a.get("is_collection") and a.get("max_value_count"):
                    item["max_values"] = _to_int(a.get("max_value_count"))
            else:
                item["kind"] = "text_ru"
        else:
            typ_name = str(a.get("type") or "").lower()
            item["kind"] = "number" if typ_name in ("decimal", "integer", "float", "number") else ("boolean" if typ_name == "boolean" else "text_ru")
        brief.append(item)
    log.info("[attrs draft=%s] prepared attrs=%s required=%s aspect=%s dict_fetches=%s in %.2fs",
             draft_id, len(brief), len(required), len(aspect), dict_fetches, time.monotonic() - started)
    user = "Attribute list:\n" + json.dumps(brief, ensure_ascii=False) + "\n\nProduct:\n" + profile
    variant_spec = str(raw.get("spec_attrs") or raw.get("variant_label") or "").strip()
    if variant_spec:
        user += f"\n\nThis is ONE VARIANT. Its distinguishing spec (Chinese):「{variant_spec}」. Fill is_aspect attributes to match THIS variant."
    ai_started = time.monotonic()
    card = _extract_json(_chat(settings, _SYS_ATTRS_PICK, user))
    log.info("[attrs draft=%s] ai returned in %.2fs", draft_id, time.monotonic() - ai_started)
    meta = {_to_int(a.get("id")): a for a in all_attrs}
    new_attrs: list[dict] = []
    mapped: list[dict] = []
    unmapped: list[dict] = []
    for ca in card.get("attributes") or []:
        aid = _to_int(ca.get("id"))
        if not aid or aid not in meta:
            continue
        m = meta[aid]
        if aid in opt_index:
            ids = ca.get("value_ids")
            ids = ids if isinstance(ids, list) else ([ids] if ids not in (None, "") else [])
            vals = []
            for raw_id in ids:
                vid = _to_int(raw_id)
                if vid in opt_index[aid]:
                    vals.append({"dictionary_value_id": vid, "value": opt_index[aid][vid]})
            if not m.get("is_collection"):
                vals = vals[:1]
            if vals:
                new_attrs.append({"id": aid, "values": vals})
                mapped.append({"id": aid, "name": m.get("name"), "value": ", ".join(v["value"] for v in vals)})
            else:
                unmapped.append({"id": aid, "name": m.get("name"), "value": str(ca.get("value_ids") or "")})
            continue
        val = str(ca.get("value") or ca.get("value_ru") or "").strip()
        if not val:
            continue
        if m.get("dictionary_id"):
            texts = [x.strip() for x in val.replace("，", ",").split(",") if x.strip()]
            vals = _resolve_values(settings, cat, typ, aid, texts, bool(m.get("is_collection")))
            if vals:
                new_attrs.append({"id": aid, "values": vals})
                mapped.append({"id": aid, "name": m.get("name"), "value": val})
            else:
                unmapped.append({"id": aid, "name": m.get("name"), "value": val})
        else:
            new_attrs.append({"id": aid, "values": [{"value": val}]})
            mapped.append({"id": aid, "name": m.get("name"), "value": val})
    desc = str(draft.get("description") or "").strip()
    if desc:
        for a in all_attrs:
            name = str(a.get("name") or "").lower()
            aid = _to_int(a.get("id"))
            if aid and not a.get("dictionary_id") and (("简介" in name) or ("аннотац" in name) or name == "описание"):
                new_attrs.append({"id": aid, "values": [{"value": desc}]})
    vg = str(raw.get("variant_group") or "").strip()
    if any(_to_int(a.get("id")) == _MODEL_NAME_ATTR_ID for a in all_attrs):
        model_value = vg or "M-" + uuid.uuid4().hex[:8].upper()
        new_attrs = [a for a in new_attrs if _to_int(a.get("id")) != _MODEL_NAME_ATTR_ID]
        new_attrs.append({"id": _MODEL_NAME_ATTR_ID, "values": [{"value": model_value}]})
    existing = list(draft.get("attributes") or []) if isinstance(draft.get("attributes"), list) else []
    replace_ids = {_to_int(a.get("id")) for a in new_attrs if _to_int(a.get("id"))}
    merged = [a for a in existing if not (isinstance(a, dict) and _to_int(a.get("id")) in replace_ids and _to_int(a.get("id")) != _HASHTAGS_ATTR_ID)]
    merged.extend(new_attrs)
    merged = _dedupe_attrs(merged)
    updated = _update_draft(draft_id, {"attributes": merged}, user_id)
    log.info("[attrs draft=%s] done total=%.2fs mapped=%s unmapped=%s",
             draft_id, time.monotonic() - started, len(mapped), len(unmapped))
    return {"ok": True, "draft": updated, "mapped_count": len(mapped), "mapped": mapped, "unmapped": unmapped}


def _make_on_step(job_id: int):
    def on_step(step: str) -> None:
        with session_scope():
            repo = TextJobRepo()
            job = repo.get(job_id)
            if job is None:
                return
            done = [s for s in str(job.get("steps_done") or "").split(",") if s]
            if step not in done:
                done.append(step)
            repo.update_status(job_id, {"current_step": step, "steps_done": ",".join(done)})
        log.info("[text_job %s] step done: %s", job_id, step)
    return on_step


def handle_text_job(job_id: int, draft_id: int) -> None:
    log.info("[text_job %s] start draft=%s", job_id, draft_id)

    # 先检查任务是否存在，不存在直接 ack 丢弃，不消耗 token
    with session_scope():
        job = TextJobRepo().get(job_id)
    if job is None:
        log.warning("[text_job %s] job not found in DB, skipping (ack)", job_id)
        return

    with session_scope():
        TextJobRepo().update_status(job_id, {"status": "running"})

    try:
        run_text_pipeline(
            draft_id,
            run_understand=_run_understand,
            run_category=_run_category,
            run_copy=_run_copy,
            run_attrs=_run_attrs,
            on_step=_make_on_step(job_id),
        )
        with session_scope():
            TextJobRepo().update_status(job_id, {"status": "done", "current_step": "attrs"})
        log.info("[text_job %s] done", job_id)
    except Exception as exc:
        log.exception("[text_job %s] failed: %s", job_id, exc)
        with session_scope():
            TextJobRepo().update_status(job_id, {"status": "failed", "error": str(exc)[:500]})
        raise


def main_text() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    log.info("Text worker started, consuming ozon_text_jobs")
    bind_engine(engine_for(None))
    consume_text_jobs(handle_text_job)


if __name__ == "__main__":
    main_text()
