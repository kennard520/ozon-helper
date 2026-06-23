from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.recommend import recommend_path  # noqa: E402

CLEAN = {"images": [{"idx": 0, "role": "整体"}, {"idx": 1, "role": "细节"}, {"idx": 2, "role": "场景"}]}
COLLAGE = {"images": [{"idx": 0, "role": "整体"}, {"idx": 1, "role": "卖点"},
                      {"idx": 2, "role": "尺寸"}, {"idx": 3, "role": "包装"}]}


class CopyAvailabilityTest(unittest.TestCase):
    def test_ozon_unprobed_copy_available_and_recommended(self):
        r = recommend_path(source="ozon", understanding=CLEAN, copyable=None)
        self.assertTrue(r["copy"]["available"])
        self.assertEqual(r["recommended"], "复制")

    def test_ozon_prohibited_no_copy(self):
        r = recommend_path(source="ozon", understanding=CLEAN, copyable=False)
        self.assertFalse(r["copy"]["available"])
        self.assertNotEqual(r["recommended"], "复制")

    def test_1688_no_copy(self):
        r = recommend_path(source="1688", understanding=CLEAN)
        self.assertFalse(r["copy"]["available"])

    def test_wb_no_copy(self):
        self.assertFalse(recommend_path(source="WB", understanding=COLLAGE)["copy"]["available"])


class ModeTest(unittest.TestCase):
    def test_clean_images_recommend_localize(self):
        r = recommend_path(source="1688", understanding=CLEAN)
        self.assertEqual(r["recommended"], "俄化")

    def test_collage_images_recommend_redo(self):
        r = recommend_path(source="1688", understanding=COLLAGE)  # 3/4 文字角色
        self.assertEqual(r["recommended"], "重做")

    def test_collage_per_image_all_redo(self):
        r = recommend_path(source="1688", understanding=COLLAGE)
        self.assertTrue(all(p["default"] == "重做" for p in r["per_image"]))

    def test_clean_per_image_visual_keep_text_localize(self):
        # 3 张里仅 1 文字(<50%)→ 俄化模式;per_image:视觉保留、文字俄化
        und = {"images": [{"idx": 0, "role": "整体"}, {"idx": 1, "role": "细节"}, {"idx": 2, "role": "卖点"}]}
        r = recommend_path(source="1688", understanding=und)
        self.assertEqual(r["recommended"], "俄化")
        by = {p["idx"]: p["default"] for p in r["per_image"]}
        self.assertEqual(by[0], "保留")   # 整体(纯视觉)保留
        self.assertEqual(by[1], "保留")   # 细节(纯视觉)保留
        self.assertEqual(by[2], "俄化")   # 卖点(文字)俄化

    def test_half_text_recommends_redo(self):
        # 2/4 文字(=50%)→ 重做(阈值含等于)
        und = {"images": [{"idx": 0, "role": "整体"}, {"idx": 1, "role": "细节"},
                          {"idx": 2, "role": "卖点"}, {"idx": 3, "role": "尺寸"}]}
        self.assertEqual(recommend_path(source="1688", understanding=und)["recommended"], "重做")

    def test_no_understanding_defaults_localize(self):
        r = recommend_path(source="1688", understanding=None)
        self.assertEqual(r["recommended"], "俄化")
        self.assertEqual(r["per_image"], [])


if __name__ == "__main__":
    unittest.main()
