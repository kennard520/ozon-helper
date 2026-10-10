from __future__ import annotations


class WarehouseMixin:
    """仓库同步 / FBS 备货发货。"""

    def _scid_of(self, store_client_id: str | None) -> str:
        """把(可能为空的)目标店解析成实际 client_id：空→默认店。仓库/订单按它隔离。"""
        return str(self._settings_for_store(store_client_id).get("ozon_client_id") or "")

    def _warehouses_with_delivery(self, scid: str) -> list[dict]:
        """仓库列表，每个仓库挂上它的配送方式（本地按 warehouse_id 分组）。"""
        warehouses = self.store.list_warehouses(scid)
        methods = self.store.list_delivery_methods(scid)
        by_wh: dict[int, list[dict]] = {}
        for m in methods:
            by_wh.setdefault(m.get("warehouse_id"), []).append(m)
        for w in warehouses:
            w["delivery_methods"] = by_wh.get(w.get("warehouse_id"), [])
        return warehouses

    def list_warehouses(self, store_client_id: str | None = None) -> dict:
        scid = self._scid_of(store_client_id)
        return {"warehouses": self._warehouses_with_delivery(scid)}

    def sync_warehouses(self, store_client_id: str | None = None) -> dict:
        from webui.ozon_client_adapter import (  # noqa: PLC0415
            fetch_delivery_methods,
            fetch_warehouses,
        )
        run = self.store.create_task_run(None, "warehouse_sync", status="running", source="webui", result={"phase": "start"})
        settings = self._settings_for_store(store_client_id)
        scid = str(settings.get("ozon_client_id") or "")
        try:
            items = fetch_warehouses(settings)
            self.store.upsert_warehouses(items, scid)
            # 配送方式挂在仓库下：仓库同步完后逐仓拉取，按店全量替换
            wids = [w.get("warehouse_id") for w in self.store.list_warehouses(scid)]
            methods = fetch_delivery_methods(settings, wids)
            self.store.replace_delivery_methods(methods, scid)
            result = {
                "synced": len(items),
                "delivery_methods": len(methods),
                "warehouses": self._warehouses_with_delivery(scid),
            }
            self.store.update_task_run(run["id"], {"status": "done", "progress_current": 1, "progress_total": 1, "result": {"phase": "done", "synced": len(items), "delivery_methods": len(methods), "store_client_id": scid}})
            return result
        except Exception as exc:
            self.store.update_task_run(run["id"], {"status": "failed", "error": str(exc)[:500], "result": {"phase": "failed", "store_client_id": scid}})
            raise

    def store_stats(self, store_client_id: str | None = None) -> dict:
        from webui.ozon_client_adapter import (  # noqa: PLC0415
            count_ozon_products,
            fetch_finance_balance,
        )
        settings = self._settings_for_store(store_client_id)
        scid = str(settings.get("ozon_client_id") or "")
        product_count = count_ozon_products(settings)
        balance = {"amount": None, "currency_code": ""}
        balance_error = ""
        try:
            balance = fetch_finance_balance(settings)
        except Exception as exc:  # noqa: BLE001
            balance_error = str(exc)
        return {
            "store_client_id": scid,
            "product_count": product_count,
            "balance": balance,
            "balance_error": balance_error,
        }

    def set_default_warehouse(self, warehouse_id: int, store_client_id: str | None = None) -> dict:
        scid = self._scid_of(store_client_id)
        self.store.set_default_warehouse(int(warehouse_id), scid)
        return {"warehouses": self._warehouses_with_delivery(scid)}

    # ---------- 功能⑤：FBS 备货发货 ----------
    def pull_fbs(self, status: str = "awaiting_packaging", days: int = 14,
                 store_client_id: str | None = None) -> dict:
        from webui.ozon_client_adapter import pull_fbs_postings  # noqa: PLC0415
        run = self.store.create_task_run(None, "fbs_pull", status="running", source="webui", result={"phase": "start", "status": status, "days": days})
        settings = self._settings_for_store(store_client_id)
        scid = str(settings.get("ozon_client_id") or "")
        try:
            items = pull_fbs_postings(settings, status, days)
            self.store.upsert_postings(items, scid)
            self.store.rebuild_procurement(scid)
            result = {"synced": len(items), "procurement": self.store.list_procurement(scid)}
            self.store.update_task_run(run["id"], {"status": "done", "progress_current": 1, "progress_total": 1, "result": {"phase": "done", "synced": len(items), "store_client_id": scid}})
            return result
        except Exception as exc:
            self.store.update_task_run(run["id"], {"status": "failed", "error": str(exc)[:500], "result": {"phase": "failed", "store_client_id": scid}})
            raise

    def list_procurement(self, store_client_id: str | None = None) -> dict:
        scid = self._scid_of(store_client_id)
        return {"procurement": self.store.list_procurement(scid)}

    def set_procurement_state(self, pid: int, purchase_state: str, note: str = "",
                              store_client_id: str | None = None) -> dict:
        self.store.set_procurement_state(int(pid), purchase_state, note=note)
        return {"procurement": self.store.list_procurement(self._scid_of(store_client_id))}

    def ship_posting(self, posting_number: str, store_client_id: str | None = None) -> dict:
        """按 posting 的商品组成一个包发货。不可逆。
        Ozon 发货请求要 product_id（swagger 里与 sku 是不同 ID）；而待发货单只带
        offer_id/sku，没有 product_id。故先用 offer_id 反查真实 product_id（info.id），
        绝不拿 sku 顶替——否则会发错货或被 Ozon 拒。"""
        from webui.ozon_client_adapter import get_ozon_info, ship_fbs  # noqa: PLC0415
        posting = self.store.get_posting(posting_number)
        if not posting:
            raise KeyError(f"posting {posting_number} not found")
        items = posting.get("products") or []
        offer_ids = [str(p.get("offer_id")) for p in items if p.get("offer_id")]
        if not offer_ids:
            raise ValueError("该 posting 无 offer_id，无法解析 product_id")
        settings = self._settings_for_store(store_client_id)
        try:
            info = get_ozon_info(settings, offer_ids)   # {offer_id: {id=product_id, ...}}
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"拉取商品信息失败，无法发货: {exc}") from exc
        products, missing = [], []
        for p in items:
            oid = str(p.get("offer_id") or "")
            pid = (info.get(oid) or {}).get("id")
            if not pid:
                missing.append(oid or "?")
                continue
            products.append({"product_id": int(pid), "quantity": int(p.get("quantity") or 1)})
        if missing:
            raise ValueError(f"无法解析 product_id 的商品: {', '.join(missing)}")
        if not products:
            raise ValueError("该 posting 无可发货商品")
        # warehouse_id 不传给 Ozon：/v4/posting/fbs/ship 接口只接受 posting_number + packages，
        # Ozon 从 posting 本身推断仓库，无需（也不接受）warehouse_id 参数。
        r = ship_fbs(settings, posting_number, [{"products": products}])
        return {"result": r.get("result") or [], "shipped": True, "response": r}
