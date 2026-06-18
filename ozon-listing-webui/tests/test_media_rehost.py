import unittest
from backend.media_rehost import rehost_draft_media, needs_rehost, is_ozon_cdn


def fake_upload(url):
    if url.startswith("https://oss/"):
        return url
    if "FAIL" in url:
        raise RuntimeError("boom")
    return "https://oss/" + url.rsplit("/", 1)[-1]


class RehostTest(unittest.TestCase):
    def test_rehosts_images_video_and_rich_images(self):
        # 非 Ozon 源媒体才会被传 OSS（Ozon 原生会跳过，见 OzonCdnSkipTest）
        draft = {
            "images": ["https://src/a.jpg", "https://oss/keep.jpg"],
            "video_url": "https://cloud.video.taobao.com/x.mp4",
            "source_raw": {"rich_content_json": {
                "content": [{"blocks": [
                    {"img": {"src": "https://src/r1.jpg", "srcMobile": "https://src/r1m.jpg"}},
                    {"text": {"content": "hi"}},
                ]}]
            }},
        }
        out, stats = rehost_draft_media(draft, fake_upload)
        self.assertEqual(out["images"][0], "https://oss/a.jpg")
        self.assertEqual(out["images"][1], "https://oss/keep.jpg")
        self.assertEqual(out["video_url"], "https://oss/x.mp4")
        img = out["source_raw"]["rich_content_json"]["content"][0]["blocks"][0]["img"]
        self.assertEqual(img["src"], "https://oss/r1.jpg")
        self.assertEqual(img["srcMobile"], "https://oss/r1m.jpg")
        self.assertEqual(stats["failed"], 0)
        self.assertGreaterEqual(stats["uploaded"], 4)
        # 原 draft 未被就地改坏(deepcopy 富文本)
        self.assertEqual(draft["source_raw"]["rich_content_json"]["content"][0]["blocks"][0]["img"]["src"],
                         "https://src/r1.jpg")

    def test_failure_keeps_original_and_counts(self):
        draft = {"images": ["https://x/FAIL.jpg", "https://x/ok.jpg"], "source_raw": {}}
        out, stats = rehost_draft_media(draft, fake_upload)
        self.assertEqual(out["images"][0], "https://x/FAIL.jpg")
        self.assertEqual(out["images"][1], "https://oss/ok.jpg")
        self.assertEqual(stats["failed"], 1)

    def test_no_rich_no_video_ok(self):
        out, stats = rehost_draft_media({"images": [], "source_raw": {}}, fake_upload)
        self.assertEqual(out["images"], [])

    def test_dedup_shared_url_uploaded_once(self):
        calls = []
        def counting_upload(url):
            calls.append(url)
            return "https://oss/" + url.rsplit("/", 1)[-1]
        draft = {"images": ["https://x/shared.jpg"],
                 "source_raw": {"rich_content_json": {"blocks": [{"img": {"src": "https://x/shared.jpg"}}]}}}
        out, stats = rehost_draft_media(draft, counting_upload)
        self.assertEqual(calls.count("https://x/shared.jpg"), 1)   # 同 URL 只传一次
        self.assertEqual(out["images"][0], "https://oss/shared.jpg")
        self.assertEqual(out["source_raw"]["rich_content_json"]["blocks"][0]["img"]["src"], "https://oss/shared.jpg")


class OzonCdnSkipTest(unittest.TestCase):
    def test_is_ozon_cdn(self):
        self.assertTrue(is_ozon_cdn("https://ir.ozone.ru/s3/x.jpg"))
        self.assertTrue(is_ozon_cdn("https://cdn1.ozone.ru/a.jpg"))
        self.assertFalse(is_ozon_cdn("https://cbu01.alicdn.com/a.jpg"))
        self.assertFalse(is_ozon_cdn(""))

    def test_needs_rehost(self):
        # 全 Ozon 原生 → 不需要 OSS
        self.assertFalse(needs_rehost({"images": ["https://ir.ozone.ru/a.jpg"]}))
        # 含非 Ozon → 需要
        self.assertTrue(needs_rehost({"images": ["https://cbu01.alicdn.com/a.jpg"]}))
        # 富文本内嵌非 Ozon 图 → 需要
        self.assertTrue(needs_rehost({"images": [], "source_raw": {"rich_content_json": {
            "blocks": [{"img": {"src": "https://x/r.jpg"}}]}}}))

    def test_rehost_skips_ozon_cdn(self):
        # ir.ozone.ru 不应被传 OSS，原样保留；非 Ozon 才传
        calls = []

        def up(u):
            calls.append(u)
            return "https://oss/" + u.rsplit("/", 1)[-1]

        draft = {"images": ["https://ir.ozone.ru/keep.jpg", "https://x/move.jpg"], "source_raw": {}}
        out, stats = rehost_draft_media(draft, up)
        self.assertEqual(out["images"][0], "https://ir.ozone.ru/keep.jpg")  # Ozon 原生不动
        self.assertEqual(out["images"][1], "https://oss/move.jpg")          # 非 Ozon 传 OSS
        self.assertEqual(calls, ["https://x/move.jpg"])                     # 只传了一个
        self.assertEqual(stats["uploaded"], 1)


if __name__ == "__main__":
    unittest.main()
