from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from webui.ai_card import build_profile  # noqa: E402

RAW = {"title": "铁油桶 15L", "params": [{"k": "材质", "v": "镀锌钢"}], "description_text": "便携"}
UND = {
    "type": "铁皮油桶", "material": "镀锌钢板",
    "specs": {"容量": "15л", "高": "36см"},
    "points": ["加厚防漏", "密封盖"], "scenes": ["自驾备油"], "kit": ["油桶x1", "软管x1"],
}


class BuildProfileTest(unittest.TestCase):
    def test_basic_without_understanding(self) -> None:
        p = build_profile(RAW)
        self.assertIn("Title: 铁油桶 15L", p)
        self.assertIn("材质: 镀锌钢", p)
        self.assertIn("Description: 便携", p)
        self.assertNotIn("Selling points", p)

    def test_understanding_facts_merged(self) -> None:
        p = build_profile(RAW, understanding=UND)
        self.assertIn("Type: 铁皮油桶", p)
        self.assertIn("Material: 镀锌钢板", p)
        self.assertIn("容量: 15л", p)
        self.assertIn("高: 36см", p)
        self.assertIn("Selling points: 加厚防漏; 密封盖", p)
        self.assertIn("Use scenes: 自驾备油", p)
        self.assertIn("Package: 油桶x1; 软管x1", p)

    def test_empty_understanding_ignored(self) -> None:
        self.assertNotIn("Selling points", build_profile(RAW, understanding={}))

    def test_wb_category_and_drawer_features_are_profile_input(self) -> None:
        raw = {
            "imt_name": "Mini jet fan",
            "subj_root_name": "Garden",
            "subj_name": "Blowers",
            "description": "Cordless handheld blower.",
            "contents": "Blower, case, nozzles",
            "options": [{"name": "Battery type", "value": "Li-Ion"}],
            "grouped_options": [
                {"group_name": "Extra", "options": [
                    {"name": "Air speed", "value": "62 m/s"},
                    {"name": "Battery type", "value": "Li-Ion"},
                ]}
            ],
        }

        p = build_profile(raw)

        self.assertIn("Title: Mini jet fan", p)
        self.assertIn("Source category: Garden / Blowers", p)
        self.assertIn("Battery type: Li-Ion", p)
        self.assertIn("Air speed: 62 m/s", p)
        self.assertEqual(p.count("Battery type: Li-Ion"), 1)
        self.assertIn("Contents: Blower, case, nozzles", p)
        self.assertIn("Description: Cordless handheld blower.", p)


if __name__ == "__main__":
    unittest.main()
