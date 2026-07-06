"""Agnes 生图/生视频 service 层 + 路由 + 设置项测试（离线：agnes/_download_bytes 全打桩）。"""
from __future__ import annotations

import gc
import importlib
import tempfile
import time
import unittest
from pathlib import Path


def _make_app(tmp: str):
    import webui.store as store_mod
    store_mod.DEFAULT_DB = Path(tmp) / "ai_media.db"
    import webui.app_service as svc
    importlib.reload(svc)
    return svc, svc.App()


def _new_draft(app, url: str, **scraped):
    """完整草稿骨架走 create_draft_from_url（insert_draft 要求全字段）。"""
    from webui.drafts import create_draft_from_url
    return app.store.insert_draft(create_draft_from_url(url, scraped=scraped or None))


class AiImageServiceTest(unittest.TestCase):
    def test_text2img_appends_local_image(self):
        import webui.agnes as agnes_mod
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db, orig_root = store_mod.DEFAULT_DB, media_mod.MEDIA_ROOT
        orig_gen = agnes_mod.generate_image
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp) / "images"
            svc, app = _make_app(tmp)
            orig_dl = svc._download_bytes
            try:
                # 语义变更:采集图→素材,测试意图是"已有图集图时,AI 生图追加到末尾"
                # 所以先用 generated 加一张图集图
                d = _new_draft(app, "https://x/1")
                app.store.add_draft_image(d["id"], "https://a/1.jpg",
                                          type="白底主图", source="generated")
                d = app.store.get_draft(d["id"])
                seen = {}
                def fake_gen(settings, prompt, *, size="1024x768", source_images=None):
                    seen.update(prompt=prompt, size=size, source_images=source_images)
                    return "https://cdn.agnes/gen.png"
                agnes_mod.generate_image = fake_gen
                svc._download_bytes = lambda url, timeout=120: b"\x89PNGDATA"
                r = app.ai_generate_image(d["id"], mode="text2img", prompt="marketing shot")
                self.assertTrue(r["ok"])
                imgs = r["draft"]["images"]
                self.assertEqual(imgs[0], "https://a/1.jpg")       # 原图集图保留
                self.assertTrue(imgs[1].startswith("/media/draft-%d/" % d["id"]))  # 追加到尾部
                self.assertEqual(seen["prompt"], "marketing shot")
                self.assertIsNone(seen["source_images"])
                # 字节真落盘
                self.assertEqual(media_mod.read_media_bytes(imgs[1]), b"\x89PNGDATA")
            finally:
                agnes_mod.generate_image = orig_gen
                svc._download_bytes = orig_dl
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                media_mod.MEDIA_ROOT = orig_root
                importlib.reload(svc)

    def test_multiple_ai_images_append_without_overwriting(self):
        import webui.agnes as agnes_mod
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db, orig_root = store_mod.DEFAULT_DB, media_mod.MEDIA_ROOT
        orig_gen = agnes_mod.generate_image
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp) / "images"
            svc, app = _make_app(tmp)
            orig_dl = svc._download_bytes
            try:
                d = _new_draft(app, "https://x/multi")
                app.store.add_draft_image(d["id"], "https://a/base.jpg",
                                          type="main", source="generated")
                calls = []

                def fake_gen(settings, prompt, *, size="1024x768", source_images=None):
                    calls.append(list(source_images or []))
                    return f"https://cdn.agnes/gen-{len(calls)}.png"

                agnes_mod.generate_image = fake_gen
                svc._download_bytes = lambda url, timeout=120: url.encode()
                first = app.ai_generate_image(
                    d["id"], mode="img2img", prompt="localize",
                    source_url="https://cdn.source/one.jpg",
                )
                second = app.ai_generate_image(
                    d["id"], mode="img2img", prompt="localize",
                    source_url="https://cdn.source/two.jpg",
                )

                self.assertTrue(first["image"].startswith("/media/draft-%d/" % d["id"]))
                self.assertTrue(second["image"].startswith("/media/draft-%d/" % d["id"]))
                self.assertNotEqual(first["image"], second["image"])
                imgs = second["draft"]["images"]
                self.assertEqual(imgs[0], "https://a/base.jpg")
                self.assertIn(first["image"], imgs)
                self.assertIn(second["image"], imgs)
                self.assertEqual(len([u for u in imgs if u.startswith("/media/")]), 2)
                self.assertEqual(calls, [["https://cdn.source/one.jpg"], ["https://cdn.source/two.jpg"]])
            finally:
                agnes_mod.generate_image = orig_gen
                svc._download_bytes = orig_dl
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                media_mod.MEDIA_ROOT = orig_root
                importlib.reload(svc)

    def test_img2img_as_main_with_local_source_becomes_data_uri(self):
        import webui.agnes as agnes_mod
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db, orig_root = store_mod.DEFAULT_DB, media_mod.MEDIA_ROOT
        orig_gen = agnes_mod.generate_image
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp) / "images"
            svc, app = _make_app(tmp)
            orig_dl = svc._download_bytes
            try:
                # 语义变更:采集图→素材,测试意图是"as_main 插到首位,已有图集图后移"
                # 先用 generated 加一张图集图
                d = _new_draft(app, "https://x/2")
                app.store.add_draft_image(d["id"], "https://a/1.jpg",
                                          type="白底主图", source="generated")
                d = app.store.get_draft(d["id"])
                # 预置一张本地源图
                (media_mod.MEDIA_ROOT / ("draft-%d" % d["id"])).mkdir(parents=True)
                (media_mod.MEDIA_ROOT / ("draft-%d" % d["id"]) / "01.jpg").write_bytes(b"JPG")
                seen = {}
                def fake_gen(settings, prompt, *, size="1024x768", source_images=None):
                    seen.update(source_images=source_images)
                    return "https://cdn.agnes/gen2.png"
                agnes_mod.generate_image = fake_gen
                svc._download_bytes = lambda url, timeout=120: b"PNG2"
                r = app.ai_generate_image(d["id"], mode="img2img", prompt="white bg",
                                          source_url="/media/draft-%d/01.jpg" % d["id"],
                                          as_main=True)
                # 本地源图 → data URI（外网拿不到 localhost /media）
                self.assertTrue(seen["source_images"][0].startswith("data:image/jpeg;base64,"))
                # as_main → 插到首位当主图
                self.assertTrue(r["draft"]["images"][0].startswith("/media/draft-%d/" % d["id"]))
                self.assertEqual(r["draft"]["images"][1], "https://a/1.jpg")
            finally:
                agnes_mod.generate_image = orig_gen
                svc._download_bytes = orig_dl
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                media_mod.MEDIA_ROOT = orig_root
                importlib.reload(svc)

    def test_validation_errors(self):
        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                d = _new_draft(app, "https://x/3")
                with self.assertRaises(ValueError):   # 空提示词
                    app.ai_generate_image(d["id"], prompt="  ")
                with self.assertRaises(ValueError):   # 图生图缺源图
                    app.ai_generate_image(d["id"], mode="img2img", prompt="x")
                with self.assertRaises(KeyError):     # 草稿不存在
                    app.ai_generate_image(99999, prompt="x")
            finally:
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)


