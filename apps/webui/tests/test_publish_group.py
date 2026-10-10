"""Tests for publish_variant_group: store method + App method + route.
All Ozon network calls are mocked — no real network traffic.
"""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_complete_draft(
    offer_id: str,
    color: str,
    size: str,
    variant_group: str,
    source_url: str,
) -> dict:
    """Build a draft that passes to_ozon_import_item validation."""
    from webui.drafts import utc_now_iso
    now = utc_now_iso()
    return {
        "source_url": source_url,
        "source_title": f"Чемодан {color} {size}",
        "ozon_title": f"Чемодан {color} {size}",
        "description": "Практичный чемодан для путешествий.",
        "category_id": "17027904",
        "type_id": "115945552",
        "price": "3999",
        "old_price": "4999",
        "stock": 10,
        "weight_g": 3500,
        "length_mm": 60,
        "width_mm": 40,
        "height_mm": 25,
        "images": ["https://ir.ozone.ru/s3/img.jpg"],
        "attributes": [],
        "offer_id": offer_id,
        "status": "ready",
        "source_platform": "ozon",
        "publish_response": None,
        "validation_errors": [],
        "created_at": now,
        "updated_at": now,
        "source_raw": {
            "variant_group": variant_group,
            "selected_aspects": [
                {"aspect": "Цвет", "aspect_key": "Color", "value": color},
                {"aspect": "Размер чемодана", "aspect_key": "SuitcaseSize", "value": size},
            ],
        },
    }


