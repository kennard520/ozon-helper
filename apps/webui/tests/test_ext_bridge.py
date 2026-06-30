from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path


class ExtBridgeTest(unittest.TestCase):
    def _client(self, tmp):
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import webui.store as store_mod  # noqa: PLC0415
        store_mod.DEFAULT_DB = Path(tmp) / "ext.db"
        import webui.app_service as svc  # noqa: PLC0415
        importlib.reload(svc)
        import webui.main as main_mod  # noqa: PLC0415
        importlib.reload(main_mod)
        self._main = main_mod
        return TestClient(main_mod.app)

    def test_ping(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                resp = client.get("/api/ext/ping")
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertTrue(body["ok"])
                self.assertIn("name", body)
                self.assertIn("version", body)
            finally:
                self._main.APP.store.close()

    def test_snapshot_store_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                snap = {
                    "product_id": "1234567",
                    "sku": "1234567",
                    "follow_count": 3,
                    "price_min": 3100,
                    "price_max": 4626,
                    "sellers": [{"name": "A", "price": 3100, "origin": "ru"}],
                }
                r1 = client.post("/api/ext/snapshot", json=snap)
                self.assertEqual(r1.status_code, 200)
                r2 = client.get("/api/ext/snapshots", params={"product_id": "1234567"})
                self.assertEqual(r2.status_code, 200)
                body = r2.json()
                self.assertEqual(body["product_id"], "1234567")
                self.assertEqual(len(body["snapshots"]), 1)
                s = body["snapshots"][0]
                self.assertEqual(s["follow_count"], 3)
                self.assertEqual(s["price_min"], 3100)
                self.assertIn("captured_at", s)
            finally:
                self._main.APP.store.close()

    def test_snapshot_dedupes_consecutive_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                snap = {"product_id": "9", "follow_count": 2, "price_min": 100, "price_max": 200, "sellers": []}
                client.post("/api/ext/snapshot", json=snap)
                client.post("/api/ext/snapshot", json=snap)  # identical → should not add a 2nd row
                body = client.get("/api/ext/snapshots", params={"product_id": "9"}).json()
                self.assertEqual(len(body["snapshots"]), 1)
            finally:
                self._main.APP.store.close()

    def test_snapshot_requires_product_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(tmp)
            try:
                resp = client.post("/api/ext/snapshot", json={"follow_count": 1})
                self.assertEqual(resp.status_code, 422)  # pydantic: missing required field
            finally:
                self._main.APP.store.close()

    # 注：/api/ext/collect（服务器端重抓）已停用——采集全走插件 collect-parsed，故相关用例删除。

    def test_collect_parsed_auto_maps_when_category_present(self):
        # 采集若已自动匹配到类目 → 自动跑 auto-map 预填属性；无类目则跳过
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                calls = []
                self._main.APP.auto_map_attributes = lambda did: calls.append(did) or {}
                # 无类目（无 API key 无法自动匹配）→ 不触发
                client.post("/api/ext/collect-parsed", json={
                    "url": "https://www.ozon.ru/product/no-cat-1/", "data": {"title": "T"}})
                self.assertEqual(calls, [])
                # 手动塞类目的草稿再采集刷新 → 触发
                from webui.drafts import create_draft_from_url
                d = self._main.APP.store.insert_draft(create_draft_from_url(
                    "https://www.ozon.ru/product/has-cat-2/", source_platform="ozon",
                    scraped={"ozon_title": "T", "category_id": "17028922", "type_id": "91476"}))
                client.post("/api/ext/collect-parsed", json={
                    "url": "https://www.ozon.ru/product/has-cat-2/", "data": {"title": "T2"}})
                self.assertIn(d["id"], calls)
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_attributes_into_draft(self):
        # 采集的名值对属性 → draft.attributes（collected_chars 据此喂 auto-map/AI），
        # 且不含 id/values（发布时会被 to_ozon_import_item 丢弃，不误发 Ozon）
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                from webui.drafts import collected_chars
                payload = {
                    "url": "https://www.ozon.ru/product/x-4318851933/",
                    "data": {
                        "title": "Наушники",
                        "attributes": [
                            {"name": "Бренд", "value": "Habbarmers"},
                            {"name": "Тип беспроводной связи", "value": "Bluetooth"},
                            {"name": "", "value": "skip"},   # 空名跳过
                        ],
                    },
                }
                r = client.post("/api/ext/collect-parsed", json=payload)
                self.assertEqual(r.status_code, 200)
                d = self._main.APP.store.get_draft(r.json()["created"][0]["id"])
                chars = collected_chars(d)
                names = {c["name"]: c["value"] for c in chars}
                self.assertEqual(names.get("Бренд"), "Habbarmers")
                self.assertEqual(names.get("Тип беспроводной связи"), "Bluetooth")
                self.assertNotIn("", names)   # 空名被过滤
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_wb_platform_and_source_raw(self):
        # WB 全插件采集：data 带 source_platform=wb + source_raw.options，后端如实落库
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                payload = {
                    "url": "https://www.wildberries.ru/catalog/123456789/detail.aspx",
                    "data": {
                        "source_platform": "wb",
                        "title": "Сумка женская",
                        "description": "Отличная",
                        "images": ["https://basket-19.wbbasket.ru/vol1/part1/1/images/big/1.webp"],
                        "weight_g": 500, "length_mm": 300, "width_mm": 200, "height_mm": 100,
                        "source_raw": {"options": [{"name": "Цвет", "value": "чёрный"}], "brand_name": "NoName"},
                    },
                }
                r = client.post("/api/ext/collect-parsed", json=payload)
                self.assertEqual(r.status_code, 200)
                did = r.json()["created"][0]["id"]
                d = self._main.APP.store.get_draft(did)
                self.assertEqual(d["source_platform"], "wb")
                self.assertEqual(d["source_title"], "Сумка женская")
                self.assertEqual(d["ozon_title"], "Сумка женская")
                self.assertEqual(d["weight_g"], 500)
                self.assertEqual(d["source_raw"]["options"][0]["value"], "чёрный")
                self.assertEqual(d["source_raw"]["brand_name"], "NoName")
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_creates_draft_without_scrape(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                payload = {
                    "url": "https://www.ozon.ru/product/renu-360-1117478728/",
                    "data": {
                        "title": "ReNu Advanced раствор для контактных линз 360 мл",
                        "description": "Описание",
                        "price": "528",
                        "old_price": "890",
                        "images": ["https://ir.ozone.ru/s3/x/1.jpg", "https://ir.ozone.ru/s3/x/2.jpg"],
                        "video_url": "",
                        "weight_g": 2800,
                        "length_mm": 240,
                        "width_mm": 350,
                        "height_mm": 540,
                        "variants": [{"sku": "111", "label": "Белый", "link": "https://www.ozon.ru/product/a-111/"}],
                        "variant_group": "G1",
                        "selected_aspects": [{"aspect": "Цвет", "value": "Белый"}]
                    }
                }
                r = client.post("/api/ext/collect-parsed", json=payload)
                self.assertEqual(r.status_code, 200)
                body = r.json()
                self.assertEqual(len(body["created"]), 1)
                did = body["created"][0]["id"]
                # 草稿落库且字段正确：Ozon 竞品标题直接进 ozon_title
                drafts = client.get("/api/drafts").json()["drafts"]
                d = [x for x in drafts if x["id"] == did][0]
                self.assertEqual(d["source_platform"], "ozon")
                self.assertEqual(d["ozon_title"], "ReNu Advanced раствор для контактных линз 360 мл")
                self.assertEqual(d["price"], "528")
                # 语义变更:采集图→素材(in_gallery=0),图集(images)为空;materials 有 2 张
                self.assertEqual(len(d["images"]), 0)
                self.assertEqual(len(d["materials"]), 2)
                self.assertEqual(d["weight_g"], 2800)
                self.assertEqual(d["length_mm"], 240)
                self.assertEqual(d["description"], "Описание")
                # variants + variant_group 落进 source_raw
                sr = d["source_raw"]
                if isinstance(sr, str):
                    import json as _json
                    sr = _json.loads(sr)
                self.assertEqual(sr["variants"][0]["sku"], "111")
                self.assertEqual(sr["variant_group"], "G1")
                self.assertEqual(sr["selected_aspects"][0]["value"], "Белый")
            finally:
                self._main.APP.store.close()

    def _attrs_of(self, draft: dict) -> list:
        raw = draft.get("attributes")
        if isinstance(raw, str):
            import json as _json
            raw = _json.loads(raw)
        return raw if isinstance(raw, list) else []

    def test_collect_parsed_writes_hashtags_into_attr_23171(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                payload = {
                    "url": "https://www.ozon.ru/product/soap-hash-1/",
                    "data": {
                        "title": "Мыло",
                        "price": "100",
                        "images": ["https://ir.ozone.ru/a.jpg"],
                        "hashtags": ["#мылоручнойработы", "#натуральноемыло", "#холодныйспособ"],
                    },
                }
                r = client.post("/api/ext/collect-parsed", json=payload)
                self.assertEqual(r.status_code, 200)
                did = r.json()["created"][0]["id"]
                d = [x for x in client.get("/api/drafts").json()["drafts"] if x["id"] == did][0]
                tag_attr = [a for a in self._attrs_of(d) if int(a.get("id") or 0) == 23171]
                self.assertEqual(len(tag_attr), 1)
                val = tag_attr[0]["values"][0]["value"]
                self.assertEqual(val, "#мылоручнойработы #натуральноемыло #холодныйспособ")
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_no_hashtags_no_attr(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                payload = {"url": "https://www.ozon.ru/product/no-hash-1/",
                           "data": {"title": "T", "price": "100", "images": ["https://ir.ozone.ru/a.jpg"]}}
                r = client.post("/api/ext/collect-parsed", json=payload)
                did = r.json()["created"][0]["id"]
                d = [x for x in client.get("/api/drafts").json()["drafts"] if x["id"] == did][0]
                self.assertEqual([a for a in self._attrs_of(d) if int(a.get("id") or 0) == 23171], [])
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_recollect_fills_missing_hashtags(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                url = "https://www.ozon.ru/product/refill-hash-1/"
                client.post("/api/ext/collect-parsed", json={
                    "url": url, "data": {"title": "T", "price": "100", "images": ["https://ir.ozone.ru/a.jpg"]}})
                # 二次采集带上标签 → 旧草稿补空
                r2 = client.post("/api/ext/collect-parsed", json={
                    "url": url, "data": {"title": "T", "price": "100",
                                         "images": ["https://ir.ozone.ru/a.jpg"], "hashtags": ["#тег"]}})
                did = r2.json()["created"][0]["id"]
                d = [x for x in client.get("/api/drafts").json()["drafts"] if x["id"] == did][0]
                tag_attr = [a for a in self._attrs_of(d) if int(a.get("id") or 0) == 23171]
                self.assertEqual(len(tag_attr), 1)
                self.assertEqual(tag_attr[0]["values"][0]["value"], "#тег")
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_does_not_download_local_video(self):
        # 视频走 OSS（插件已传，video_url 是 OSS 直链）：后端不再下载本地副本（已去掉 _ext_cache_video）
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            import webui.media as media_mod  # noqa: PLC0415
            called = {"n": 0}
            orig = media_mod.download_video
            media_mod.download_video = lambda url, key, **kw: (called.update(n=called["n"] + 1) or "media/x/video.mp4")
            try:
                payload = {"url": "https://www.ozon.ru/product/vid-1/",
                           "data": {"title": "T", "price": "100", "images": ["https://ir.ozone.ru/a.jpg"],
                                    "video_url": "https://cdn.example.com/v.mp4"}}
                r = client.post("/api/ext/collect-parsed", json=payload)
                did = r.json()["created"][0]["id"]
                d = [x for x in client.get("/api/drafts").json()["drafts"] if x["id"] == did][0]
                sr = d["source_raw"]
                if isinstance(sr, str):
                    import json as _json
                    sr = _json.loads(sr)
                self.assertEqual(called["n"], 0)                  # 后端没下载本地视频
                self.assertIsNone((sr or {}).get("video_local"))  # 没有本地副本路径
            finally:
                media_mod.download_video = orig
                self._main.APP.store.close()

    def test_collect_parsed_video_download_failure_does_not_break(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            import webui.media as media_mod  # noqa: PLC0415
            orig = media_mod.download_video
            def _boom(url, key, **kw):
                raise RuntimeError("network down")
            media_mod.download_video = _boom
            try:
                payload = {"url": "https://www.ozon.ru/product/vid-2/",
                           "data": {"title": "T", "price": "100", "images": ["https://ir.ozone.ru/a.jpg"],
                                    "video_url": "https://v-1.ozone.ru/vod/v/x.mp4"}}
                r = client.post("/api/ext/collect-parsed", json=payload)
                self.assertEqual(r.status_code, 200)  # 下载失败不影响建草稿
                self.assertEqual(len(r.json()["created"]), 1)
            finally:
                media_mod.download_video = orig
                self._main.APP.store.close()

    def test_collect_parsed_no_video_no_download(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            import webui.media as media_mod  # noqa: PLC0415
            calls = {"n": 0}
            orig = media_mod.download_video
            media_mod.download_video = lambda *a, **k: (calls.update(n=calls["n"] + 1) or "x")
            try:
                client.post("/api/ext/collect-parsed", json={
                    "url": "https://www.ozon.ru/product/novid-1/",
                    "data": {"title": "T", "price": "100", "images": ["https://ir.ozone.ru/a.jpg"]}})
                self.assertEqual(calls["n"], 0)
            finally:
                media_mod.download_video = orig
                self._main.APP.store.close()

    def test_collect_parsed_dedupes_same_url(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                payload = {"url": "https://www.ozon.ru/product/x-999/", "data": {"title": "T", "price": "100", "images": ["https://ir.ozone.ru/a.jpg"]}}
                r1 = client.post("/api/ext/collect-parsed", json=payload)
                id1 = r1.json()["created"][0]["id"]
                r2 = client.post("/api/ext/collect-parsed", json=payload)
                id2 = r2.json()["created"][0]["id"]
                self.assertEqual(id1, id2)  # 同 url 去重，不重复建
            finally:
                self._main.APP.store.close()

    def test_collect_parsed_requires_url(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            client = self._client(tmp)
            try:
                resp = client.post("/api/ext/collect-parsed", json={"data": {"title": "x"}})
                self.assertEqual(resp.status_code, 422)
            finally:
                self._main.APP.store.close()


if __name__ == "__main__":
    unittest.main()