class AiVideoStateMachineTest(unittest.TestCase):
    """backend/ai_video.py 状态机：create→poll→done/failed/stopped，全注入无网络。"""

    def setUp(self):
        import webui.ai_video as av
        self.av = av
        self._orig_sleep = av._sleep
        av._sleep = lambda s: None
        av._stop.clear()
        av._set(status="idle", draft_id=0, video_id="", progress=0, url="", last_error="")

    def tearDown(self):
        self.av._sleep = self._orig_sleep
        self.av._stop.clear()

    def _wait_terminal(self, timeout=5.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.av.video_status()
            if st["status"] not in ("running",):
                return st
            time.sleep(0.01)
        return self.av.video_status()

    def test_done_flow_calls_on_done(self):
        seq = [{"status": "in_progress", "progress": 50, "url": "", "error": ""},
               {"status": "completed", "progress": 100,
                "url": "https://storage.googleapis.com/v.mp4", "error": ""}]
        done = {}
        self.av.start_video(
            lambda: {"video_id": "v1"},
            lambda vid: seq.pop(0),
            lambda draft_id, url: done.update(draft_id=draft_id, url=url),
            7)
        st = self._wait_terminal()
        self.assertEqual(st["status"], "done")
        self.assertEqual(st["url"], "https://storage.googleapis.com/v.mp4")
        self.assertEqual(st["video_id"], "v1")
        self.assertEqual(done, {"draft_id": 7, "url": "https://storage.googleapis.com/v.mp4"})

    def test_failed_flow(self):
        self.av.start_video(
            lambda: {"video_id": "v2"},
            lambda vid: {"status": "failed", "progress": 0, "url": "", "error": "boom"},
            lambda draft_id, url: None,
            1)
        st = self._wait_terminal()
        self.assertEqual(st["status"], "error")
        self.assertIn("boom", st["last_error"])

    def test_create_exception_becomes_error(self):
        def bad_create():
            raise RuntimeError("Agnes 接口报错 HTTP 401")
        self.av.start_video(bad_create, lambda vid: {}, lambda d, u: None, 1)
        st = self._wait_terminal()
        self.assertEqual(st["status"], "error")
        self.assertIn("401", st["last_error"])

    def test_double_start_returns_running_state(self):
        import threading
        gate = threading.Event()
        def slow_query(vid):
            gate.wait(2)
            return {"status": "completed", "progress": 100, "url": "https://x/v.mp4", "error": ""}
        self.av.start_video(lambda: {"video_id": "v3"}, slow_query, lambda d, u: None, 3)
        r2 = self.av.start_video(lambda: {"video_id": "OTHER"}, slow_query, lambda d, u: None, 99)
        self.assertEqual(r2["status"], "running")
        self.assertEqual(r2["draft_id"], 3)   # 没被第二个任务顶掉
        gate.set()
        self._wait_terminal()


class AiVideoServiceTest(unittest.TestCase):
    def test_start_ai_video_and_writeback(self):
        import webui.agnes as agnes_mod
        import webui.ai_video as av
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        orig_create, orig_query = agnes_mod.create_video_task, agnes_mod.query_video
        orig_dlv = media_mod.download_video
        orig_sleep = av._sleep
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                av._sleep = lambda s: None
                av._stop.clear()
                av._set(status="idle", draft_id=0, video_id="", progress=0, url="", last_error="")
                app.store.save_settings({"agnes_api_key": "K"})
                # 语义变更:采集图→素材,视频生成需要图集图;先 add_draft_image 加图集图
                d = _new_draft(app, "https://x/4", ozon_title="Держатель")
                app.store.add_draft_image(d["id"], "https://a/main.jpg",
                                          type="白底主图", source="generated")
                d = app.store.get_draft(d["id"])
                seen = {}
                def fake_create(settings, prompt, *, image=None, **kw):
                    seen.update(prompt=prompt, image=image)
                    return {"video_id": "v9", "task_id": "t9", "status": "queued"}
                agnes_mod.create_video_task = fake_create
                agnes_mod.query_video = lambda settings, vid: {
                    "status": "completed", "progress": 100,
                    "url": "https://storage.googleapis.com/out.mp4", "error": ""}
                media_mod.download_video = lambda url, key, **kw: f"/media/{key}/video.mp4"
                r = app.start_ai_video(d["id"])
                self.assertEqual(r["status"], "running")
                t0 = time.time()
                while time.time() - t0 < 5 and av.video_status()["status"] == "running":
                    time.sleep(0.01)
                st = av.video_status()
                self.assertEqual(st["status"], "done")
                # 默认用主图 + 默认提示词（带商品标题）
                self.assertEqual(seen["image"], "https://a/main.jpg")
                self.assertIn("Держатель", seen["prompt"])
                # 回写：video_url + 本地预览副本（独立 key，避免覆盖采集来的源视频）
                after = app.store.get_draft(d["id"])
                self.assertEqual(after["video_url"], "https://storage.googleapis.com/out.mp4")
                self.assertEqual((after.get("source_raw") or {}).get("video_local"),
                                 "/media/draft-%d-ai/video.mp4" % d["id"])
            finally:
                agnes_mod.create_video_task = orig_create
                agnes_mod.query_video = orig_query
                media_mod.download_video = orig_dlv
                av._sleep = orig_sleep
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)

    def test_start_requires_key_and_images(self):
        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                # 语义变更:采集图→素材,图集为空;用 generated 加图集图后才有主图可用
                d = _new_draft(app, "https://x/5")
                app.store.add_draft_image(d["id"], "https://a/1.jpg",
                                          type="白底主图", source="generated")
                with self.assertRaises(RuntimeError):   # 未配 Agnes key → 启动前报错
                    app.start_ai_video(d["id"])
                app.store.save_settings({"agnes_api_key": "K"})
                d2 = _new_draft(app, "https://x/6")
                with self.assertRaises(ValueError):     # 无图无法图生视频
                    app.start_ai_video(d2["id"])
            finally:
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)


