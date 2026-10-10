import unittest

from ozon_common.oss import OssClient


class FakeBucket:
    def __init__(self):
        self.store = {}
        self.put_calls = 0

    def object_exists(self, key):
        return key in self.store

    def put_object(self, key, data):
        self.put_calls += 1
        self.store[key] = data


SET = {"oss_endpoint": "oss-cn-hangzhou.aliyuncs.com", "oss_bucket": "mybkt",
       "oss_access_key_id": "ak", "oss_access_key_secret": "sk"}


class OssClientTest(unittest.TestCase):
    def test_not_configured_when_missing_fields(self):
        self.assertFalse(OssClient({}).configured())
        self.assertTrue(OssClient(SET).configured())

    def test_upload_bytes_md5_key_and_default_url(self):
        fb = FakeBucket()
        c = OssClient(SET, bucket=fb)
        url = c.upload_bytes(b"hello", "jpg")
        self.assertEqual(url, "https://mybkt.oss-cn-hangzhou.aliyuncs.com/ozon-media/5d41402abc4b2a76b9719d911017c592.jpg")
        self.assertEqual(fb.put_calls, 1)

    def test_upload_bytes_idempotent(self):
        fb = FakeBucket()
        c = OssClient(SET, bucket=fb)
        c.upload_bytes(b"hello", "jpg")
        c.upload_bytes(b"hello", "jpg")
        self.assertEqual(fb.put_calls, 1)

    def test_public_base_overrides_domain(self):
        s = {**SET, "oss_public_base": "https://cdn.example.com"}
        c = OssClient(s, bucket=FakeBucket())
        url = c.upload_bytes(b"x", "png")
        self.assertTrue(url.startswith("https://cdn.example.com/ozon-media/"))

    def test_upload_remote_skips_when_already_on_oss(self):
        fb = FakeBucket()
        c = OssClient(SET, bucket=fb)
        u = "https://mybkt.oss-cn-hangzhou.aliyuncs.com/ozon-media/abc.jpg"
        self.assertEqual(c.upload_remote(u), u)
        self.assertEqual(fb.put_calls, 0)


if __name__ == "__main__":
    unittest.main()
