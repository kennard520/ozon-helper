from __future__ import annotations

from typing import Any

from webui.drafts import NO_BRAND, utc_now_iso


PROTECTED_OZON_FIELDS = (
    "ozon_title",
    "description",
    "category_id",
    "type_id",
    "attributes",
    "price",
    "old_price",
    "stock",
    "images",
    "video_url",
    "weight_g",
    "length_mm",
    "width_mm",
    "height_mm",
    "supplier",
    "purchase_url",
    "purchase_note",
    "cost_cny",
)


def _empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


class OzonSyncMixin:
    @staticmethod
    def _variant_warning(info: dict) -> str | None:
        model_info = info.get("model_info") or {}
        try:
            count = int(model_info.get("count") or 0)
        except (TypeError, ValueError, AttributeError):
            count = 0
        if count <= 1:
            return None
        return f"该 Ozon 商品属于包含 {count} 个 SKU 的变体组；本次仅导入当前 SKU。"

    @classmethod
    def _sync_snapshot(
        cls,
        *,
        sku: int,
        info: dict,
        attributes: dict | None,
        description: str,
    ) -> dict:
        return {
            "sku": int(sku),
            "synced_at": utc_now_iso(),
            "info": info,
            "attributes": attributes,
            "description": description,
            "variant_warning": cls._variant_warning(info),
        }

    @staticmethod
    def _safe_error(exc: Exception, settings: dict | None = None) -> str:
        message = str(exc)[:500]
        configured = settings or {}
        secrets = [configured.get("ozon_api_key")]
        secrets.extend(st.get("api_key") for st in configured.get("ozon_stores") or [])
        for secret in secrets:
            secret_text = str(secret or "")
            if secret_text:
                message = message.replace(secret_text, "***")
        return message or type(exc).__name__

    def _remote_draft_by_sku(
        self,
        sku: int,
        store_client_id: str,
    ) -> tuple[dict, list[str]]:
        from webui.ozon_client_adapter import (  # noqa: PLC0415
            get_ozon_attributes,
            get_ozon_descriptions,
            get_ozon_info_by_skus,
            ozon_to_draft,
        )

        scid = str(store_client_id or "").strip()
        settings = self._settings_for_store(scid)
        info_by_sku = get_ozon_info_by_skus(settings, [int(sku)])
        info = info_by_sku.get(str(sku))
        if not info:
            raise KeyError(f"Ozon SKU {sku} 不存在或不属于店铺 {scid}")
        offer_id = str(info.get("offer_id") or "").strip()
        if not offer_id:
            raise ValueError(f"Ozon SKU {sku} 未返回 offer_id")

        warnings: list[str] = []
        attributes: dict | None = None
        try:
            settings = self._settings_for_store(scid)
            attributes = get_ozon_attributes(settings, [offer_id]).get(offer_id)
            if attributes is None:
                warnings.append("属性未获取，尺寸和商品属性留空")
        except Exception as exc:  # noqa: BLE001
            settings = self._settings_for_store(scid)
            warnings.append(f"属性拉取失败，尺寸和商品属性留空: {self._safe_error(exc, settings)}")

        description = ""
        try:
            settings = self._settings_for_store(scid)
            description = str(get_ozon_descriptions(settings, [offer_id]).get(offer_id) or "")
            if not description:
                warnings.append("描述未获取，描述字段留空")
        except Exception as exc:  # noqa: BLE001
            settings = self._settings_for_store(scid)
            warnings.append(f"描述拉取失败，描述字段留空: {self._safe_error(exc, settings)}")

        draft = ozon_to_draft(info, attributes)
        if description:
            draft["description"] = description
        snapshot = self._sync_snapshot(
            sku=sku,
            info=info,
            attributes=attributes,
            description=description,
        )
        return self._normalize_ozon_draft(
            draft,
            sku=sku,
            store_client_id=scid,
            snapshot=snapshot,
        ), warnings

    @staticmethod
    def _diff_editable_fields(existing: dict, remote: dict) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for field in PROTECTED_OZON_FIELDS:
            local_value = existing.get(field)
            remote_value = remote.get(field)
            if (_empty(local_value) or _empty(remote_value)
                    or local_value == remote_value):
                continue
            conflicts.append({
                "field": field,
                "local": local_value,
                "remote": remote_value,
            })
        return conflicts

    @staticmethod
    def _normalize_ozon_draft(
        draft: dict,
        *,
        sku: int,
        store_client_id: str,
        snapshot: dict,
    ) -> dict:
        normalized = dict(draft)
        now = utc_now_iso()
        source_raw = dict(normalized.get("source_raw") or {})
        source_raw["ozon_sync"] = snapshot
        normalized.update({
            "store_client_id": str(store_client_id),
            "source": "ozon",
            "source_platform": "ozon",
            "source_offer_id": str(sku),
            "source_url": f"ozon://product/{sku}",
            "source_raw": source_raw,
            "status": "published",
        })
        normalized.setdefault("purchase_url", "")
        normalized.setdefault("purchase_note", "")
        normalized["brand_id"] = None
        normalized["brand_name"] = NO_BRAND
        normalized.setdefault("cost_cny", None)
        normalized.setdefault("video_url", "")
        normalized.setdefault("local_images", [])
        normalized.setdefault("validation_errors", [])
        normalized.setdefault("publish_response", None)
        normalized["created_at"] = now
        normalized["updated_at"] = now
        return normalized

    @staticmethod
    def _merge_pulled_into_existing(
        existing: dict,
        pulled: dict,
        selected_fields: list[str] | None = None,
    ) -> dict:
        selected = None if selected_fields is None else set(selected_fields)
        patch: dict[str, Any] = {}
        for field in PROTECTED_OZON_FIELDS:
            if field not in pulled:
                continue
            remote_value = pulled.get(field)
            if _empty(existing.get(field)) and not _empty(remote_value):
                patch[field] = remote_value
            elif selected is not None and field in selected:
                patch[field] = remote_value

        if pulled.get("ozon_product_id") is not None:
            patch["ozon_product_id"] = pulled["ozon_product_id"]
        patch.update({
            "source": "ozon",
            "source_platform": "ozon",
            "source_raw": pulled.get("source_raw") or {},
            "offer_id": existing.get("offer_id") or pulled.get("offer_id"),
            "status": "published",
        })
        return patch

    def import_ozon_product_by_sku(
        self,
        sku: int,
        store_client_id: str,
        selected_fields: list[str] | None = None,
    ) -> dict:
        sku = int(sku)
        if sku <= 0:
            raise ValueError("SKU 必须是正整数")
        scid = str(store_client_id or "").strip()
        if not scid:
            raise ValueError("store_client_id 不能为空")

        remote, warnings = self._remote_draft_by_sku(sku, scid)
        existing = self.store.find_ozon_draft(
            store_client_id=scid,
            sku=str(sku),
            product_id=remote.get("ozon_product_id"),
            offer_id=str(remote.get("offer_id") or ""),
        )
        if existing is None:
            draft = self.store.insert_draft(remote)
            return {
                "created": True,
                "draft": draft,
                "conflicts": [],
                "warnings": warnings,
            }

        conflicts = self._diff_editable_fields(existing, remote)
        patch = self._merge_pulled_into_existing(existing, remote, selected_fields)
        draft = self.store.update_draft(existing["id"], patch)
        return {
            "created": False,
            "draft": draft,
            "conflicts": conflicts,
            "warnings": warnings,
        }

    def sync_ozon_products(
        self,
        store_client_id: str,
        visibility: str = "ALL",
    ) -> dict:
        from webui.ozon_client_adapter import (  # noqa: PLC0415
            get_ozon_attributes,
            get_ozon_descriptions,
            get_ozon_info,
            list_ozon_products,
            ozon_to_draft,
        )

        scid = str(store_client_id or "").strip()
        settings = self._settings_for_store(scid)
        if not scid:
            scid = str(settings.get("ozon_client_id") or "").strip()
        run = self.store.create_task_run(
            None,
            "ozon_product_pull",
            status="running",
            source="webui",
            result={"phase": "start", "visibility": visibility, "store_client_id": scid},
        )
        errors: list[str] = []
        warnings: list[str] = []
        try:
            listing = list_ozon_products(self._settings_for_store(scid), visibility)
        except Exception as exc:  # noqa: BLE001
            error = self._safe_error(exc, settings)
            self.store.update_task_run(run["id"], {
                "status": "failed",
                "error": error,
                "result": {"phase": "list_products", "visibility": visibility},
            })
            return {
                "created": 0,
                "updated": 0,
                "preserved": 0,
                "failed": 1,
                "pulled": 0,
                "drafts": self.store.list_drafts(),
                "errors": [error],
                "warnings": [],
            }

        offer_ids = [str(item.get("offer_id")) for item in listing if item.get("offer_id")]
        try:
            info = get_ozon_info(self._settings_for_store(scid), offer_ids) if offer_ids else {}
        except Exception as exc:  # noqa: BLE001
            error = self._safe_error(exc, settings)
            self.store.update_task_run(run["id"], {
                "status": "failed",
                "error": error,
                "result": {"phase": "product_info", "visibility": visibility},
            })
            return {
                "created": 0,
                "updated": 0,
                "preserved": 0,
                "failed": len(offer_ids),
                "pulled": 0,
                "drafts": self.store.list_drafts(),
                "errors": [error],
                "warnings": [],
            }

        try:
            attributes = get_ozon_attributes(
                self._settings_for_store(scid), offer_ids,
            ) if offer_ids else {}
        except Exception as exc:  # noqa: BLE001
            attributes = {}
            warnings.append(f"属性拉取失败，尺寸和商品属性留空: {self._safe_error(exc, settings)}")
        try:
            descriptions = get_ozon_descriptions(
                self._settings_for_store(scid), offer_ids,
            ) if offer_ids else {}
        except Exception as exc:  # noqa: BLE001
            descriptions = {}
            warnings.append(f"描述拉取失败，描述字段留空: {self._safe_error(exc, settings)}")

        listing_by_offer = {
            str(item.get("offer_id")): item for item in listing if item.get("offer_id")
        }
        created = updated = preserved = failed = pulled = 0
        for offer_id in offer_ids:
            remote_info = info.get(offer_id)
            if remote_info is None:
                failed += 1
                errors.append(f"offer_id {offer_id}: 未返回商品详情")
                continue
            try:
                listing_item = listing_by_offer.get(offer_id) or {}
                sku_value = remote_info.get("sku") or listing_item.get("sku")
                if not sku_value:
                    # 兼容旧 info/list 响应及现有拉取调用；新 API 响应优先使用真实 SKU。
                    sku_value = remote_info.get("id") or listing_item.get("product_id")
                sku = int(sku_value)
                remote = ozon_to_draft(remote_info, attributes.get(offer_id))
                description = str(descriptions.get(offer_id) or "")
                if description:
                    remote["description"] = description
                snapshot = self._sync_snapshot(
                    sku=sku,
                    info=remote_info,
                    attributes=attributes.get(offer_id),
                    description=description,
                )
                remote = self._normalize_ozon_draft(
                    remote,
                    sku=sku,
                    store_client_id=scid,
                    snapshot=snapshot,
                )
                existing = self.store.find_ozon_draft(
                    store_client_id=scid,
                    sku=str(sku),
                    product_id=remote.get("ozon_product_id"),
                    offer_id=offer_id,
                )
                if existing is None:
                    self.store.insert_draft(remote)
                    created += 1
                else:
                    conflicts = self._diff_editable_fields(existing, remote)
                    patch = self._merge_pulled_into_existing(existing, remote)
                    self.store.update_draft(existing["id"], patch)
                    if conflicts:
                        preserved += 1
                    else:
                        updated += 1
                pulled += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append(f"offer_id {offer_id}: {self._safe_error(exc, settings)}")

        result = {
            "phase": "done",
            "visibility": visibility,
            "store_client_id": scid,
            "created": created,
            "updated": updated,
            "preserved": preserved,
            "failed": failed,
            "pulled": pulled,
            "warnings": warnings,
        }
        self.store.update_task_run(run["id"], {
            "status": "done",
            "progress_current": 1,
            "progress_total": 1,
            "error": errors[0] if errors else (warnings[0] if warnings else None),
            "result": result,
        })
        return {
            **result,
            "drafts": self.store.list_drafts(),
            "errors": errors or warnings,
        }
