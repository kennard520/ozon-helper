"""历史数据回填(从 Store.init 剥离;DDL 交给 metadata/Alembic,数据回填仍 run-once、自限)。"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text

from webui.drafts import loads_json, utc_now_iso

log = logging.getLogger("ozon.app")

# OZ 随机占位货号(random_offer_id 生成的)模式：只有这种和空货号才会被重格式化，真实/已格式化货号不动
_OZ_PLACEHOLDER = re.compile(r"^OZ[A-Z0-9]{10}$")
# 货号片段清洗：去 HTML 实体 + 空白/斜杠/尖括号等不适合做货号的字符；连字符是分隔符故也去掉
_OID_STRIP = re.compile(r"[\s/\\><&;,|+]+")


def _oid_seg(value: Any) -> str:
    s = str(value or "").replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return _OID_STRIP.sub("", s).strip("-").strip()


def _offer_id_base(platform: Any, source_raw: Any) -> str:
    """按 {平台}-{变体维度值} 拼货号(可读，标明来源+哪个 SKU)：
    1688/ozon/wb + selected_aspects 各轴值，如 1688-红-XL；无变体维度退回 spec_attrs；再没有就平台+随机短码。"""
    plat = str(platform or "1688").strip() or "1688"
    sr = source_raw if isinstance(source_raw, dict) else {}
    parts = []
    aspects = sr.get("selected_aspects")
    if isinstance(aspects, list):
        for a in aspects:
            seg = _oid_seg((a or {}).get("value") if isinstance(a, dict) else "")
            if seg:
                parts.append(seg)
    if not parts:
        seg = _oid_seg(sr.get("spec_attrs") or sr.get("variant_label"))
        if seg:
            parts.append(seg)
    if parts:
        return plat + "-" + "-".join(parts)
    import uuid  # noqa: PLC0415
    return plat + "-" + uuid.uuid4().hex[:6].upper()


def _variant_group_of(source_raw_json: Any) -> str:
    """从 source_raw_json 取 variant_group（同组合并键）；无则空串。"""
    sr = loads_json(source_raw_json, {}) or {}
    return str((sr.get("variant_group") if isinstance(sr, dict) else "") or "").strip()


def _unique_offer_id(conn, base: str, exclude_id: int | None = None) -> str:
    """保证货号唯一：撞库就加 -2/-3。conn 为 SQLAlchemy Connection。"""
    cand, n = base, 1
    while True:
        row = conn.execute(
            text("SELECT id FROM drafts WHERE offer_id=:oid LIMIT 1"), {"oid": cand}
        ).fetchone()
        if not row or (exclude_id is not None and int(row._mapping["id"]) == int(exclude_id)):
            return cand
        n += 1
        cand = f"{base}-{n}"


def run_backfills(engine) -> None:
    """对给定 SQLAlchemy engine 依次跑三个自限回填。"""
    with engine.begin() as conn:
        _backfill_variant_group(conn)
        _backfill_offer_id(conn)
        _backfill_draft_images(conn)


def _backfill_variant_group(conn) -> None:
    """历史草稿把 variant_group 从 source_raw_json 回填到新列。
    只处理「列空但 JSON 里有 variant_group」的行 → 回填后列非空，下次不再命中，自限一次；
    非变体草稿(JSON 无该键)永不命中，不浪费。失败不阻断启动(列空时分组面板退化，不崩)。"""
    try:
        rows = conn.execute(
            text(
                "SELECT id, source_raw_json FROM drafts "
                "WHERE variant_group = '' AND source_raw_json LIKE '%variant_group%'"
            )
        ).fetchall()
        for r in rows:
            m = r._mapping
            vg = _variant_group_of(m.get("source_raw_json"))
            if vg:
                conn.execute(
                    text("UPDATE drafts SET variant_group=:vg WHERE id=:id"),
                    {"vg": vg, "id": m["id"]},
                )
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[store] variant_group backfill skipped: {exc}")


def _backfill_offer_id(conn) -> None:
    """历史草稿货号规整成 {平台}-{变体维度} 格式（货号必填、可读标明来源）。
    只动**未发布**且货号为空或还是 OZ 随机占位的——真实/已发布/已格式化的货号绝不碰。
    自限：重格式化后货号以 {平台}- 开头、不再匹配占位模式，下次启动跳过。"""
    try:
        rows = conn.execute(
            text("SELECT id, status, offer_id, source_platform, source_raw_json FROM drafts")
        ).fetchall()
        for r in rows:
            m = r._mapping
            if m["status"] == "published":
                continue
            cur = str(m["offer_id"] or "")
            if cur and not _OZ_PLACEHOLDER.match(cur):
                continue   # 已是真实/格式化货号，不动
            sr = loads_json(m.get("source_raw_json"), {})
            base = _offer_id_base(m["source_platform"], sr)
            new = _unique_offer_id(conn, base, exclude_id=m["id"])
            conn.execute(
                text("UPDATE drafts SET offer_id=:oid WHERE id=:id"),
                {"oid": new, "id": m["id"]},
            )
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[store] offer_id backfill skipped: {exc}")


def _backfill_draft_images(conn) -> None:
    """一次性：把 images_json 里的图回填到 draft_images 表。
    自限：已有 draft_images 行的草稿跳过。失败不阻断启动。"""
    try:
        rows = conn.execute(
            text(
                "SELECT d.id, d.images_json, d.source_raw_json FROM drafts d"
                " WHERE NOT EXISTS (SELECT 1 FROM draft_images di WHERE di.draft_id = d.id)"
                " AND d.images_json != '[]' AND d.images_json != ''"
            )
        ).fetchall()
        if not rows:
            return
        now = utc_now_iso()
        inserted = 0
        for r in rows:
            m = r._mapping
            images = loads_json(m["images_json"], []) or []
            if not images:
                continue
            src_json = m.get("source_raw_json")
            sr = loads_json(src_json, {}) if src_json else {}
            image_types = sr.get("image_types") if isinstance(sr.get("image_types"), dict) else {}
            for i, url in enumerate(images):
                typ = str(image_types.get(url) or "")
                conn.execute(
                    text(
                        "INSERT INTO draft_images (draft_id, position, url, type, source, created_at)"
                        " VALUES (:draft_id, :pos, :url, :typ, :src, :now)"
                    ),
                    {"draft_id": m["id"], "pos": i, "url": str(url), "typ": typ,
                     "src": "collected", "now": now},
                )
            inserted += 1
        if inserted:
            log.info(f"[store] draft_images backfill: {inserted} drafts migrated")
    except Exception as exc:  # noqa: BLE001
        log.warning(f"[store] draft_images backfill skipped: {exc}")
