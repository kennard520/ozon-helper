import unittest

from webui.ai_card import navigate_category

TREE = [
    {"description_category_id": 10, "category_name": "Электроника", "children": [
        {"description_category_id": 11, "category_name": "Наушники", "children": [
            {"type_id": 111, "type_name": "Внутриканальные", "description_category_id": 11},
            {"type_id": 112, "type_name": "Накладные", "description_category_id": 11, "disabled": True},
        ]},
    ]},
    {"description_category_id": 20, "category_name": "Сумки", "children": [
        {"type_id": 201, "type_name": "Сумка через плечо", "description_category_id": 20},
    ]},
]


class NavigateCategoryTest(unittest.TestCase):
    def test_drills_to_leaf_by_ai_choices(self):
        calls = []
        answers = ['{"index": 1}', '{"index": 0}']
        def chat(system, user):
            calls.append(user)
            return answers[len(calls) - 1]
        out = navigate_category(TREE, chat, "сумка кожаная")
        self.assertEqual(out["description_category_id"], 20)
        self.assertEqual(out["type_id"], 201)
        self.assertIn("Сумки", out["path"])
        self.assertIn("Сумка через плечо", out["path"])
        self.assertFalse(out["category_fallback"])

    def test_filters_disabled_leaf(self):
        seen_opts = []
        answers = ['{"index": 0}', '{"index": 0}', '{"index": 0}']
        def chat(system, user):
            seen_opts.append(user)
            return answers[len(seen_opts) - 1]
        out = navigate_category(TREE, chat, "наушники")
        self.assertEqual(out["type_id"], 111)
        self.assertNotIn("Накладные", seen_opts[-1])

    def test_invalid_index_retries_then_fallback(self):
        def chat(system, user):
            return '{"index": 99}'
        out = navigate_category(TREE, chat, "x")
        self.assertTrue(out["category_fallback"])
        self.assertEqual(out["description_category_id"], 11)

    def test_empty_tree_returns_none(self):
        self.assertIsNone(navigate_category([], lambda s, u: '{"index":0}', "x"))


if __name__ == "__main__":
    unittest.main()
