import unittest
from backend.settings_migrate import normalize_stores, mirror_of


class NormalizeStoresTest(unittest.TestCase):
    def test_synthesizes_main_store_from_legacy_fields(self):
        s = {"ozon_client_id": "111", "ozon_api_key": "K1", "ozon_stores": []}
        stores = normalize_stores(s)
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0]["client_id"], "111")
        self.assertEqual(stores[0]["api_key"], "K1")
        self.assertTrue(stores[0]["is_default"])
        self.assertEqual(stores[0]["name"], "主店")

    def test_keeps_existing_stores_and_adds_legacy_main_as_default(self):
        s = {"ozon_client_id": "111", "ozon_api_key": "K1",
             "ozon_stores": [{"name": "店2", "client_id": "222", "api_key": "K2"}]}
        stores = normalize_stores(s)
        ids = [x["client_id"] for x in stores]
        self.assertIn("111", ids)
        self.assertIn("222", ids)
        by_id = {x["client_id"]: x for x in stores}
        self.assertTrue(by_id["111"]["is_default"])
        self.assertFalse(by_id["222"]["is_default"])

    def test_does_not_duplicate_when_main_already_in_list(self):
        s = {"ozon_client_id": "222", "ozon_api_key": "K2",
             "ozon_stores": [{"name": "店2", "client_id": "222", "api_key": "K2", "is_default": True}]}
        stores = normalize_stores(s)
        self.assertEqual([x["client_id"] for x in stores], ["222"])

    def test_exactly_one_default_when_list_has_none(self):
        s = {"ozon_stores": [{"name": "a", "client_id": "1", "api_key": "x"},
                             {"name": "b", "client_id": "2", "api_key": "y"}]}
        stores = normalize_stores(s)
        self.assertEqual(sum(1 for x in stores if x["is_default"]), 1)
        self.assertTrue(stores[0]["is_default"])

    def test_exactly_one_default_when_list_has_many(self):
        s = {"ozon_stores": [{"name": "a", "client_id": "1", "api_key": "x", "is_default": True},
                             {"name": "b", "client_id": "2", "api_key": "y", "is_default": True}]}
        stores = normalize_stores(s)
        self.assertEqual(sum(1 for x in stores if x["is_default"]), 1)
        self.assertTrue(stores[0]["is_default"])

    def test_empty_when_nothing_configured(self):
        self.assertEqual(normalize_stores({}), [])

    def test_mirror_of_returns_default_creds(self):
        stores = [{"name": "a", "client_id": "1", "api_key": "x", "is_default": False},
                  {"name": "b", "client_id": "2", "api_key": "y", "is_default": True}]
        self.assertEqual(mirror_of(stores), ("2", "y"))

    def test_mirror_of_empty(self):
        self.assertEqual(mirror_of([]), ("", ""))


from backend.settings_migrate import migrate_ai, ai_config


class MigrateAiTest(unittest.TestCase):
    def test_new_keys_take_precedence(self):
        s = {"ai_text": {"engine": "agnes", "api_base": "b", "api_key": "k", "model": "m"}}
        out = migrate_ai(s)
        self.assertEqual(out["ai_text"]["engine"], "agnes")
        self.assertEqual(out["ai_text"]["model"], "m")

    def test_migrates_legacy_text_from_translate_and_provider(self):
        s = {"ai_chat_provider": "remote", "translate_api_base": "B",
             "translate_api_key": "K", "translate_model": "deepseek-chat",
             "translate_engine": "glossary"}
        out = migrate_ai(s)
        self.assertEqual(out["ai_text"], {"engine": "openai", "api_base": "B",
                                          "api_key": "K", "model": "deepseek-chat", "multimodal": False})
        self.assertEqual(out["translate_mode"], "glossary")

    def test_legacy_provider_agnes_maps_engine_agnes(self):
        s = {"ai_chat_provider": "agnes", "translate_engine": "remote"}
        out = migrate_ai(s)
        self.assertEqual(out["ai_text"]["engine"], "agnes")
        self.assertEqual(out["translate_mode"], "ai")

    def test_migrates_legacy_image_and_video_from_agnes(self):
        s = {"agnes_api_base": "AB", "agnes_api_key": "AK",
             "agnes_image_model": "img-1", "agnes_video_model": "vid-1"}
        out = migrate_ai(s)
        self.assertEqual(out["ai_image"], {"engine": "agnes", "api_base": "AB",
                                           "api_key": "AK", "model": "img-1"})
        self.assertEqual(out["ai_video"], {"engine": "agnes", "api_base": "AB",
                                           "api_key": "AK", "model": "vid-1"})

    def test_ai_config_returns_resolver_shape(self):
        s = {"ai_text": {"engine": "openai", "api_base": "B", "api_key": "K", "model": "M"}}
        self.assertEqual(ai_config(s, "text"),
                         {"engine": "openai", "base": "B", "key": "K", "model": "M"})

    def test_ai_text_multimodal_from_new_field(self):
        s = {"ai_text": {"engine": "agnes", "api_base": "b", "api_key": "k", "model": "m", "multimodal": True}}
        self.assertTrue(migrate_ai(s)["ai_text"]["multimodal"])

    def test_ai_text_multimodal_migrates_from_ai_card_vision(self):
        s = {"ai_card_vision": True, "translate_api_base": "B", "translate_api_key": "K"}
        self.assertTrue(migrate_ai(s)["ai_text"]["multimodal"])

    def test_ai_text_multimodal_defaults_false(self):
        self.assertFalse(migrate_ai({})["ai_text"]["multimodal"])


if __name__ == "__main__":
    unittest.main()
