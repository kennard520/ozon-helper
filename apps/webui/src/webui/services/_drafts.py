"""DraftMixin —— 草稿 CRUD / 基础管理。"""
from __future__ import annotations

from webui.drafts import NO_BRAND, utc_now_iso
from webui.services._helpers import _to_int, step_flags


class DraftMixin:
    def list_drafts(self, *, status: str = "all", page: int = 1, page_size: int = 20,
                    store_client_id: str | None = None) -> dict:
        """草稿绑定店：store_client_id 非 None 时只返回该店草稿（计数同）。
        没传 store_client_id → 回退默认店：先 settings.ozon_client_id，再 ozon_stores 里 is_default/第一个店。
        绝不"不带店=全店混列"（会和前端"带当前店"的请求结果打架，草稿忽有忽无）；
        只有完全没配任何店时才退回不过滤(单店/旧数据兼容)。"""
        if store_client_id is None:
            s = self.store.get_settings() or {}
            default_store = str(s.get("ozon_client_id") or "")
            if not default_store:
                stores = s.get("ozon_stores") or []
                if stores:
                    dft = next((x for x in stores if x.get("is_default")), stores[0])
                    default_store = str(dft.get("client_id") or "")
            store_client_id = default_store or None
        scid = None if store_client_id is None else str(store_client_id or "")
        # 列表按变体组聚合：同组只出一行(代表)，Tab 计数同口径——避免数字对不上/同组跨页重复
        drafts, total = self.store.list_drafts_page(
            status=status, page=page, page_size=page_size, store_client_id=scid, group=True)
        return {
            "drafts": drafts,
            "total": total,
            "page": max(1, int(page)),
            "page_size": max(1, min(int(page_size), 200)),
            "counts": self.store.count_by_status(store_client_id=scid, group=True),
        }

    def get_draft(self, draft_id: int) -> dict:
        """单草稿明细：分组列表里只出代表行，点变体组里某个兄弟变体编辑时，它可能不在当前页，
        据此单独按 id 拉一份。这是用户主动点选时的必要加载，不是每次动作都拉整份。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        return {"draft": draft}

    def regenerate_offer_id(self, draft_id: int) -> dict:
        """按 {平台}-{变体维度} 重新生成货号（撞库自动去重），写入草稿。给「重新生成」按钮用。"""
        from webui.store import _offer_id_base  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        base = _offer_id_base(draft.get("source_platform"), draft.get("source_raw"))
        new = self.store._unique_offer_id(base, exclude_id=draft_id)
        updated = self.store.update_draft(draft_id, {"offer_id": new})
        return {"ok": True, "offer_id": new, "draft": updated}

    def copy_draft_to_store(self, draft_id: int, target_client_id: str) -> dict:
        """把草稿复制到另一个店：克隆内容（标题/类目/属性/媒体/尺寸/描述/采购信息），
        重置店级字段（store_client_id=目标店、状态重算、清 ozon_product_id/库存/仓库/发布响应）。
        目标店已有同来源草稿则拦截，不重复建。"""
        from webui.drafts import utc_now_iso  # noqa: PLC0415
        target = str(target_client_id or "").strip()
        if not target:
            return {"ok": False, "error": "未指定目标店铺"}
        src = self.store.get_draft(draft_id)
        if src is None:
            raise KeyError(f"draft {draft_id} not found")
        if str(src.get("store_client_id") or "") == target:
            return {"ok": False, "error": "目标店与当前店相同"}
        dup = self.store.find_by_source_url(src["source_url"], None, target)
        if dup:
            return {"ok": False, "error": "该店已存在此来源商品", "draft_id": dup["id"]}
        now = utc_now_iso()
        clone = {
            **src,
            "store_client_id": target,
            "ozon_product_id": None,
            "stock": 0,
            "warehouse_id": None,
            "publish_response": None,
            "status": "ready",          # insert_draft 会按校验结果改成 invalid（缺字段时）
            "created_at": now,
            "updated_at": now,
        }
        clone.pop("id", None)
        saved = self.store.insert_draft(clone)
        return {"ok": True, "draft": saved}

    def update_draft(self, draft_id: int, payload: dict) -> dict:
        current = self.store.get_draft(draft_id)
        if current is None:
            raise KeyError(f"draft {draft_id} not found")
        normalized = dict(payload or {})
        brand_name = str(normalized.get("brand_name") or current.get("brand_name") or "").strip()
        brand_id = normalized.get("brand_id", current.get("brand_id"))
        normalized["brand_id"] = brand_id if brand_name == NO_BRAND and _to_int(brand_id) > 0 else None
        normalized["brand_name"] = NO_BRAND
        draft = self.store.update_draft(draft_id, normalized)
        # 类别变更 → 同步到同组其它变体（合并成一张 Ozon 卡，类别必须一致）
        if "category_id" in normalized or "type_id" in normalized:
            self._sync_group_category(draft, draft.get("category_id"), draft.get("type_id"),
                                      str(draft.get("category_path") or ""))
        return {"draft": draft}

    def _sync_group_category(self, draft: dict, cat, typ, path: str = "") -> int:
        """同组变体合并成一张 Ozon 多变体卡，一张卡只有一个类别 → 把类别同步到本组所有兄弟变体。
        返回改动的兄弟数（已一致的跳过）。无 variant_group / 类别不全则不动。"""
        from webui.drafts import loads_json  # noqa: PLC0415
        cat_s, typ_s = str(cat or "").strip(), str(typ or "").strip()
        if not cat_s or not typ_s:
            return 0
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        group = str((sr or {}).get("variant_group") or "").strip()
        if not group:
            return 0
        patch = {"category_id": cat_s, "type_id": typ_s}
        if path:
            patch["category_path"] = path
        n = 0
        for sib in self.store.list_drafts_by_variant_group(group):
            if int(sib["id"]) == int(draft["id"]):
                continue
            if str(sib.get("category_id") or "") == cat_s and str(sib.get("type_id") or "") == typ_s:
                continue
            self.store.update_draft(int(sib["id"]), dict(patch))
            n += 1
        return n

    def batch_update_drafts(self, ids: list, patch: dict) -> dict:
        """批量给多个草稿打同一个补丁（目前用于批量设库存/仓库）。
        只放行安全的批量字段；逐条复用 update_draft，并保留各自原 status——
        否则未传 status 时 update_draft 会重算，把已发布草稿误降级为 ready。"""
        allowed = {k: v for k, v in (patch or {}).items() if k in ("stock", "warehouse_id")}
        if not allowed:
            raise ValueError("没有可批量设置的字段（仅支持 stock / warehouse_id）")
        updated, errors = [], []
        for did in ids or []:
            try:
                cur = self.store.get_draft(int(did))
                if cur is None:
                    errors.append({"id": did, "error": "草稿不存在"})
                    continue
                # 保留原 status，避免批量改库存/仓库时被重算降级
                draft = self.store.update_draft(int(did), {**allowed, "status": cur.get("status")})
                updated.append(draft)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": did, "error": str(exc)})
        return {"updated": updated, "errors": errors}

    def delete(self, draft_id: int, scope: str = "auto") -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        # 删除草稿只清理本地工作台记录，不级联下架/删除 Ozon 线上商品。
        # 线上商品的下架、归档、删除必须走单独的显式操作，避免误删已发布商品。
        scope_norm = str(scope or "auto").strip().lower()
        deleted_ids = [int(draft_id)]
        from webui.drafts import loads_json  # noqa: PLC0415
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        group = str((sr or {}).get("variant_group") or "").strip()
        if group and scope_norm in {"group", "auto", ""}:
            siblings = self.store.list_drafts_by_variant_group(group)
            sibling_ids = [int(d["id"]) for d in siblings]
            is_group_rep = bool(sibling_ids) and int(draft_id) == max(sibling_ids)
            if scope_norm == "group" or is_group_rep:
                deleted_ids = sibling_ids
        for did in deleted_ids:
            self.store.delete_draft(did)
        # 不再回传全量 drafts（list_drafts 会把全部草稿全字段序列化，又慢又大；前端删除后自行 removeDraft/重拉分页）
        return {
            "deleted": True,
            "id": draft_id,
            "ids": deleted_ids,
            "scope": "group" if len(deleted_ids) > 1 else "single",
            "ozon_deleted": False,
            "ozon_response": None,
            "ozon_error": None,
        }

    def variant_group_siblings(self, draft_id: int) -> dict:
        """该草稿所属变体组的兄弟变体清单(轻量)，供编辑器展示「共 N 变体」+ 区别规格。"""
        from webui.drafts import loads_json  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        group = str((sr or {}).get("variant_group") or "").strip()
        if not group:
            return {"ok": True, "group": "", "variants": [], "count": 0}
        out = []
        for d in self.store.list_drafts_by_variant_group(group):
            dsr = d.get("source_raw")
            if isinstance(dsr, str):
                dsr = loads_json(dsr, {})
            dsr = dsr or {}
            flags = step_flags(d)
            preview_image = (list(d.get("images") or [])[:1] or [""])[0]
            if not preview_image:
                preview_image = next(
                    (str(m.get("local_url") or m.get("url") or "") for m in (d.get("materials") or [])
                     if str(m.get("local_url") or m.get("url") or "")),
                    "",
                )
            out.append({"id": d.get("id"),
                        "spec": str(dsr.get("spec_attrs") or dsr.get("variant_label") or "").strip(),
                        "price": d.get("price"), "status": d.get("status"),
                        "image": preview_image,
                        "current": d.get("id") == draft_id,
                        "steps": flags,
                        "done": sum(1 for v in flags.values() if v)})
        return {"ok": True, "group": group, "variants": out, "count": len(out)}