class ReviewFixesTest(unittest.TestCase):
    """对抗 review 确认问题的回归：竞态重读 / local_images 对齐 / 视频副本刷新 / 状态保持 / 发布兜底。"""

    def test_image_write_rereads_draft_no_lost_update(self):
        # 生成期间（fake_gen 阻塞点）别的写者改了 images——写回时必须基于最新值，不丢并发图
        import webui.agnes as agnes_mod
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db, orig_root = store_mod.DEFAULT_DB, media_mod.MEDIA_ROOT
        orig_gen = agnes_mod.generate_image
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp) / "images"
            svc, app = _make_app(tmp)
            orig_dl = svc._download_bytes
            try:
                # 语义变更:采集图→素材,测试意图是"并发生图时读最新 images 快照"
                # 先用 generated 在图集里放一张图
                d = _new_draft(app, "https://x/7")
                app.store.add_draft_image(d["id"], "https://a/1.jpg",
                                          type="白底主图", source="generated")
                d = app.store.get_draft(d["id"])
                def fake_gen(settings, prompt, *, size="1024x768", source_images=None):
                    # 模拟生成耗时窗口内的并发编辑：用户又加了一张图
                    cur = app.store.get_draft(d["id"])
                    app.store.update_draft(d["id"], {"images": [*cur["images"], "https://a/2.jpg"]})
                    return "https://cdn.agnes/gen.png"
                agnes_mod.generate_image = fake_gen
                svc._download_bytes = lambda url, timeout=120: b"PNG"
                r = app.ai_generate_image(d["id"], prompt="x")
                self.assertEqual(r["draft"]["images"][:2], ["https://a/1.jpg", "https://a/2.jpg"])
                self.assertTrue(r["draft"]["images"][2].startswith("/media/"))
            finally:
                agnes_mod.generate_image = orig_gen
                svc._download_bytes = orig_dl
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                media_mod.MEDIA_ROOT = orig_root
                importlib.reload(svc)

    def test_as_main_keeps_local_images_aligned(self):
        # images↔local_images 按下标配对（前端 localMap）：头插主图必须给 local_images 补位
        import webui.agnes as agnes_mod
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db, orig_root = store_mod.DEFAULT_DB, media_mod.MEDIA_ROOT
        orig_gen = agnes_mod.generate_image
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp) / "images"
            svc, app = _make_app(tmp)
            orig_dl = svc._download_bytes
            try:
                # 语义变更:采集图→素材,测试意图是"as_main 头插时 local_images 对齐"
                # 先建草稿,再 update_draft 把图集图和 local_images 同时设上
                d = _new_draft(app, "https://x/8")
                app.store.update_draft(d["id"], {
                    "images": ["https://a/1.jpg", "https://a/2.jpg"],
                    "local_images": ["/media/draft-x/01.jpg", "/media/draft-x/02.jpg"],
                })
                d = app.store.get_draft(d["id"])
                agnes_mod.generate_image = lambda *a, **kw: "https://cdn.agnes/g.png"
                svc._download_bytes = lambda url, timeout=120: b"PNG"
                r = app.ai_generate_image(d["id"], prompt="x", as_main=True)
                imgs, locs = r["draft"]["images"], r["draft"]["local_images"]
                self.assertEqual(len(locs), 3)
                self.assertEqual(locs[0], "")                       # AI 图补空位
                self.assertEqual(locs[1], "/media/draft-x/01.jpg")  # 原配对不错位
                self.assertEqual(imgs[1], "https://a/1.jpg")
            finally:
                agnes_mod.generate_image = orig_gen
                svc._download_bytes = orig_dl
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                media_mod.MEDIA_ROOT = orig_root
                importlib.reload(svc)

    def test_download_video_overwrite_refreshes_cache(self):
        import urllib.request as ur

        import webui.media as media_mod
        orig_root, orig_urlopen = media_mod.MEDIA_ROOT, ur.urlopen
        with tempfile.TemporaryDirectory() as tmp:
            media_mod.MEDIA_ROOT = Path(tmp) / "images"
            class FakeResp:
                def __init__(self, data): self._d = data
                def read(self, n=-1): return self._d
                def __enter__(self): return self
                def __exit__(self, *a): return False
            payload = {"data": b"VIDEO1"}
            ur.urlopen = lambda req, timeout=60: FakeResp(payload["data"])
            try:
                p1 = media_mod.download_video("https://g/v1.mp4", "k")
                self.assertEqual(media_mod.read_media_bytes(p1), b"VIDEO1")
                payload["data"] = b"VIDEO2"
                # 默认命中缓存（旧行为，采集场景）
                media_mod.download_video("https://g/v2.mp4", "k")
                self.assertEqual(media_mod.read_media_bytes(p1), b"VIDEO1")
                # overwrite=True 强制刷新（AI 重生成场景）
                media_mod.download_video("https://g/v2.mp4", "k", overwrite=True)
                self.assertEqual(media_mod.read_media_bytes(p1), b"VIDEO2")
            finally:
                ur.urlopen = orig_urlopen
                media_mod.MEDIA_ROOT = orig_root

    def test_video_done_drops_stale_local_and_keeps_status(self):
        # 下载失败 → video_local 置空（别播旧副本）；后台写库不得改 status
        import webui.media as media_mod
        import webui.store as store_mod
        orig_db, orig_dlv = store_mod.DEFAULT_DB, media_mod.download_video
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                d = _new_draft(app, "https://x/10", images=["https://a/1.jpg"])
                app.store.update_draft(d["id"], {
                    "status": "published",
                    "source_raw": {"video_local": "/media/draft-old/video.mp4", "keep": 1}})
                media_mod.download_video = lambda url, key, **kw: ""   # 下载失败
                app._on_ai_video_done(d["id"], "https://g/new.mp4")
                after = app.store.get_draft(d["id"])
                self.assertEqual(after["video_url"], "https://g/new.mp4")
                self.assertEqual(after["source_raw"]["video_local"], "")   # 旧指针被清掉
                self.assertEqual(after["source_raw"]["keep"], 1)           # 其余键不丢
                self.assertEqual(after["status"], "published")             # 状态不被悄悄打回
            finally:
                media_mod.download_video = orig_dlv
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)

    def test_resolve_image_input_rejects_video_files(self):
        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                with self.assertRaises(ValueError):
                    app._resolve_image_input("/media/draft-1-ai/video.mp4")
            finally:
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)


