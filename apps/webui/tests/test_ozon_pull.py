from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


# 用 plan §11 已核实的字段形状构造假 info / attrs
def _fake_info(offer_id="A", pid=111, price="799", images=None, primary=None,
               stocks_present=7, cat=17028922, type_id=94307, name="Товар"):
    info = {
        "id": pid,
        "offer_id": offer_id,
        "name": name,
        "price": price,
        "old_price": "999",
        "currency_code": "RUB",
        "description_category_id": cat,
        "type_id": type_id,
        "primary_image": primary if primary is not None else ["https://img/primary.jpg"],
        "images": images if images is not None else [],
        "stocks": {"stocks": [{"present": stocks_present, "reserved": 0}]},
    }
    return info


def _fake_attrs(offer_id="A", weight=500, depth=300, width=200, height=100,
                attributes=None,
                video="https://v-1.ozone.ru/x.mp4"):
    return {
        "id": 111,
        "offer_id": offer_id,
        "description_category_id": 17028922,
        "type_id": 94307,
        "weight": weight,
        "weight_unit": "g",
        "depth": depth,
        "width": width,
        "height": height,
        "dimension_unit": "mm",
        "attributes": attributes if attributes is not None else [{"id": 4180, "values": [{"value": "X"}]}],
        "complex_attributes": [
            {"id": 21837, "complex_id": 100001, "values": [{"value": "name"}]},
            {"id": 21841, "complex_id": 100001, "values": [{"value": video}]},
        ] if video else [],
    }


class OzonToDraftTest(unittest.TestCase):
    def test_pure_mapping_merges_info_and_attrs(self) -> None:
        from webui.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415
        info = _fake_info(images=["https://img/a.jpg", "https://img/b.jpg"])
        attrs = _fake_attrs()
        d = ozon_to_draft(info, attrs)
        self.assertEqual(d["source"], "ozon")
        self.assertEqual(d["ozon_product_id"], 111)
        self.assertEqual(d["offer_id"], "A")
        self.assertEqual(d["category_id"], "17028922")
        self.assertEqual(d["type_id"], "94307")
        self.assertEqual(d["price"], "799")            # 字符串
        self.assertIsInstance(d["price"], str)
        self.assertEqual(d["images"], ["https://img/a.jpg", "https://img/b.jpg"])
        self.assertEqual(d["stock"], 7)                # stocks[].present
        self.assertEqual(d["length_mm"], 300)          # Ozon 300mm → 内部 300mm
        self.assertEqual(d["width_mm"], 200)
        self.assertEqual(d["height_mm"], 100)
        self.assertEqual(d["weight_g"], 500)           # attrs weight(g)
        self.assertEqual(d["attributes"], attrs["attributes"])
        self.assertEqual(d["status"], "published")
        # video_url 从 complex_attributes id=21841 中提取
        self.assertEqual(d["video_url"], "https://v-1.ozone.ru/x.mp4")

    def test_video_url_empty_when_no_complex_attributes(self) -> None:
        """attrs 为 None 或无 complex_attributes 时 video_url 应为空字符串。"""
        from webui.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415
        info = _fake_info()
        # attrs=None
        d = ozon_to_draft(info, None)
        self.assertEqual(d["video_url"], "")
        # attrs 有 complex_attributes 但无 id=21841
        attrs_no_video = _fake_attrs(video="")
        d2 = ozon_to_draft(info, attrs_no_video)
        self.assertEqual(d2["video_url"], "")

    def test_images_fallback_to_primary_when_empty(self) -> None:
        from webui.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415
        info = _fake_info(images=[], primary=["https://img/primary.jpg"])
        d = ozon_to_draft(info, None)
        self.assertEqual(d["images"], ["https://img/primary.jpg"])
        # attrs 为 None 时尺寸/克重不报错，留 0
        self.assertEqual(d["weight_g"], 0)
        self.assertEqual(d["length_mm"], 0)

    def test_units_normalized_internal_cm_g(self) -> None:
        """单位归一：内部尺寸 mm、重量 g。kg→g；Ozon cm→mm、mm→mm。"""
        from webui.ozon_client_adapter import ozon_to_draft  # noqa: PLC0415
        info = _fake_info()
        attrs = _fake_attrs(weight=2, depth=30, width=20, height=10)
        attrs["weight_unit"] = "kg"        # 2kg → 2000g
        attrs["dimension_unit"] = "cm"     # 30/20/10 cm → 内部 300/200/100 mm
        d = ozon_to_draft(info, attrs)
        self.assertEqual(d["weight_g"], 2000)
        self.assertEqual(d["length_mm"], 300)
        self.assertEqual(d["width_mm"], 200)
        self.assertEqual(d["height_mm"], 100)


class FindByOfferIdTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        import webui.store as store_mod  # noqa: PLC0415
        from webui.drafts import create_draft_from_url  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.DEFAULT_DB = Path(tmp) / "x.db"
            store = store_mod.Store()
            try:
                d = create_draft_from_url("https://detail.1688.com/offer/123456789012.html")
                d["offer_id"] = "OF-9"
                store.insert_draft(d)
                found = store.find_by_offer_id("OF-9")
                self.assertIsNotNone(found)
                self.assertEqual(found["offer_id"], "OF-9")
                self.assertIsNone(store.find_by_offer_id("missing"))
            finally:
                store.close()

    def test_duplicate_offer_id_returns_newest(self) -> None:
        """两条相同 offer_id 时，find_by_offer_id 必须返回 id 最大（最新插入）的那条。"""
        import webui.store as store_mod  # noqa: PLC0415
        from webui.drafts import create_draft_from_url  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.DEFAULT_DB = Path(tmp) / "dup.db"
            store = store_mod.Store()
            try:
                # 第一条：source_url 唯一，offer_id = "DUP"
                d1 = create_draft_from_url("https://detail.1688.com/offer/111.html")
                d1["offer_id"] = "DUP"
                d1["ozon_title"] = "First"
                inserted1 = store.insert_draft(d1)

                # 第二条：不同 source_url，但相同 offer_id
                d2 = create_draft_from_url("https://detail.1688.com/offer/222.html")
                d2["offer_id"] = "DUP"
                d2["ozon_title"] = "Second"
                inserted2 = store.insert_draft(d2)

                # 确认第二条 id 更大
                self.assertGreater(inserted2["id"], inserted1["id"])

                # find_by_offer_id 必须返回 id 最大的那条（最新）
                found = store.find_by_offer_id("DUP")
                self.assertIsNotNone(found)
                self.assertEqual(found["id"], inserted2["id"])
                self.assertEqual(found["ozon_title"], "Second")
            finally:
                store.close()


