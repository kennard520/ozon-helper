"""DraftRepo — drafts + draft_images 聚合的 SQLAlchemy Core 访问层。

等价替换 webui store.py 中的 drafts 聚合方法(parity 第一):
  insert_draft / update_draft / get_draft / list_drafts / list_drafts_page /
  count_by_status / find_by_source_url / find_by_offer_id / set_ai_proposal /
  delete_draft / set_media_status / apply_media_oss / list_pending_media_drafts /
  list_drafts_by_variant_group

以及私有辅助:
  _row_to_draft / _load_draft_images / _sync_draft_images /
  _variant_group_of / _group_keys / _unique_offer_id

约定(与 store.py 一致):
- user_id / store_client_id 的默认解析(_uid 等)仍在 Store 层做,repo 收解析后的值。
- offer_id 生成中需要 webui-only 的 validate_draft / _offer_id_base,故 Store 层
  预先算好 errors / status / offer_id_base 传入;repo 只做 source_url 去重 +
  offer_id 撞库去重(读 DB) + INSERT + 同步 draft_images。
- N+1 照旧:_row_to_draft 每行单独查 draft_images(与 store 完全一致,优化留 M5)。
- JSON 编解码用 ozon_common.jsonio(与 DraftImageRepo 同源)。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, insert, select, update

from ozon_common.dal.repositories.base import BaseRepo
from ozon_common.dal.schema import draft_images as DI
from ozon_common.dal.schema import drafts as D
from ozon_common.jsonio import dumps_json, loads_json, utc_now_iso


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, "", " "):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", " "):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class DraftRepo(BaseRepo):
    # ------------------------------------------------------------------
    # 写入 / 更新
    # ------------------------------------------------------------------

    def _unique_offer_id(self, base: str, exclude_id: int | None = None) -> str:
        """保证货号唯一:撞库就加 -2/-3。"""
        cand, n = base, 1
        while True:
            row = self.s.execute(
                select(D.c.id).where(D.c.offer_id == cand).limit(1)
            ).first()
            if not row or (exclude_id is not None and int(row.id) == int(exclude_id)):
                return cand
            n += 1
            cand = f"{base}-{n}"

    def insert_draft(
        self,
        draft: dict[str, Any],
        *,
        user_id: int,
        store_cid: str,
        errors: list[str],
        status: str,
        offer_id_base: str,
    ) -> dict[str, Any]:
        """INSERT 一条草稿(含 draft_images 同步)。

        与 store.insert_draft 一致:
          - 先按 (user, store, source_url) 去重,命中直接返回旧草稿;
          - offer_id:来源已带就用(Store 经 offer_id_base 传入);否则按 base 撞库去重;
          - INSERT 后 _sync_draft_images;
          - 返回 find_by_source_url(source_url, user_id) or draft。
        errors/status 由 Store 用 validate_draft 预先算好传入。
        """
        existing = self.find_by_source_url(draft["source_url"], user_id, store_cid)
        if existing:
            return existing
        # 来源已带 offer_id 就用;否则 Store 给的 offer_id_base 撞库去重
        offer_id_val = str(draft.get("offer_id") or "").strip()
        if not offer_id_val:
            offer_id_val = self._unique_offer_id(offer_id_base)
        res = self.s.execute(
            insert(D).values(
                user_id=int(user_id),
                store_client_id=store_cid,
                source_platform=draft.get("source_platform", "1688"),
                source_url=draft["source_url"],
                source_offer_id=draft.get("source_offer_id"),
                source_title=draft["source_title"],
                purchase_url=draft.get("purchase_url", ""),
                purchase_note=draft.get("purchase_note", ""),
                ozon_title=draft["ozon_title"],
                description=draft["description"],
                category_id=draft["category_id"],
                type_id=draft.get("type_id", ""),
                brand_id=_to_int_or_none(draft.get("brand_id")),
                brand_name=str(draft.get("brand_name") or ""),
                price=draft["price"],
                old_price=draft["old_price"],
                stock=draft["stock"],
                weight_g=draft.get("weight_g"),
                length_mm=draft.get("length_mm"),
                width_mm=draft.get("width_mm"),
                height_mm=draft.get("height_mm"),
                cost_cny=_to_float_or_none(draft.get("cost_cny")),
                video_url=str(draft.get("video_url") or ""),
                local_images_json=dumps_json(draft.get("local_images") or []),
                source=str(draft.get("source") or ""),
                ozon_product_id=_to_int_or_none(draft.get("ozon_product_id")),
                offer_id=offer_id_val,
                supplier=str(draft.get("supplier") or ""),
                source_raw_json=dumps_json(draft.get("source_raw") or {}),
                variant_group=str(
                    (draft.get("source_raw") or {}).get("variant_group") or ""
                ).strip(),
                images_json=dumps_json([]),
                attributes_json=dumps_json(draft["attributes"]),
                status=status,
                validation_errors_json=dumps_json(errors),
                publish_response_json=(
                    dumps_json(draft["publish_response"])
                    if draft["publish_response"] is not None
                    else None
                ),
                created_at=draft["created_at"],
                updated_at=draft["updated_at"],
            )
        )
        new_id = int(res.inserted_primary_key[0])
        self._sync_draft_images(
            new_id,
            draft["images"],
            (draft.get("source_raw") or {}).get("image_types"),
        )
        return self.find_by_source_url(draft["source_url"], user_id) or draft

    def update_draft(
        self,
        draft_id: int,
        updated: dict[str, Any],
        *,
        user_id: int,
        errors: list[str],
        status: str,
        sync_images: bool,
    ) -> dict[str, Any]:
        """UPDATE 一条草稿(含 draft_images 同步)。

        与 store.update_draft 一致:Store 已把 current 与 patch 合并成 updated、
        算好 errors/status,并标明是否需同步 images(patch 含 'images')。
        """
        self.s.execute(
            update(D)
            .where(D.c.id == int(draft_id))
            .values(
                source_platform=updated.get("source_platform", "1688"),
                source_title=updated["source_title"],
                purchase_url=updated.get("purchase_url", ""),
                purchase_note=updated.get("purchase_note", ""),
                ozon_title=updated["ozon_title"],
                description=updated["description"],
                category_id=updated["category_id"],
                type_id=str(updated.get("type_id") or ""),
                brand_id=_to_int_or_none(updated.get("brand_id")),
                brand_name=str(updated.get("brand_name") or ""),
                price=updated["price"],
                old_price=updated["old_price"],
                stock=int(updated["stock"]),
                weight_g=_to_int_or_none(updated.get("weight_g")),
                length_mm=_to_int_or_none(updated.get("length_mm")),
                width_mm=_to_int_or_none(updated.get("width_mm")),
                height_mm=_to_int_or_none(updated.get("height_mm")),
                cost_cny=_to_float_or_none(updated.get("cost_cny")),
                video_url=str(updated.get("video_url") or ""),
                local_images_json=dumps_json(updated.get("local_images") or []),
                source=str(updated.get("source") or ""),
                ozon_product_id=_to_int_or_none(updated.get("ozon_product_id")),
                offer_id=str(updated.get("offer_id") or ""),
                supplier=str(updated.get("supplier") or ""),
                warehouse_id=_to_int_or_none(updated.get("warehouse_id")),
                source_raw_json=dumps_json(updated.get("source_raw") or {}),
                variant_group=str(
                    (updated.get("source_raw") or {}).get("variant_group") or ""
                ).strip(),
                images_json=dumps_json([]),
                attributes_json=dumps_json(updated["attributes"]),
                status=status,
                validation_errors_json=dumps_json(errors),
                publish_response_json=(
                    dumps_json(updated.get("publish_response"))
                    if updated.get("publish_response") is not None
                    else None
                ),
                pricing_json=(
                    dumps_json(updated.get("pricing"))
                    if updated.get("pricing") is not None
                    else None
                ),
                updated_at=updated["updated_at"],
            )
        )
        if sync_images:
            self._sync_draft_images(
                draft_id,
                updated["images"],
                (updated.get("source_raw") or {}).get("image_types"),
            )
        draft = self.get_draft(draft_id, user_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found after update")
        return draft

    def set_ai_proposal(self, draft_id: int, proposal: dict | None) -> None:
        """写/清空草稿的 AI 待确认草案列;不触碰其它字段、不重算 status。"""
        self.s.execute(
            update(D)
            .where(D.c.id == int(draft_id))
            .values(
                ai_proposal_json=dumps_json(proposal) if proposal is not None else None
            )
        )

    def set_media_status(self, draft_id: int, status: str) -> None:
        self.s.execute(
            update(D)
            .where(D.c.id == int(draft_id))
            .values(media_status=str(status), updated_at=utc_now_iso())
        )

    def apply_media_oss(self, draft_id: int, media_map: dict) -> None:
        """把草稿 images/video_url 里命中 media_map 的原 URL 换成 OSS URL,并置 media_status=done。
        从 draft_images 表读、_sync_draft_images 写。"""
        imgs = [r["url"] for r in self._load_draft_images(draft_id)]
        if not imgs:
            return
        new_imgs = [media_map.get(u, u) for u in imgs]
        video_row = self.s.execute(
            select(D.c.video_url).where(D.c.id == int(draft_id))
        ).first()
        vurl = (video_row.video_url or "") if video_row else ""
        new_vurl = media_map.get(vurl, vurl)
        self.s.execute(
            update(D)
            .where(D.c.id == int(draft_id))
            .values(video_url=new_vurl, media_status="done", updated_at=utc_now_iso())
        )
        self._sync_draft_images(draft_id, new_imgs)

    def delete_draft(self, draft_id: int, user_id: int) -> None:
        self.s.execute(
            delete(D).where(D.c.id == int(draft_id), D.c.user_id == int(user_id))
        )
        self.s.execute(delete(DI).where(DI.c.draft_id == int(draft_id)))

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def list_pending_media_drafts(self, user_id: int) -> list[dict]:
        """当前用户 media_status=pending 的草稿,返回 [{id, images, video_url}],供插件补传。"""
        rows = self.s.execute(
            select(D.c.id, D.c.video_url).where(
                D.c.user_id == int(user_id), D.c.media_status == "pending"
            )
        ).all()
        return [
            {
                "id": r.id,
                "images": [x["url"] for x in self._load_draft_images(r.id)],
                "video_url": r.video_url or "",
            }
            for r in rows
        ]

    def list_drafts(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.s.execute(
            select(D).where(D.c.user_id == int(user_id)).order_by(D.c.id.desc())
        ).all()
        return [self._row_to_draft(row) for row in rows]

    def count_by_status(
        self,
        user_id: int,
        store_client_id: str | None = None,
        group: bool = False,
    ) -> dict[str, int]:
        """各状态计数 + all 总数。store_client_id 非 None 时按当前店过滤。
        group=True:按变体组计数(一个组算一条,组状态=代表/最新成员状态)。"""
        conds = [D.c.user_id == int(user_id)]
        if store_client_id is not None:
            conds.append(D.c.store_client_id == str(store_client_id or ""))
        counts = {"all": 0, "invalid": 0, "ready": 0, "failed": 0, "published": 0}
        if group:
            groups = self._group_keys(conds)
            for g in groups:
                if g["status"] in counts:
                    counts[g["status"]] += 1
            counts["all"] = len(groups)
            return counts
        counts["all"] = int(
            self.s.execute(select(func.count()).where(*conds)).scalar() or 0
        )
        rows = self.s.execute(
            select(D.c.status, func.count().label("c"))
            .where(*conds)
            .group_by(D.c.status)
        ).all()
        for r in rows:
            if r.status in counts:
                counts[r.status] += int(r.c)
        return counts

    def list_drafts_page(
        self,
        *,
        status: str = "all",
        page: int = 1,
        page_size: int = 20,
        user_id: int,
        store_client_id: str | None = None,
        group: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """真·后端分页:按 user_id + status (+当前店) 过滤 + LIMIT/OFFSET。
        返回 (当前页草稿, 该过滤下总数)。group=True 走变体组分页(口径同 count_by_status(group=True))。"""
        status = (status or "all").strip()
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))  # 上限 200,防一次拉爆
        base_conds = [D.c.user_id == int(user_id)]
        if store_client_id is not None:
            base_conds.append(D.c.store_client_id == str(store_client_id or ""))
        if group:
            groups = self._group_keys(base_conds)  # 轻量分组(不解析 JSON)
            if status not in ("", "all"):
                groups = [g for g in groups if g["status"] == status]
            total = len(groups)
            offset = (page - 1) * page_size
            page_groups = groups[offset : offset + page_size]
            if not page_groups:
                return [], total
            ids = [g["rep_id"] for g in page_groups]
            rows = self.s.execute(select(D).where(D.c.id.in_(ids))).all()
            by_id = {r._mapping["id"]: r for r in rows}
            out = []
            for g in page_groups:
                r = by_id.get(g["rep_id"])
                if r is None:
                    continue
                d = self._row_to_draft(r)
                d["group_count"] = g["count"]
                out.append(d)
            return out, total
        conds = list(base_conds)
        if status not in ("", "all"):
            conds.append(D.c.status == status)
        offset = (page - 1) * page_size
        total = int(self.s.execute(select(func.count()).where(*conds)).scalar() or 0)
        rows = self.s.execute(
            select(D)
            .where(*conds)
            .order_by(D.c.id.desc())
            .limit(page_size)
            .offset(offset)
        ).all()
        return [self._row_to_draft(r) for r in rows], total

    def get_draft(self, draft_id: int, user_id: int) -> dict[str, Any] | None:
        row = self.s.execute(
            select(D).where(D.c.id == int(draft_id), D.c.user_id == int(user_id))
        ).first()
        return self._row_to_draft(row) if row else None

    def find_by_source_url(
        self,
        source_url: str,
        user_id: int,
        store_client_id: str | None = None,
    ) -> dict[str, Any] | None:
        """按 (user, source_url) 查;store_client_id 非 None 时再按店过滤。"""
        conds = [D.c.source_url == source_url, D.c.user_id == int(user_id)]
        if store_client_id is not None:
            conds.append(D.c.store_client_id == str(store_client_id or ""))
        row = self.s.execute(
            select(D).where(*conds).order_by(D.c.id.desc()).limit(1)
        ).first()
        return self._row_to_draft(row) if row else None

    def find_by_offer_id(self, offer_id: str, user_id: int) -> dict[str, Any] | None:
        row = self.s.execute(
            select(D)
            .where(D.c.offer_id == str(offer_id), D.c.user_id == int(user_id))
            .order_by(D.c.id.desc())
            .limit(1)
        ).first()
        return self._row_to_draft(row) if row else None

    def list_drafts_by_variant_group(self, group: str) -> list[dict[str, Any]]:
        """返回同组草稿(按 id 升序)。走 variant_group 索引列,只取同组那几行。"""
        group = str(group or "").strip()
        if not group:
            return []
        rows = self.s.execute(
            select(D).where(D.c.variant_group == group).order_by(D.c.id.asc())
        ).all()
        return [self._row_to_draft(r) for r in rows]

    # ------------------------------------------------------------------
    # 私有辅助
    # ------------------------------------------------------------------

    def _variant_group_of(self, source_raw_json: Any) -> str:
        """从 source_raw_json 取 variant_group(同组合并键);无则空串。"""
        sr = loads_json(source_raw_json, {}) or {}
        return str((sr.get("variant_group") if isinstance(sr, dict) else "") or "").strip()

    def _group_keys(self, conds: list) -> list[dict[str, Any]]:
        """轻量分组索引:只取 id/status/variant_group,按 variant_group 归并成组。
        返回 [{rep_id, status, count}],代表=组内最新(id 最大),按代表 id DESC 排列。"""
        rows = self.s.execute(
            select(D.c.id, D.c.status, D.c.variant_group)
            .where(*conds)
            .order_by(D.c.id.desc())
        ).all()
        groups: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        for r in rows:
            vg = str(r.variant_group or "").strip()
            key = f"vg::{vg}" if vg else f"id::{r.id}"
            if key in seen:
                groups[seen[key]]["count"] += 1
            else:
                seen[key] = len(groups)
                groups.append({"rep_id": r.id, "status": r.status, "count": 1})
        return groups

    def _load_draft_images(self, draft_id: int) -> list[dict[str, Any]]:
        rows = self.s.execute(
            select(DI.c.url, DI.c.type, DI.c.source)
            .where(DI.c.draft_id == int(draft_id))
            .order_by(DI.c.position)
        ).all()
        return [{"url": r.url, "type": r.type, "source": r.source} for r in rows]

    def _sync_draft_images(
        self,
        draft_id: int,
        images: list[str],
        image_types: dict[str, str] | None = None,
    ) -> None:
        """把 images 数组同步到 draft_images 表行。
        保留旧行已有的 type/source(按 url 匹配),新图用 image_types 或兜底。"""
        now = utc_now_iso()
        old_rows = self.s.execute(
            select(DI.c.url, DI.c.type, DI.c.source).where(
                DI.c.draft_id == int(draft_id)
            )
        ).all()
        old_map: dict[str, tuple[str, str]] = {}
        for r in old_rows:
            old_map[str(r.url)] = (str(r.type or ""), str(r.source or ""))
        types = dict(image_types or {})
        self.s.execute(delete(DI).where(DI.c.draft_id == int(draft_id)))
        for i, url in enumerate(images):
            url = str(url)
            prev = old_map.get(url)
            typ = types.get(url) or (prev[0] if prev else "") or "其他"
            src = prev[1] if prev else "collected"
            self.s.execute(
                insert(DI).values(
                    draft_id=int(draft_id),
                    position=i,
                    url=url,
                    type=typ,
                    source=src,
                    created_at=now,
                )
            )

    def _row_to_draft(self, row) -> dict[str, Any]:
        m = row._mapping
        source_platform = m["source_platform"]
        purchase_url = m["purchase_url"] or (
            m["source_url"] if source_platform == "1688" else ""
        )
        # 图片全部从 draft_images 一对多表读;images_json 列已停用
        dimg_rows = self._load_draft_images(m["id"])
        images = [r["url"] for r in dimg_rows]
        image_types = {r["url"]: r["type"] for r in dimg_rows if r["type"]}
        sr = loads_json(m["source_raw_json"], {})
        if image_types:
            sr["image_types"] = image_types
        elif "image_types" not in sr:
            sr["image_types"] = {}
        return {
            "id": m["id"],
            "user_id": m["user_id"],
            "store_client_id": m["store_client_id"],
            "source_platform": source_platform,
            "source_url": m["source_url"],
            "source_offer_id": m["source_offer_id"],
            "source": m["source"],
            "ozon_product_id": m["ozon_product_id"],
            "offer_id": m["offer_id"],
            "supplier": m["supplier"],
            "warehouse_id": m["warehouse_id"],
            "source_raw": sr,
            "source_title": m["source_title"],
            "purchase_url": purchase_url,
            "purchase_note": m["purchase_note"],
            "ozon_title": m["ozon_title"],
            "description": m["description"],
            "category_id": m["category_id"],
            "type_id": m["type_id"],
            "brand_id": m["brand_id"],
            "brand_name": m["brand_name"],
            "price": m["price"],
            "old_price": m["old_price"],
            "stock": m["stock"],
            "weight_g": m["weight_g"],
            "length_mm": m["length_mm"],
            "width_mm": m["width_mm"],
            "height_mm": m["height_mm"],
            "images": images,
            "attributes": loads_json(m["attributes_json"], {}),
            "cost_cny": m["cost_cny"],
            "video_url": m["video_url"] or "",
            "local_images": loads_json(m["local_images_json"], []),
            "status": m["status"],
            "validation_errors": loads_json(m["validation_errors_json"], []),
            "publish_response": loads_json(m["publish_response_json"], None),
            "pricing": loads_json(m["pricing_json"], None),
            "ai_proposal": loads_json(m["ai_proposal_json"], None),
            "media_status": m["media_status"] or "done",
            "created_at": m["created_at"],
            "updated_at": m["updated_at"],
        }
