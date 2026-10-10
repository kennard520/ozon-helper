from __future__ import annotations

import json
import unittest

from webui.media_rehost import public_oss_url, rewrite_item_media

S = {
    "oss_public_base": "http://8.152.196.119:8585/oss",
    "oss_bucket": "ozon-helper",
    "oss_endpoint": "oss-cn-beijing.aliyuncs.com",
}
DIRECT = "https://ozon-helper.oss-cn-beijing.aliyuncs.com/"


class PublicOssUrlTest(unittest.TestCase):
    def test_proxy_to_direct(self):
        u = "http://8.152.196.119:8585/oss/ozon-media/abc.jpg"
        self.assertEqual(public_oss_url(u, S), DIRECT + "ozon-media/abc.jpg")

    def test_ozon_cdn_unchanged(self):
        u = "https://ir.ozone.ru/s3/x/a.jpg"
        self.assertEqual(public_oss_url(u, S), u)

    def test_no_config_unchanged(self):
        u = "http://8.152.196.119:8585/oss/ozon-media/abc.jpg"
        self.assertEqual(public_oss_url(u, {}), u)


class RewriteItemMediaTest(unittest.TestCase):
    def test_rewrites_images_video_rich(self):
        rich = {"content": [{"blocks": [{"img": {"src": "http://8.152.196.119:8585/oss/ozon-media/r.jpg"}}]}]}
        item = {
            "offer_id": "1",
            "images": ["http://8.152.196.119:8585/oss/ozon-media/a.jpg", "https://ir.ozone.ru/b.jpg"],
            "attributes": [{"id": 11254, "complex_id": 0, "values": [{"value": json.dumps(rich)}]}],
            "complex_attributes": [{"attributes": [
                {"complex_id": 100001, "id": 21841, "values": [{"value": "http://8.152.196.119:8585/oss/ozon-media/v.mp4"}]},
                {"complex_id": 100001, "id": 21837, "values": [{"value": "видео"}]},
            ]}],
        }
        out = rewrite_item_media(item, S)
        # 图集：代理→直链，Ozon 原生不动
        self.assertEqual(out["images"], [DIRECT + "ozon-media/a.jpg", "https://ir.ozone.ru/b.jpg"])
        # 视频
        self.assertEqual(out["complex_attributes"][0]["attributes"][0]["values"][0]["value"],
                         DIRECT + "ozon-media/v.mp4")
        # 富文本内嵌图
        node = json.loads(out["attributes"][0]["values"][0]["value"])
        self.assertEqual(node["content"][0]["blocks"][0]["img"]["src"], DIRECT + "ozon-media/r.jpg")
        # 原 item 不被改动（深拷贝）
        self.assertEqual(item["images"][0], "http://8.152.196.119:8585/oss/ozon-media/a.jpg")


if __name__ == "__main__":
    unittest.main()
