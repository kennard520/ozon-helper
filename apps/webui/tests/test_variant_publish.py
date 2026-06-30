"""Unit tests for variant_publish.py — pure assembly logic, NO network / publish calls."""
from __future__ import annotations

import json
import unittest
from typing import Any

from webui.variant_publish import (
    COLOR_DICT_ATTR_ID,
    COLOR_TEXT_ATTR_ID,
    MODEL_NAME_ATTR_ID,
    build_group_items,
    find_size_aspect_attr,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_draft(
    offer_id: str,
    color: str,
    size: str,
    variant_group: str = "vg-suitcase-01",
) -> dict[str, Any]:
    """Build a minimal valid draft (passes validate_draft) with selected_aspects."""
    return {
        "id": hash(offer_id) % 1000,
        "offer_id": offer_id,
        "source_offer_id": offer_id,
        "ozon_title": f"Чемодан {color} {size}",
        "description": "Практичный чемодан для путешествий.",
        "category_id": "17028922",
        "type_id": "94307",
        "price": "3999",
        "old_price": "4999",
        "weight_g": 3500,
        "length_mm": 60,
        "width_mm": 40,
        "height_mm": 25,
        "images": ["https://cdn.example.test/img.jpg"],
        "attributes": [],
        "source_raw": json.dumps({
            "variant_group": variant_group,
            "selected_aspects": [
                {"aspect": "Цвет", "aspect_key": "Color", "value": color},
                {"aspect": "Размер чемодана", "aspect_key": "SuitcaseSize", "value": size},
            ],
        }),
    }


# Category attrs for the suitcase category
_CATEGORY_ATTRS: list[dict[str, Any]] = [
    # color dict aspect
    {
        "id": COLOR_DICT_ATTR_ID,   # 10096
        "name": "Цвет товара",
        "is_required": True,
        "is_aspect": True,
        "dictionary_id": 123,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
    # color text aspect
    {
        "id": COLOR_TEXT_ATTR_ID,   # 10097
        "name": "Цвет",
        "is_required": False,
        "is_aspect": True,
        "dictionary_id": 0,         # free text — no dictionary
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
    # size aspect (suitcase)
    {
        "id": 9381,
        "name": "Размер чемодана",
        "is_required": True,
        "is_aspect": True,
        "dictionary_id": 4250098,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
    # regular non-aspect attr
    {
        "id": 9048,
        "name": "Название модели",
        "is_required": True,
        "is_aspect": False,
        "dictionary_id": 0,
        "is_collection": False,
        "type": "String",
        "group_name": "",
        "description": "",
        "category_dependent": False,
    },
]


def _stub_resolve_dict(attr_id: int, dictionary_id: int, text: str) -> dict[str, Any] | None:
    """Always resolves; dictionary_value_id encodes the text for easy assertions."""
    return {"dictionary_value_id": 111, "value": text}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class FindSizeAspectAttrTest(unittest.TestCase):

    def test_returns_size_attr_not_color(self) -> None:
        result = find_size_aspect_attr(_CATEGORY_ATTRS)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 9381)

    def test_returns_none_when_no_aspect_attrs(self) -> None:
        attrs_no_aspect = [
            {"id": 100, "name": "Материал", "is_aspect": False, "dictionary_id": 999},
        ]
        self.assertIsNone(find_size_aspect_attr(attrs_no_aspect))

    def test_returns_none_for_empty_list(self) -> None:
        self.assertIsNone(find_size_aspect_attr([]))


class BuildGroupItemsTest(unittest.TestCase):

    def setUp(self) -> None:
        self.draft_white = _make_draft("SKU-WHITE-M", color="Белый", size="M")
        self.draft_beige = _make_draft("SKU-BEIGE-M", color="Бежевый", size="M")
        self.drafts = [self.draft_white, self.draft_beige]
        self.model_name = "TravelPro X1"

    def test_returns_two_items_for_two_drafts(self) -> None:
        items = build_group_items(self.drafts, _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict)
        self.assertEqual(len(items), 2)

    def test_each_item_has_model_name_attr_9048(self) -> None:
        items = build_group_items(self.drafts, _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict)
        for item in items:
            attr_ids = [a["id"] for a in item["attributes"]]
            self.assertIn(MODEL_NAME_ATTR_ID, attr_ids)
            model_attrs = [a for a in item["attributes"] if a["id"] == MODEL_NAME_ATTR_ID]
            self.assertEqual(model_attrs[0]["values"][0]["value"], self.model_name)

    def test_each_item_has_color_dict_and_text_attrs(self) -> None:
        items = build_group_items(self.drafts, _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict)
        expected_colors = ["Белый", "Бежевый"]
        for item, expected_color in zip(items, expected_colors):
            attr_ids = [a["id"] for a in item["attributes"]]
            # 10096 color dict
            self.assertIn(COLOR_DICT_ATTR_ID, attr_ids)
            color_dict = next(a for a in item["attributes"] if a["id"] == COLOR_DICT_ATTR_ID)
            self.assertEqual(color_dict["values"][0]["dictionary_value_id"], 111)
            # 10097 color text
            self.assertIn(COLOR_TEXT_ATTR_ID, attr_ids)
            color_text = next(a for a in item["attributes"] if a["id"] == COLOR_TEXT_ATTR_ID)
            self.assertEqual(color_text["values"][0]["value"], expected_color)

    def test_each_item_has_size_aspect_attr_9381(self) -> None:
        items = build_group_items(self.drafts, _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict)
        for item in items:
            attr_ids = [a["id"] for a in item["attributes"]]
            self.assertIn(9381, attr_ids)
            size_attr = next(a for a in item["attributes"] if a["id"] == 9381)
            self.assertEqual(size_attr["values"][0]["dictionary_value_id"], 111)
            # value is the original size text "M"
            self.assertEqual(size_attr["values"][0]["value"], "M")

    def test_incomplete_draft_raises_value_error(self) -> None:
        """to_ozon_import_item raises ValueError for incomplete drafts; build_group_items propagates."""
        bad_draft = {
            "id": 99,
            "offer_id": "BAD-DRAFT",
            # ozon_title deliberately missing → validate_draft hard error
            "description": "Описание",
            "category_id": "17028922",
            "type_id": "94307",
            "price": "999",
            "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
            "images": ["https://cdn.example.test/img.jpg"],
        }
        with self.assertRaises(ValueError):
            build_group_items([bad_draft], _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict)

    def test_no_size_attr_in_category_still_produces_items(self) -> None:
        """If category has no size aspect, items still get 9048 + color attrs."""
        color_only_attrs = [a for a in _CATEGORY_ATTRS if a["id"] in (COLOR_DICT_ATTR_ID, COLOR_TEXT_ATTR_ID)]
        items = build_group_items(
            [self.draft_white], color_only_attrs, self.model_name, _stub_resolve_dict
        )
        self.assertEqual(len(items), 1)
        attr_ids = [a["id"] for a in items[0]["attributes"]]
        self.assertIn(MODEL_NAME_ATTR_ID, attr_ids)
        self.assertIn(COLOR_DICT_ATTR_ID, attr_ids)
        self.assertNotIn(9381, attr_ids)

    def test_source_raw_as_string_is_parsed(self) -> None:
        """source_raw stored as JSON string (DB row) must still be parsed correctly."""
        # _make_draft already stores source_raw as a JSON string — just verify it works
        items = build_group_items(
            [self.draft_white], _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict
        )
        attr_ids = [a["id"] for a in items[0]["attributes"]]
        self.assertIn(COLOR_TEXT_ATTR_ID, attr_ids)

    def test_model_name_not_duplicated_if_already_present(self) -> None:
        """If draft already has attr 9048 set, build_group_items must NOT add a second copy."""
        draft_with_model = dict(self.draft_white)
        draft_with_model["attributes"] = [
            {"id": MODEL_NAME_ATTR_ID, "values": [{"value": self.model_name}]}
        ]
        items = build_group_items(
            [draft_with_model], _CATEGORY_ATTRS, self.model_name, _stub_resolve_dict
        )
        count_9048 = sum(1 for a in items[0]["attributes"] if a["id"] == MODEL_NAME_ATTR_ID)
        self.assertEqual(count_9048, 1)


if __name__ == "__main__":
    unittest.main()