class PullOzonProductsTest(unittest.TestCase):
    def _svc(self, tmp):
        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "pull.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        return svc

    def test_pull_inserts_and_dedups(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            svc = self._svc(tmp)
            app = svc.App()
            # 配上假凭据，避免 build_client 报缺 key（虽然下面把网络函数全替了）
            app.store.save_settings({"ozon_client_id": "C-1", "ozon_api_key": "K-1"})

            listing = [{"product_id": 111, "offer_id": "A"},
                       {"product_id": 222, "offer_id": "B"}]
            info = {"A": _fake_info("A", 111), "B": _fake_info("B", 222, name="Второй")}
            attrs = {"A": _fake_attrs("A"), "B": _fake_attrs("B")}

            # monkeypatch 源模块属性（pull 内 local import 在调用时解析，能拿到补丁）
            orig = (adapter.list_ozon_products, adapter.get_ozon_info, adapter.get_ozon_attributes)
            adapter.list_ozon_products = lambda settings, visibility="ALL": listing
            adapter.get_ozon_info = lambda settings, offer_ids: {k: info[k] for k in offer_ids if k in info}
            adapter.get_ozon_attributes = lambda settings, offer_ids: {k: attrs[k] for k in offer_ids if k in attrs}
            try:
                r1 = app.pull_ozon_products("ALL")
                self.assertEqual(r1["pulled"], 2)
                drafts = app.store.list_drafts()
                self.assertEqual(len(drafts), 2)
                self.assertTrue(all(d["source"] == "ozon" for d in drafts))
                pids = sorted(d["ozon_product_id"] for d in drafts)
                self.assertEqual(pids, [111, 222])

                # 再拉一次相同 offer_id → 走 update，不新增
                r2 = app.pull_ozon_products("ALL")
                self.assertEqual(r2["pulled"], 2)
                self.assertEqual(len(app.store.list_drafts()), 2)
            finally:
                (adapter.list_ozon_products, adapter.get_ozon_info,
                 adapter.get_ozon_attributes) = orig
                app.store.close()


    def test_pull_fills_description_from_descriptions_endpoint(self) -> None:
        """首拉时 get_ozon_descriptions 返回的描述应写入草稿 description 字段。"""
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            svc = self._svc(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C-1", "ozon_api_key": "K-1"})

            listing = [{"product_id": 111, "offer_id": "A"}]
            info = {"A": _fake_info("A", 111)}
            attrs = {"A": _fake_attrs("A")}
            descs = {"A": "Описание товара на русском"}

            orig = (adapter.list_ozon_products, adapter.get_ozon_info,
                    adapter.get_ozon_attributes, adapter.get_ozon_descriptions)
            adapter.list_ozon_products = lambda settings, visibility="ALL": listing
            adapter.get_ozon_info = lambda settings, offer_ids: {k: info[k] for k in offer_ids if k in info}
            adapter.get_ozon_attributes = lambda settings, offer_ids: {k: attrs[k] for k in offer_ids if k in attrs}
            adapter.get_ozon_descriptions = lambda settings, offer_ids: {k: descs.get(k, "") for k in offer_ids}
            try:
                app.pull_ozon_products("ALL")
                d = app.store.find_by_offer_id("A")
                self.assertIsNotNone(d)
                self.assertEqual(d["description"], "Описание товара на русском")
            finally:
                (adapter.list_ozon_products, adapter.get_ozon_info,
                 adapter.get_ozon_attributes, adapter.get_ozon_descriptions) = orig
                app.store.close()

    def test_repull_description_does_not_clobber_user_edited(self) -> None:
        """再拉时，若用户已编辑描述，Ozon 返回的描述不得覆盖用户的描述（merge 只填空）。"""
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            svc = self._svc(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C-1", "ozon_api_key": "K-1"})

            listing = [{"product_id": 111, "offer_id": "A"}]
            info = {"A": _fake_info("A", 111)}
            attrs = {"A": _fake_attrs("A")}
            descs = {"A": "Ozon原始描述"}

            orig = (adapter.list_ozon_products, adapter.get_ozon_info,
                    adapter.get_ozon_attributes, adapter.get_ozon_descriptions)
            adapter.list_ozon_products = lambda settings, visibility="ALL": listing
            adapter.get_ozon_info = lambda settings, offer_ids: {k: info[k] for k in offer_ids if k in info}
            adapter.get_ozon_attributes = lambda settings, offer_ids: {k: attrs[k] for k in offer_ids if k in attrs}
            adapter.get_ozon_descriptions = lambda settings, offer_ids: {k: descs.get(k, "") for k in offer_ids}
            try:
                # 首拉
                app.pull_ozon_products("ALL")
                d = app.store.find_by_offer_id("A")
                # 用户手编描述
                app.store.update_draft(d["id"], {"description": "手写的俄语描述（用户版）"})

                # Ozon 返回不同描述，再拉
                descs["A"] = "Ozon更新后的描述"
                app.pull_ozon_products("ALL")

                d2 = app.store.find_by_offer_id("A")
                # 用户手编的描述不被覆盖
                self.assertEqual(d2["description"], "手写的俄语描述（用户版）")
            finally:
                (adapter.list_ozon_products, adapter.get_ozon_info,
                 adapter.get_ozon_attributes, adapter.get_ozon_descriptions) = orig
                app.store.close()

    def test_repull_does_not_clobber_user_edits(self) -> None:
        """P1：再拉已存在草稿不能覆盖用户手编的 description/price/supplier，
        但要刷新 Ozon 权威身份字段 ozon_product_id。"""
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            svc = self._svc(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C-1", "ozon_api_key": "K-1"})

            listing = [{"product_id": 111, "offer_id": "A"}]
            info1 = {"A": _fake_info("A", 111, price="799")}
            attrs = {"A": _fake_attrs("A")}

            orig = (adapter.list_ozon_products, adapter.get_ozon_info, adapter.get_ozon_attributes)
            adapter.list_ozon_products = lambda settings, visibility="ALL": listing
            adapter.get_ozon_info = lambda settings, offer_ids: {k: info1[k] for k in offer_ids if k in info1}
            adapter.get_ozon_attributes = lambda settings, offer_ids: {k: attrs[k] for k in offer_ids if k in attrs}
            try:
                # 首拉建草稿
                app.pull_ozon_products("ALL")
                d = app.store.find_by_offer_id("A")
                # 用户手编：填描述/改价/填供应商
                app.store.update_draft(d["id"], {
                    "description": "手写的俄语描述",
                    "price": "1234",
                    "supplier": "我的供应商",
                    "purchase_url": "https://1688.com/x",
                    "cost_cny": 88,
                })
                # 再拉：Ozon 返回不同价 + 空描述 + 不同 product_id
                info1["A"] = _fake_info("A", 999, price="555")
                r = app.pull_ozon_products("ALL")
                self.assertEqual(r["pulled"], 1)
                self.assertEqual(len(app.store.list_drafts()), 1)

                d2 = app.store.find_by_offer_id("A")
                # 用户编辑不被覆盖
                self.assertEqual(d2["description"], "手写的俄语描述")
                self.assertEqual(d2["price"], "1234")
                self.assertEqual(d2["supplier"], "我的供应商")
                self.assertEqual(d2["purchase_url"], "https://1688.com/x")
                self.assertEqual(d2["cost_cny"], 88)
                # Ozon 权威身份字段刷新
                self.assertEqual(d2["ozon_product_id"], 999)
                self.assertEqual(d2["offer_id"], "A")
                # 再拉后状态保持 published（不降级为 ready）
                self.assertEqual(d2["status"], "published")
                # 再拉时视频从 complex_attributes 填入（首拉已有视频，此处验证非空）
                self.assertTrue(d2.get("video_url"), "再拉后 video_url 应被填入")
            finally:
                (adapter.list_ozon_products, adapter.get_ozon_info,
                 adapter.get_ozon_attributes) = orig
                app.store.close()

    def test_repull_keeps_published_status(self) -> None:
        """再拉已上架商品后，status 必须保持 published，不能被降级为 ready。

        首拉后 insert_draft 会因 validate_draft（description/尺寸等必填）将草稿标为 invalid；
        用 update_draft 手动将 status 设为 published 模拟已发布状态，然后再拉验证不被降级。
        """
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            svc = self._svc(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C-1", "ozon_api_key": "K-1"})

            listing = [{"product_id": 111, "offer_id": "A"}]
            info = {"A": _fake_info("A", 111)}
            attrs = {"A": _fake_attrs("A")}

            orig = (adapter.list_ozon_products, adapter.get_ozon_info, adapter.get_ozon_attributes)
            adapter.list_ozon_products = lambda settings, visibility="ALL": listing
            adapter.get_ozon_info = lambda settings, offer_ids: {k: info[k] for k in offer_ids if k in info}
            adapter.get_ozon_attributes = lambda settings, offer_ids: {k: attrs[k] for k in offer_ids if k in attrs}
            try:
                # 首拉建草稿（insert_draft 因 validate_draft 可能存为 invalid，这是预期行为）
                app.pull_ozon_products("ALL")
                d = app.store.find_by_offer_id("A")
                self.assertIsNotNone(d)
                # 手动将 status 设为 published，模拟该商品已发布到 Ozon 的状态
                app.store.update_draft(d["id"], {"status": "published"})
                d_after_set = app.store.find_by_offer_id("A")
                self.assertEqual(d_after_set["status"], "published")

                # 再拉：_merge_pulled_into_existing 必须显式传 status="published"，
                # 否则 update_draft 会将其重算为 "ready"/"invalid"
                app.pull_ozon_products("ALL")
                d2 = app.store.find_by_offer_id("A")
                # 再拉后 status 仍为 published，不降级
                self.assertEqual(d2["status"], "published")
            finally:
                (adapter.list_ozon_products, adapter.get_ozon_info,
                 adapter.get_ozon_attributes) = orig
                app.store.close()

    def test_repull_fills_video_when_existing_empty(self) -> None:
        """再拉时，若现有草稿 video_url 为空且拉来的有视频，则填入 video_url。"""
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            svc = self._svc(tmp)
            app = svc.App()
            app.store.save_settings({"ozon_client_id": "C-1", "ozon_api_key": "K-1"})

            listing = [{"product_id": 111, "offer_id": "A"}]
            info = {"A": _fake_info("A", 111)}
            # 首拉：attrs 不含视频
            attrs_no_video = {"A": _fake_attrs("A", video="")}
            # 再拉：attrs 含视频
            attrs_with_video = {"A": _fake_attrs("A", video="https://v-1.ozone.ru/clip.mp4")}

            current_attrs = attrs_no_video

            orig = (adapter.list_ozon_products, adapter.get_ozon_info, adapter.get_ozon_attributes)
            adapter.list_ozon_products = lambda settings, visibility="ALL": listing
            adapter.get_ozon_info = lambda settings, offer_ids: {k: info[k] for k in offer_ids if k in info}
            adapter.get_ozon_attributes = lambda settings, offer_ids: {k: current_attrs[k] for k in offer_ids if k in current_attrs}
            try:
                # 首拉：无视频
                app.pull_ozon_products("ALL")
                d = app.store.find_by_offer_id("A")
                self.assertEqual(d.get("video_url", ""), "")

                # 再拉：attrs 里有视频了
                current_attrs.update(attrs_with_video)
                app.pull_ozon_products("ALL")
                d2 = app.store.find_by_offer_id("A")
                self.assertEqual(d2.get("video_url"), "https://v-1.ozone.ru/clip.mp4")
            finally:
                (adapter.list_ozon_products, adapter.get_ozon_info,
                 adapter.get_ozon_attributes) = orig
                app.store.close()


class GetOzonAttributesPaginationTest(unittest.TestCase):
    """get_ozon_attributes 必须跟踪 last_id 游标直到耗尽。"""

    def test_pagination_merges_all_pages(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        # 构造假 result 列表：每条 1000 个模拟 full-page，再 1 条短 page
        page1_items = [{"offer_id": f"P1-{i}"} for i in range(1000)]
        page2_items = [{"offer_id": "P2-0"}, {"offer_id": "P2-1"}]

        call_log: list[dict] = []

        class StubClient:
            def get_products_attributes(self, *, offer_ids=None, product_ids=None,
                                        last_id="", limit=1000):
                call_log.append({"last_id": last_id, "limit": limit})
                if last_id == "":
                    return {"result": page1_items, "last_id": "L1"}
                elif last_id == "L1":
                    return {"result": page2_items, "last_id": ""}
                else:
                    return {"result": [], "last_id": ""}

        original_build = adapter.build_client
        adapter.build_client = lambda settings: StubClient()
        try:
            result = adapter.get_ozon_attributes(
                {"ozon_client_id": "C", "ozon_api_key": "K"},
                ["dummy"],
            )
        finally:
            adapter.build_client = original_build

        # 两页合并后应有 1002 条
        self.assertEqual(len(result), 1002)
        self.assertIn("P1-0", result)
        self.assertIn("P1-999", result)
        self.assertIn("P2-0", result)
        self.assertIn("P2-1", result)
        # 第一次调用 last_id 为空，第二次为 "L1"
        self.assertEqual(len(call_log), 2)
        self.assertEqual(call_log[0]["last_id"], "")
        self.assertEqual(call_log[1]["last_id"], "L1")


class GetOzonInfoBySkusTest(unittest.TestCase):
    def test_returns_items_keyed_by_string_sku(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        item = {"sku": 4998185789, "offer_id": "A"}

        class StubClient:
            def get_products_info(self, *, skus=None):
                return {"items": [item]}

        original_build = adapter.build_client
        adapter.build_client = lambda settings: StubClient()
        try:
            result = adapter.get_ozon_info_by_skus({}, [4998185789])
        finally:
            adapter.build_client = original_build

        self.assertEqual(result, {"4998185789": item})

    def test_batches_requests_at_one_thousand_skus(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        calls: list[list[int]] = []

        class StubClient:
            def get_products_info(self, *, skus=None):
                chunk = list(skus or [])
                calls.append(chunk)
                return {"items": [{"sku": sku} for sku in chunk]}

        original_build = adapter.build_client
        adapter.build_client = lambda settings: StubClient()
        try:
            result = adapter.get_ozon_info_by_skus({}, list(range(1001)))
        finally:
            adapter.build_client = original_build

        self.assertEqual([len(chunk) for chunk in calls], [1000, 1])
        self.assertEqual(len(result), 1001)
        self.assertEqual(result["1000"], {"sku": 1000})


class FetchWarehousesPaginationTest(unittest.TestCase):
    """fetch_warehouses 必须跟踪 cursor/has_next 直到耗尽，合并所有页仓库。"""

    def test_pagination_merges_all_pages(self) -> None:
        import webui.ozon_client_adapter as adapter  # noqa: PLC0415

        page1 = [{"warehouse_id": 1, "name": "W1"}, {"warehouse_id": 2, "name": "W2"}]
        page2 = [{"warehouse_id": 3, "name": "W3"}]

        call_log: list[dict] = []

        class StubClient:
            def list_warehouses(self, *, cursor: str = "", limit: int = 100):
                call_log.append({"cursor": cursor})
                if cursor == "":
                    return {"warehouses": page1, "cursor": "C1", "has_next": True}
                elif cursor == "C1":
                    return {"warehouses": page2, "cursor": "", "has_next": False}
                else:
                    return {"warehouses": [], "cursor": "", "has_next": False}

        original_build = adapter.build_client
        adapter.build_client = lambda settings: StubClient()
        try:
            result = adapter.fetch_warehouses(
                {"ozon_client_id": "C", "ozon_api_key": "K"}
            )
        finally:
            adapter.build_client = original_build

        # 两页合并后应有 3 个仓库
        self.assertEqual(len(result), 3)
        ids = [w["warehouse_id"] for w in result]
        self.assertIn(1, ids)
        self.assertIn(2, ids)
        self.assertIn(3, ids)
        # 第一次 cursor 为空，第二次为 "C1"
        self.assertEqual(len(call_log), 2)
        self.assertEqual(call_log[0]["cursor"], "")
        self.assertEqual(call_log[1]["cursor"], "C1")


if __name__ == "__main__":
    unittest.main()