class CardChatProviderTest(unittest.TestCase):
    """_card_chat 路由：remote→deepseek_chat；agnes→agnes_chat（vision 时带公网图）。"""

    def test_remote_default_routes_to_deepseek(self):
        import webui.ai_card as aic
        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        orig_chat = aic.deepseek_chat
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                seen = {}
                aic.deepseek_chat = lambda settings, s, u, images=None: seen.update(s=s, u=u) or "R"
                fn = app._card_chat({}, {})
                self.assertEqual(fn("SYS", "USR"), "R")
                self.assertEqual(seen, {"s": "SYS", "u": "USR"})
            finally:
                aic.deepseek_chat = orig_chat
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)

    def test_agnes_with_vision_passes_public_images(self):
        import webui.agnes as agnes_mod
        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        orig_chat = agnes_mod.agnes_chat
        with tempfile.TemporaryDirectory() as tmp:
            svc, app = _make_app(tmp)
            try:
                seen = {}
                def fake(settings, s, u, images=None):
                    seen.update(images=images)
                    return "A"
                agnes_mod.agnes_chat = fake
                settings = {"ai_text": {"engine": "agnes", "api_base": "b", "api_key": "K",
                                        "model": "m", "multimodal": True}}
                draft = {"images": ["/media/draft-1/01.jpg", "https://a/1.jpg", "https://a/2.jpg", "https://a/3.jpg"],
                         "source_raw": {"detail_images": ["https://a/4.jpg", "https://a/5.jpg"]}}
                fn = app._card_chat(settings, draft)
                self.assertEqual(fn("S", "U"), "A")
                # 本地 /media 跳过；multimodal=True 只取第一张公网主图
                self.assertEqual(seen["images"], ["https://a/1.jpg", "https://a/2.jpg", "https://a/3.jpg", "https://a/4.jpg"])
                # multimodal 关 → 不带图
                fn2 = app._card_chat({"ai_text": {"engine": "agnes", "api_base": "b",
                                                  "api_key": "K", "model": "m",
                                                  "multimodal": False}}, draft)
                fn2("S", "U")
                self.assertIsNone(seen["images"])
            finally:
                agnes_mod.agnes_chat = orig_chat
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)


