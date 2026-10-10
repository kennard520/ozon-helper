import json


def _leaf(cat, typ, path):
    node = {"description_category_id": cat, "category_name": path[0], "children": []}
    cur = node
    for name in path[1:-1]:
        child = {"category_name": name, "children": []}
        cur["children"].append(child)
        cur = child
    cur["children"].append({"type_id": typ, "type_name": path[-1]})
    return node


def test_broad_then_leaf_only_expands_selected_root_categories():
    from ozon_common.text_pipeline.ai_card import navigate_category_broad_then_leaf

    roots = [
        _leaf(1, 11, ["Household", "Laundry soap"]),
        _leaf(2, 22, ["Beauty", "Body hygiene", "Solid soap"]),
        _leaf(3, 33, ["Pharmacy", "Skin care", "Cream"]),
        _leaf(4, 44, ["Construction", "Tools", "Drill"]),
    ]
    calls = []

    def chat(_system, user):
        calls.append(user)
        if "Root categories" in user:
            root_options = json.loads(user.split("Root categories:\n", 1)[1].split("\n\nProduct:", 1)[0])
            assert [opt["name"] for opt in root_options] == ["Household", "Beauty", "Pharmacy", "Construction"]
            return '{"indices": [1, 0]}'
        leaf_options = json.loads(
            user.split("Final category candidates (pick the best matching final leaf index):\n", 1)[1]
            .split("\n\nProduct:", 1)[0]
        )
        assert [opt["path"] for opt in leaf_options] == [
            "Beauty / Body hygiene / Solid soap",
            "Household / Laundry soap",
        ]
        return '{"index": 0}'

    nav = navigate_category_broad_then_leaf(roots, chat, "handmade goat milk soap for face and body")

    assert len(calls) == 2
    assert nav["description_category_id"] == 2
    assert nav["type_id"] == 22
