import unittest

from ozon_common.oss import OssClient


class _FakeBucket:
    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.signed = []

    def object_exists(self, key):
        return key in self.existing

    def sign_url(self, method, key, expires, headers=None, slash_safe=False):
        self.signed.append((method, key))
        return f"https://signed/{method}/{key}?exp={expires}"


def _client(bucket):
    return OssClient(
        {"oss_endpoint": "oss-cn-shanghai.aliyuncs.com", "oss_bucket": "b",
         "oss_access_key_id": "ak", "oss_access_key_secret": "sk"},
        bucket=bucket,
    )


class OssPresignTest(unittest.TestCase):
    def test_presign_new_object(self):
        b = _FakeBucket()
        c = _client(b)
        out = c.presign_items([{"key": "ozon-media/abc123.jpg", "content_type": "image/jpeg"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["key"], "ozon-media/abc123.jpg")
        self.assertTrue(out[0]["upload_url"].startswith("https://signed/PUT/"))
        self.assertTrue(out[0]["url"].endswith("/ozon-media/abc123.jpg"))
        self.assertEqual(b.signed, [("PUT", "ozon-media/abc123.jpg")])

    def test_existing_object_not_signed(self):
        b = _FakeBucket(existing={"ozon-media/dup.jpg"})
        c = _client(b)
        out = c.presign_items([{"key": "ozon-media/dup.jpg"}])
        self.assertIsNone(out[0]["upload_url"])           # 已存在 → 不再上传(去重)
        self.assertTrue(out[0]["url"].endswith("/ozon-media/dup.jpg"))
        self.assertEqual(b.signed, [])                    # 没签 PUT

    def test_rejects_non_prefix_key(self):
        b = _FakeBucket()
        c = _client(b)
        # 非 ozon-media/ 前缀 → 拒签，防越权覆盖他人对象
        out = c.presign_items([{"key": "../../secret.jpg"}, {"key": "other/x.jpg"}])
        self.assertEqual(out, [])
        self.assertEqual(b.signed, [])

    def test_mixed_batch(self):
        b = _FakeBucket(existing={"ozon-media/has.png"})
        c = _client(b)
        out = c.presign_items([
            {"key": "ozon-media/has.png"},
            {"key": "ozon-media/new.png", "content_type": "image/png"},
        ])
        self.assertEqual(len(out), 2)
        self.assertIsNone(out[0]["upload_url"])
        self.assertIsNotNone(out[1]["upload_url"])


class AppPresignTest(unittest.TestCase):
    def test_presign_media_requires_oss(self):
        import importlib
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            import webui.store as store_mod
            store_mod.DEFAULT_DB = Path(tmp) / "p.db"
            import webui.app_service as svc
            importlib.reload(svc)
            app = svc.App()
            try:
                with self.assertRaises(ValueError):
                    app.presign_media([{"key": "ozon-media/x.jpg"}])  # 没配 OSS → 报错
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
