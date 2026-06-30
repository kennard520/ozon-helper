from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ozon_common.image_plan import build_image_plan  # noqa: E402

IMAGES = [f"https://oss/{i}.jpg" for i in range(4)]
UND = {
    "images": [{"idx": 0, "role": "整体"}, {"idx": 1, "role": "整体"},
               {"idx": 2, "role": "细节"}, {"idx": 3, "role": "细节"}],
    "points": ["4L大容量", "140°夜视摄像头", "双向语音"],
    "specs": {"尺寸": "205×205×305 mm"},
}


class BuildImagePlanTest(unittest.TestCase):
    def test_slots_and_actions(self) -> None:
        plan = build_image_plan(UND, IMAGES)
        by_id = {s["slot_id"]: s for s in plan}
        self.assertIn("main", by_id)
        self.assertEqual(by_id["main"]["action"], "white")
        self.assertEqual(by_id["main"]["source_idx"], 0)        # 整体图
        self.assertEqual(by_id["scene1"]["action"], "scene")
        self.assertEqual(by_id["size"]["action"], "infographic")
        self.assertEqual(by_id["size"]["bullets"], ["205×205×305 mm"])

    def test_details_use_distinct_sources(self) -> None:
        plan = build_image_plan(UND, IMAGES)
        details = [s for s in plan if s["role"] == "细节"]
        self.assertEqual(len(details), 2)
        self.assertEqual({d["source_idx"] for d in details}, {2, 3})   # 不同源图，避重复角度

    def test_points_capped(self) -> None:
        plan = build_image_plan(UND, IMAGES, max_points=2)
        pts = [s for s in plan if s["role"] == "卖点"]
        self.assertEqual(len(pts), 2)                                   # 3 个卖点裁到 2
        self.assertEqual(pts[0]["bullets"], ["4L大容量"])

    def test_no_understanding_minimal_plan(self) -> None:
        plan = build_image_plan(None, IMAGES)
        ids = {s["slot_id"] for s in plan}
        self.assertIn("main", ids)
        self.assertIn("scene1", ids)
        self.assertNotIn("size", ids)                                   # 无 specs → 无尺寸图

    def test_empty_images_empty_plan(self) -> None:
        self.assertEqual(build_image_plan(UND, []), [])


if __name__ == "__main__":
    unittest.main()