_FAKE_CATEGORY_ATTRS = [
    {
        "id": 10096,  # COLOR_DICT_ATTR_ID
        "name": "Цвет товара",
        "is_required": True,
        "is_aspect": True,
        "dictionary_id": 1494,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
    {
        "id": 10097,  # COLOR_TEXT_ATTR_ID
        "name": "Цвет",
        "is_required": False,
        "is_aspect": True,
        "dictionary_id": 0,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
    {
        "id": 9381,  # size aspect
        "name": "Размер чемодана",
        "is_required": True,
        "is_aspect": True,
        "dictionary_id": 4250098,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
    {
        "id": 9048,  # model name
        "name": "Название модели",
        "is_required": True,
        "is_aspect": False,
        "dictionary_id": 0,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
]


class _DbBase(unittest.TestCase):
    """每个 test 一个临时 DB，不污染主库。"""

    def setUp(self):
        import webui.store as store_mod
        self.tmp = Path(tempfile.mkdtemp()) / "t.db"
        self._old_db = store_mod.DEFAULT_DB
        store_mod.DEFAULT_DB = self.tmp

    def tearDown(self):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = self._old_db


# ---------------------------------------------------------------------------
# Store-level tests
# ---------------------------------------------------------------------------

class TestListDraftsByVariantGroup(_DbBase):

    def _store(self):
        import webui.store as store_mod
        return store_mod.Store(self.tmp)

    def _insert(self, store, offer_id, variant_group, source_url):
        from webui.drafts import create_draft_from_url
        d = create_draft_from_url(source_url)
        d.update({
            "source_platform": "ozon",
            "ozon_title": "Чемодан",
            "description": "Desc",
            "category_id": "1",
            "type_id": "2",
            "price": "100",
            "stock": 1,
            "offer_id": offer_id,
            "images": ["https://ir.ozone.ru/a.jpg"],
            "source_raw": {"variant_group": variant_group, "selected_aspects": []},
        })
        return store.insert_draft(d)

    def test_returns_matching_drafts(self):
        st = self._store()
        self._insert(st, "SKU-1", "GRP-A", "https://www.ozon.ru/product/a-1/")
        self._insert(st, "SKU-2", "GRP-A", "https://www.ozon.ru/product/a-2/")
        self._insert(st, "SKU-3", "GRP-B", "https://www.ozon.ru/product/b-3/")
        result = st.list_drafts_by_variant_group("GRP-A")
        self.assertEqual(len(result), 2)
        offer_ids = {d["offer_id"] for d in result}
        self.assertEqual(offer_ids, {"SKU-1", "SKU-2"})
        st.close()

    def test_returns_empty_for_unknown_group(self):
        st = self._store()
        self._insert(st, "SKU-1", "GRP-A", "https://www.ozon.ru/product/a-1/")
        result = st.list_drafts_by_variant_group("UNKNOWN")
        self.assertEqual(result, [])
        st.close()

    def test_empty_group_returns_empty(self):
        st = self._store()
        result = st.list_drafts_by_variant_group("")
        self.assertEqual(result, [])
        st.close()

    def test_source_raw_json_string_is_matched(self):
        """source_raw stored as JSON string (from DB) must still be matched correctly."""
        st = self._store()
        self._insert(st, "SKU-X", "GRP-JSON", "https://www.ozon.ru/product/x-1/")
        result = st.list_drafts_by_variant_group("GRP-JSON")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["offer_id"], "SKU-X")
        st.close()


# ---------------------------------------------------------------------------
# App-level tests (monkeypatched Ozon calls)
# ---------------------------------------------------------------------------

class TestPublishVariantGroup(_DbBase):

    def _app(self):
        import webui.app_service as svc
        return svc.App()

    def _insert_complete_drafts(self, app, variant_group: str) -> tuple:
        d1 = _make_complete_draft(
            "SKU-WHITE-M", "Белый", "M", variant_group,
            "https://www.ozon.ru/product/white-m-111/",
        )
        d2 = _make_complete_draft(
            "SKU-BEIGE-L", "Бежевый", "L", variant_group,
            "https://www.ozon.ru/product/beige-l-222/",
        )
        r1 = app.store.insert_draft(d1)
        r2 = app.store.insert_draft(d2)
        # 语义变更:采集图→素材(in_gallery=0),发布前需有图集图;
        # 用 source="generated" add_draft_image 注入图集图,与实际 AI 出图流程一致
        app.store.add_draft_image(r1["id"], "https://ir.ozone.ru/s3/img.jpg",
                                  type="白底主图", source="generated")
        app.store.add_draft_image(r2["id"], "https://ir.ozone.ru/s3/img.jpg",
                                  type="白底主图", source="generated")
        r1 = app.store.get_draft(r1["id"])
        r2 = app.store.get_draft(r2["id"])
        return r1, r2

    def test_publish_two_variants_ok(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        self._insert_complete_drafts(app, "G")

        captured_items: list = []

        def fake_publish_items(settings, items):
            captured_items.extend(items)
            return {"result": {"task_id": 42}}

        def fake_search_attr_values(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 555, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search_attr_values
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "imported", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "imported", "errors": []},
            ]}
        }

        result = app.publish_variant_group("G")

        self.assertTrue(result["published"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["variant_group"], "G")
        # model_name defaults to variant_group key when not provided
        self.assertEqual(result["model_name"], "G")
        self.assertEqual(len(captured_items), 2)
        # Each item must have attr 9048 (model name)
        for item in captured_items:
            attr_ids = [a["id"] for a in item["attributes"]]
            self.assertIn(9048, attr_ids)
        # Each item must have color dict attr 10096 with dict value 555
        for item in captured_items:
            color_attrs = [a for a in item["attributes"] if a["id"] == 10096]
            self.assertTrue(len(color_attrs) > 0)
            self.assertEqual(color_attrs[0]["values"][0]["dictionary_value_id"], 555)

    def test_group_publish_records_each_variant_status_from_poll(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, r2 = self._insert_complete_drafts(app, "G-PARTIAL")

        def fake_publish_items(settings, items):
            return {"result": {"task_id": 7001}}

        def fake_search_attr_values(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 555, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search_attr_values
        publish_mod.time.sleep = lambda seconds: None
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "imported", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "imported", "errors": [
                    {"level": "error", "attribute_id": 10096, "description": "bad color"},
                ]},
            ]}
        }

        result = app.publish_variant_group("G-PARTIAL")

        self.assertFalse(result["published"])
        self.assertEqual(result["published_count"], 1)
        self.assertEqual(result["failed"], 1)
        by_id = {row["id"]: row for row in result["results"]}
        self.assertTrue(by_id[r1["id"]]["published"])
        self.assertFalse(by_id[r2["id"]]["published"])
        self.assertEqual(app.store.get_draft(r1["id"])["status"], "published")
        failed = app.store.get_draft(r2["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("bad color", " ".join(failed["validation_errors"]))

    def test_group_publish_treats_skipped_zero_product_as_failed(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, _ = self._insert_complete_drafts(app, "G-SKIP")

        def fake_publish_items(settings, items):
            return {"result": {"task_id": 7002}}

        def fake_search_attr_values(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 555, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search_attr_values
        publish_mod.time.sleep = lambda seconds: None
        publish_mod._lookup_product_by_offer_id = lambda settings, offer_id: None
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "product_id": 0, "status": "skipped", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "product_id": 123, "status": "imported", "errors": []},
            ]}
        }

        result = app.publish_variant_group("G-SKIP")

        self.assertFalse(result["published"])
        self.assertEqual(result["published_count"], 1)
        self.assertEqual(result["failed"], 1)
        failed = app.store.get_draft(r1["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any("Ozon" in e and "跳过" in e for e in failed["validation_errors"]))

    def test_group_publish_confirms_skipped_zero_product_by_offer_lookup(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, _ = self._insert_complete_drafts(app, "G-SKIP-LOOKUP")

        def fake_publish_items(settings, items):
            return {"result": {"task_id": 7003}}

        def fake_search_attr_values(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 555, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search_attr_values
        publish_mod.time.sleep = lambda seconds: None
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "product_id": 0, "status": "skipped", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "product_id": 123, "status": "imported", "errors": []},
            ]}
        }
        publish_mod._lookup_product_by_offer_id = lambda settings, offer_id: {
            "offer_id": offer_id,
            "product_id": 456,
            "source": "product_info",
            "raw": {"id": 456, "offer_id": offer_id},
        }

        result = app.publish_variant_group("G-SKIP-LOOKUP")

        self.assertTrue(result["published"])
        self.assertEqual(result["published_count"], 2)
        self.assertEqual(result["failed"], 0)
        published = app.store.get_draft(r1["id"])
        self.assertEqual(published["status"], "published")
        item = (published["publish_response"] or {}).get("item") or {}
        self.assertEqual(item.get("product_id"), 456)

    def test_group_publish_recovers_poll_timeout_by_offer_lookup(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, _ = self._insert_complete_drafts(app, "G-POLL-TIMEOUT")

        def fake_publish_items(settings, items):
            return {"result": {"task_id": 7004}}

        def fake_search_attr_values(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 555, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search_attr_values
        publish_mod.time.sleep = lambda seconds: None
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "pending", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "pending", "errors": []},
            ]}
        }
        publish_mod._lookup_product_by_offer_id = lambda settings, offer_id: {
            "offer_id": offer_id,
            "product_id": 789,
            "source": "product_info",
            "raw": {"id": 789, "offer_id": offer_id},
        }

        result = app.publish_variant_group("G-POLL-TIMEOUT")

        self.assertTrue(result["published"])
        self.assertEqual(result["published_count"], 2)
        published = app.store.get_draft(r1["id"])
        self.assertEqual(published["status"], "published")
        item = (published["publish_response"] or {}).get("item") or {}
        self.assertEqual(item.get("product_id"), 789)

    def test_custom_model_name(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        self._insert_complete_drafts(app, "G2")

        def fake_publish_items(settings, items):
            return {"result": {"task_id": 1}}

        def fake_search_attr_values(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 1, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search_attr_values
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "imported", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "imported", "errors": []},
            ]}
        }

        result = app.publish_variant_group("G2", model_name="TravelPro X1")
        self.assertEqual(result["model_name"], "TravelPro X1")

    def test_group_publish_rehosts_local_media_before_submit(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, _ = self._insert_complete_drafts(app, "GMEDIA")
        app.store.update_draft(r1["id"], {"images": ["/media/draft-1/local.png"]})
        app.store.save_settings({
            "oss_endpoint": "oss-cn.test.aliyuncs.com",
            "oss_bucket": "bucket",
            "oss_access_key_id": "ak",
            "oss_access_key_secret": "sk",
            "oss_public_base": "https://cdn.example.com",
        })

        captured: list = []
        uploaded: list = []

        class FakeOss:
            def __init__(self, settings, local_reader=None):
                self.settings = settings
                self.local_reader = local_reader

            def configured(self):
                return True

            def upload_remote(self, url):
                uploaded.append(url)
                return "https://cdn.example.com/ozon-media/local.png"

        def fake_publish_items(settings, items):
            captured.extend(items)
            return {"result": {"task_id": 1}}

        def fake_search(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 1, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.OssClient = FakeOss
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "imported", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "imported", "errors": []},
            ]}
        }

        result = app.publish_variant_group("GMEDIA")

        self.assertEqual(result["rehost"]["uploaded"], 1)
        self.assertEqual(uploaded, ["/media/draft-1/local.png"])
        self.assertEqual(captured[0]["images"], ["https://bucket.oss-cn.test.aliyuncs.com/ozon-media/local.png"])
        self.assertEqual(app.store.get_draft(r1["id"])["images"], ["https://cdn.example.com/ozon-media/local.png"])

    def test_group_publish_rewrites_proxy_video_to_direct_oss_before_submit(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, _ = self._insert_complete_drafts(app, "GVIDEO")
        proxy_video = "http://8.152.196.119:8585/oss/ozon-media/video.mp4"
        direct_video = "https://ozon-helper.oss-cn-beijing.aliyuncs.com/ozon-media/video.mp4"
        app.store.update_draft(r1["id"], {"video_url": proxy_video})
        app.store.save_settings({
            "oss_endpoint": "oss-cn-beijing.aliyuncs.com",
            "oss_bucket": "ozon-helper",
            "oss_access_key_id": "ak",
            "oss_access_key_secret": "sk",
            "oss_public_base": "http://8.152.196.119:8585/oss",
        })

        captured: list = []
        uploaded: list = []

        class FakeOss:
            def __init__(self, settings, local_reader=None):
                self.settings = settings
                self.local_reader = local_reader

            def configured(self):
                return True

            def upload_remote(self, url):
                uploaded.append(url)
                return proxy_video

        def fake_publish_items(settings, items):
            captured.extend(items)
            return {"result": {"task_id": 1}}

        def fake_search(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 1, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.OssClient = FakeOss
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "imported", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "imported", "errors": []},
            ]}
        }

        result = app.publish_variant_group("GVIDEO")

        self.assertTrue(result["submitted"])
        self.assertEqual(uploaded, [proxy_video])
        video_attrs = [
            attr
            for ca in captured[0].get("complex_attributes", [])
            for attr in ca.get("attributes", [])
            if attr.get("id") == 21841
        ]
        self.assertEqual(video_attrs[0]["values"][0]["value"], direct_video)

    def test_group_publish_drops_zero_volume_ml_before_submit(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        app = self._app()
        r1, _ = self._insert_complete_drafts(app, "GVOLUME")
        attrs = list(r1.get("attributes") or [])
        attrs.append({"id": 8163, "values": [{"value": "0"}]})
        app.store.update_draft(r1["id"], {"attributes": attrs})

        captured: list = []

        def fake_publish_items(settings, items):
            captured.extend(items)
            return {"result": {"task_id": 1}}

        def fake_search(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 1, "value": value}]}

        category_attrs = [*_FAKE_CATEGORY_ATTRS, {
            "id": 8163,
            "name": "体积/容量，毫升",
            "is_required": False,
            "is_aspect": False,
            "dictionary_id": 0,
        }]
        app._category_attrs = lambda c, t: category_attrs
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search
        publish_mod.get_import_info = lambda settings, task_id: {
            "result": {"items": [
                {"offer_id": "SKU-WHITE-M", "status": "imported", "errors": []},
                {"offer_id": "SKU-BEIGE-L", "status": "imported", "errors": []},
            ]}
        }

        app.publish_variant_group("GVOLUME")

        first_attr_ids = {a["id"] for a in captured[0]["attributes"]}
        self.assertNotIn(8163, first_attr_ids)

    def test_empty_group_raises_value_error(self):
        app = self._app()
        with self.assertRaises(ValueError) as ctx:
            app.publish_variant_group("NONEXISTENT")
        self.assertIn("没有草稿", str(ctx.exception))

    def test_draft_missing_category_raises_value_error(self):
        import webui.app_service as app_service
        from webui.drafts import create_draft_from_url

        app = self._app()
        d = create_draft_from_url("https://www.ozon.ru/product/no-cat-999/")
        d.update({
            "source_platform": "ozon",
            "ozon_title": "Товар",
            "description": "Desc",
            "category_id": "",   # <-- missing
            "type_id": "",
            "price": "100",
            "stock": 1,
            "images": ["https://ir.ozone.ru/a.jpg"],
            "source_raw": {"variant_group": "GNO", "selected_aspects": []},
        })
        app.store.insert_draft(d)

        with self.assertRaises(ValueError) as ctx:
            app.publish_variant_group("GNO")
        self.assertIn("缺类目", str(ctx.exception))

    def test_cny_currency_passthrough(self):
        """With contract_currency=CNY (default), items keep original price without conversion."""
        import webui.app_service as app_service

        app = self._app()
        app.store.save_settings({"contract_currency": "CNY"})
        self._insert_complete_drafts(app, "GCNY")

        captured: list = []

        def fake_publish_items(settings, items):
            captured.extend(items)
            return {"result": {}}

        def fake_search(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 1, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search

        app.publish_variant_group("GCNY")
        for it in captured:
            self.assertEqual(it.get("currency_code"), "CNY")
            # price must be original value (no division)
            self.assertEqual(it["price"], "3999")

    def test_rub_currency_conversion(self):
        """With contract_currency=RUB and rub_cny=0.1, price should be divided by 0.1."""
        import webui.app_service as app_service

        app = self._app()
        app.store.save_settings({"contract_currency": "RUB", "rub_cny": 0.1})
        self._insert_complete_drafts(app, "GRUB")

        captured: list = []

        def fake_publish_items(settings, items):
            captured.extend(items)
            return {"result": {}}

        def fake_search(settings, cat, typ, attr_id, value, limit=5, **kw):
            return {"result": [{"id": 1, "value": value}]}

        app._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
        app_service.publish_items = fake_publish_items
        app_service.search_attribute_values = fake_search

        app.publish_variant_group("GRUB")
        for it in captured:
            self.assertEqual(it.get("currency_code"), "RUB")
            # 3999 / 0.1 = 39990.0
            self.assertAlmostEqual(float(it["price"]), 39990.0)


# ---------------------------------------------------------------------------
# Route-level tests (TestClient, no network)
# ---------------------------------------------------------------------------

class TestPublishGroupRoute(_DbBase):

    def _client(self):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = self.tmp
        import webui.app_service as svc
        importlib.reload(svc)
        import webui.main as main_mod
        importlib.reload(main_mod)
        self._main = main_mod
        from fastapi.testclient import TestClient
        return TestClient(main_mod.app)

    def _insert_drafts(self, client, variant_group):
        """Insert two complete drafts via store directly."""
        app = self._main.APP
        d1 = _make_complete_draft(
            "SKU-A", "Белый", "M", variant_group,
            "https://www.ozon.ru/product/rte-a-1/",
        )
        d2 = _make_complete_draft(
            "SKU-B", "Бежевый", "L", variant_group,
            "https://www.ozon.ru/product/rte-b-2/",
        )
        r1 = app.store.insert_draft(d1)
        r2 = app.store.insert_draft(d2)
        # 语义变更:采集图→素材,发布前需有图集图
        app.store.add_draft_image(r1["id"], "https://ir.ozone.ru/s3/img.jpg",
                                  type="白底主图", source="generated")
        app.store.add_draft_image(r2["id"], "https://ir.ozone.ru/s3/img.jpg",
                                  type="白底主图", source="generated")

    def test_publish_group_route_ok(self):
        import webui.app_service as app_service
        import webui.services._publish as publish_mod

        client = self._client()
        try:
            self._insert_drafts(client, "GRTE")

            self._main.APP._category_attrs = lambda c, t: _FAKE_CATEGORY_ATTRS
            app_service.publish_items = lambda s, items: {"result": {"task_id": 7}}
            app_service.search_attribute_values = lambda s, c, t, a, v, **kw: {"result": [{"id": 99, "value": v}]}
            publish_mod.get_import_info = lambda settings, task_id: {
                "result": {"items": [
                    {"offer_id": "SKU-A", "status": "imported", "errors": []},
                    {"offer_id": "SKU-B", "status": "imported", "errors": []},
                ]}
            }

            resp = client.post("/api/ext/publish-group", json={"variant_group": "GRTE"})
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertTrue(body["published"])
            self.assertEqual(body["count"], 2)
            self.assertEqual(body["variant_group"], "GRTE")
        finally:
            self._main.APP.store.close()

    def test_publish_group_route_unknown_group_400(self):
        client = self._client()
        try:
            resp = client.post("/api/ext/publish-group", json={"variant_group": "NOPE"})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("没有草稿", resp.json()["detail"])
        finally:
            self._main.APP.store.close()

    def test_publish_group_route_missing_category_400(self):
        from webui.drafts import create_draft_from_url

        client = self._client()
        try:
            app = self._main.APP
            d = create_draft_from_url("https://www.ozon.ru/product/nocat-555/")
            d.update({
                "source_platform": "ozon",
                "ozon_title": "Товар",
                "description": "D",
                "category_id": "",
                "type_id": "",
                "price": "10",
                "stock": 1,
                "images": ["https://ir.ozone.ru/a.jpg"],
                "source_raw": {"variant_group": "GNOCAT", "selected_aspects": []},
            })
            app.store.insert_draft(d)

            resp = client.post("/api/ext/publish-group", json={"variant_group": "GNOCAT"})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("缺类目", resp.json()["detail"])
        finally:
            self._main.APP.store.close()

    def test_publish_group_model_missing_required_field_400(self):
        """variant_group is required — missing it → 422."""
        client = self._client()
        try:
            resp = client.post("/api/ext/publish-group", json={})
            self.assertEqual(resp.status_code, 422)
        finally:
            self._main.APP.store.close()


if __name__ == "__main__":
    unittest.main()
