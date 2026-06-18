import unittest
from backend.ai_card import generate_card

TREE = [
    {"description_category_id": 20, "category_name": "Сумки", "children": [
        {"type_id": 201, "type_name": "Сумка через плечо", "description_category_id": 20},
    ]},
]


class GenerateCardNavTest(unittest.TestCase):
    def test_uses_category_roots_navigation(self):
        # 序列：2 次类目下钻 + 文案(标题/描述/标签) + 属性(尺寸/毛重)
        seq = ['{"index":0}', '{"index":0}',
               '{"ozon_title":"Сумка кожаная","description":"опис","hashtags":["сумка","#кожа"]}',
               '{"attributes":[],"weight_g":300,"length_cm":20,"width_cm":15,"height_cm":8}']
        st = {"i": 0}
        def chat(system, user):
            r = seq[st["i"]]; st["i"] += 1; return r
        out = generate_card({"title": "сумка"}, chat=chat, category_roots=TREE,
                            fetch_required_attrs=lambda c, t: [], resolve_values=lambda *a: [])
        self.assertTrue(out["ok"])
        self.assertEqual(out["category_id"], "20")
        self.assertEqual(out["type_id"], "201")
        self.assertIn("Сумка через плечо", out["category_path"])
        self.assertEqual(out["ozon_title"], "Сумка кожаная")   # 来自文案请求
        self.assertEqual(out["description"], "опис")
        self.assertEqual(out["weight_g"], 300)                  # 来自属性请求
        # 标签 → attr 23171，单串、# 前缀
        tag_attr = next(a for a in out["attributes"] if int(a["id"]) == 23171)
        self.assertEqual(tag_attr["values"][0]["value"], "#сумка #кожа")

    def test_nav_failure_returns_error(self):
        out = generate_card({"title": "x"}, chat=lambda s, u: '{"index":0}',
                            category_roots=[], fetch_required_attrs=lambda c, t: [],
                            resolve_values=lambda *a: [])
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
