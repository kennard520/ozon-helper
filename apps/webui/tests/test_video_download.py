from __future__ import annotations

import tempfile
import unittest
import urllib.request
from pathlib import Path

import webui.media as media


class _FakeResp:
    def __init__(self, data: bytes):
        self._d = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            d, self._d = self._d, b""
            return d
        d, self._d = self._d[:n], self._d[n:]
        return d


class TestDownloadVideo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_root = media.MEDIA_ROOT
        media.MEDIA_ROOT = Path(self._tmp.name)
        self._orig_open = urllib.request.urlopen

    def tearDown(self):
        urllib.request.urlopen = self._orig_open
        media.MEDIA_ROOT = self._orig_root
        self._tmp.cleanup()

    def _patch(self, data: bytes):
        urllib.request.urlopen = lambda req, timeout=0: _FakeResp(data)

    def test_downloads_and_returns_media_path(self):
        self._patch(b"\x00\x01fakevideo")
        rel = media.download_video("https://cloud.video.taobao.com/x/435852352518.mp4", "draft-202")
        self.assertEqual(rel, "/media/draft-202/video.mp4")
        # 文件真的落地
        self.assertTrue((media.MEDIA_ROOT / "draft-202" / "video.mp4").exists())

    def test_non_http_returns_empty(self):
        self.assertEqual(media.download_video("/media/x/y.mp4", "k"), "")
        self.assertEqual(media.download_video("", "k"), "")

    def test_oversize_rejected(self):
        self._patch(b"x" * 200)
        rel = media.download_video("https://h/v.mp4", "k", max_bytes=100)
        self.assertEqual(rel, "")

    def test_ext_from_url(self):
        self._patch(b"data")
        rel = media.download_video("https://h/clip.mov", "k")
        self.assertTrue(rel.endswith("/video.mov"))


if __name__ == "__main__":
    unittest.main()