class AgnesRoutesAndSettingsTest(unittest.TestCase):
    def test_routes_and_settings_masking(self):
        from fastapi.testclient import TestClient

        import webui.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.DEFAULT_DB = Path(tmp) / "routes.db"
            import webui.app_service as svc; importlib.reload(svc)
            import webui.main as main_mod; importlib.reload(main_mod)
            app = main_mod.APP
            try:
                client = TestClient(main_mod.app)
                # 设置项：key 只回 _saved 布尔，其余明文回显
                r = client.post("/api/settings", json={
                    "ai_chat_provider": "agnes", "ai_card_vision": True,
                    "agnes_api_base": "https://apihub.agnes-ai.com/v1",
                    "agnes_api_key": "`sk-xxx`",   # 带反引号 → _clean_secret
                    "agnes_chat_model": "agnes-2.0-flash"})
                self.assertEqual(r.status_code, 200)
                s = r.json()["settings"]
                self.assertEqual(s["ai_chat_provider"], "agnes")
                self.assertTrue(s["ai_card_vision"])
                self.assertTrue(s["agnes_api_key_saved"])
                self.assertNotIn("agnes_api_key", s)
                self.assertEqual(app.store.get_settings()["agnes_api_key"], "sk-xxx")
                # 路由错误映射
                self.assertEqual(client.post("/api/drafts/9999/ai-image",
                                             json={"prompt": "x"}).status_code, 404)
                d = _new_draft(app, "https://x/9")
                self.assertEqual(client.post(f"/api/drafts/{d['id']}/ai-image",
                                             json={"prompt": ""}).status_code, 400)
                self.assertEqual(client.post("/api/drafts/9999/ai-video",
                                             json={}).status_code, 404)
                # 状态路由可达
                st = client.get("/api/ai-video/status")
                self.assertEqual(st.status_code, 200)
                self.assertIn(st.json()["status"],
                              ("idle", "done", "error", "stopped", "running"))
            finally:
                app.store.close(); gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)
                importlib.reload(main_mod)


if __name__ == "__main__":
    unittest.main()
