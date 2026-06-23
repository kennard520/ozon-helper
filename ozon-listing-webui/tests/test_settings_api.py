import importlib, tempfile, unittest
from pathlib import Path


class SettingsApiTest(unittest.TestCase):
    def _client(self, tmp):
        from fastapi.testclient import TestClient
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "s.db"
        import backend.app_service as svc
        importlib.reload(svc)
        import backend.main as main_mod
        importlib.reload(main_mod)
        self._main = main_mod
        return TestClient(main_mod.app)

    def test_state_exposes_unified_stores_with_default_and_masked_ai(self):
        # Since saving ozon_stores now replaces the canonical list (and mirrors the default
        # store into ozon_client_id), supply both stores in a single ozon_stores call.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={"ozon_stores": [
                    {"name": "主店", "client_id": "111", "api_key": "K1", "is_default": True},
                    {"name": "店2", "client_id": "222", "api_key": "K2", "is_default": False}]})
                st = client.get("/api/state").json()["settings"]
                stores = st["ozon_stores"]
                ids = [x["client_id"] for x in stores]
                self.assertIn("111", ids)
                self.assertIn("222", ids)
                self.assertEqual(sum(1 for x in stores if x.get("is_default")), 1)
                self.assertTrue(all("api_key" not in x for x in stores))
                self.assertTrue(all("api_key_saved" in x for x in stores))
                for kind in ("ai_text", "ai_image", "ai_video"):
                    self.assertIn(kind, st)
                    self.assertIn("engine", st[kind])
                    self.assertIn("api_key_saved", st[kind])
                    self.assertNotIn("api_key", st[kind])
            finally:
                self._main.APP.store.close()

    def test_saving_stores_mirrors_default_to_legacy_fields(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={"ozon_stores": [
                    {"name": "A", "client_id": "1", "api_key": "ka", "is_default": False},
                    {"name": "B", "client_id": "2", "api_key": "kb", "is_default": True}]})
                st = client.get("/api/state").json()["settings"]
                self.assertEqual(st["ozon_client_id"], "2")
            finally:
                self._main.APP.store.close()

    def test_main_save_without_stores_keeps_them(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={"ozon_stores": [
                    {"name": "A", "client_id": "1", "api_key": "ka", "is_default": True}]})
                client.post("/api/settings", json={"contract_currency": "CNY"})
                st = client.get("/api/state").json()["settings"]
                self.assertEqual([x["client_id"] for x in st["ozon_stores"]], ["1"])
            finally:
                self._main.APP.store.close()

    def test_saving_ai_text_block_roundtrips(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={"ai_text": {
                    "engine": "openai", "api_base": "https://api.deepseek.com",
                    "api_key": "sk-x", "model": "deepseek-chat"}})
                st = client.get("/api/state").json()["settings"]
                self.assertEqual(st["ai_text"]["engine"], "openai")
                self.assertEqual(st["ai_text"]["model"], "deepseek-chat")
                # 平台/模型重构：旧内联 api_key 自动迁移到 ai_platforms(按域名命名)，槽改为引用平台名
                self.assertEqual(st["ai_text"]["platform"], "DeepSeek")
                self.assertTrue(any(p["name"] == "DeepSeek" and p["key_saved"]
                                    for p in st["ai_platforms"]))
            finally:
                self._main.APP.store.close()

    def test_ai_block_key_preserved_when_not_resent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                # 平台 key 留空=沿用同名平台已存 key（不必每次重发密钥）
                client.post("/api/settings", json={"ai_platforms": [
                    {"name": "P", "base": "B", "key": "AK"}]})
                client.post("/api/settings", json={"ai_platforms": [
                    {"name": "P", "base": "B", "key": ""}]})
                s = self._main.APP.store.get_settings()
                plat = {p["name"]: p for p in (s.get("ai_platforms") or [])}["P"]
                self.assertEqual(plat["key"], "AK")
            finally:
                self._main.APP.store.close()


    def test_ai_text_multimodal_roundtrips(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={"ai_text": {
                    "engine": "agnes", "api_base": "B", "api_key": "k", "model": "m", "multimodal": True}})
                st = client.get("/api/state").json()["settings"]
                self.assertTrue(st["ai_text"]["multimodal"])
                client.post("/api/settings", json={"ai_text": {
                    "engine": "agnes", "api_base": "B", "api_key": "", "model": "m", "multimodal": False}})
                st2 = client.get("/api/state").json()["settings"]
                self.assertFalse(st2["ai_text"]["multimodal"])
            finally:
                self._main.APP.store.close()


    def test_oss_config_roundtrips_masked(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                client.post("/api/settings", json={
                    "oss_endpoint": "oss-cn-hangzhou.aliyuncs.com", "oss_bucket": "b",
                    "oss_access_key_id": "ak", "oss_access_key_secret": "sk",
                    "oss_public_base": "https://cdn.x.com"})
                st = client.get("/api/state").json()["settings"]
                self.assertEqual(st["oss_endpoint"], "oss-cn-hangzhou.aliyuncs.com")
                self.assertEqual(st["oss_bucket"], "b")
                self.assertEqual(st["oss_access_key_id"], "ak")
                self.assertEqual(st["oss_public_base"], "https://cdn.x.com")
                self.assertTrue(st["oss_access_key_secret_saved"])
                self.assertNotIn("oss_access_key_secret", st)
                client.post("/api/settings", json={"oss_endpoint": "oss-cn-beijing.aliyuncs.com"})
                self.assertEqual(self._main.APP.store.get_settings()["oss_access_key_secret"], "sk")
            finally:
                self._main.APP.store.close()


if __name__ == "__main__":
    unittest.main()
