from __future__ import annotations

from ozon_mcp.tools import CHATGPT_TOOL_NAMES, _stage_done, _variant_work_status, register_tools
from ozon_mcp.runtime import compact_draft, draft_ids_for_scope


class FakeMcp:
    def __init__(self) -> None:
        self.names: list[str] = []

    def tool(self):
        def _decorator(fn):
            self.names.append(fn.__name__)
            return fn

        return _decorator


def test_compact_draft_keeps_core_fields_and_counts_images() -> None:
    draft = {
        "id": 7,
        "source_url": "https://example.test/item",
        "ozon_title": "Title",
        "description": "Desc",
        "images": [{"url": "a"}, {"url": "b"}],
        "attributes": [{"id": 1}, {"id": 2}],
        "secret": "hidden",
    }

    out = compact_draft(draft)

    assert out is not None
    assert out["id"] == 7
    assert out["image_count"] == 2
    assert out["attribute_count"] == 2
    assert "secret" not in out


def test_register_tools_can_expose_chatgpt_subset_only() -> None:
    fake = FakeMcp()

    register_tools(fake, include_tools=CHATGPT_TOOL_NAMES)

    assert set(fake.names) == set(CHATGPT_TOOL_NAMES)
    assert "openai_generate_product_image" in fake.names
    assert "get_ozon_analytics_context" in fake.names
    assert "chatgpt_save_optimization_notes" in fake.names
    assert "generate_image" not in fake.names
    assert "publish_draft" not in fake.names


def test_draft_ids_for_scope_expands_variant_group() -> None:
    class FakeApp:
        def get_draft(self, draft_id: int):
            return {"id": draft_id, "source_raw": {"variant_group": "G"}}

        def variant_group_siblings(self, draft_id: int):
            return {"variants": [{"id": 3}, {"id": "4"}]}

    group, ids = draft_ids_for_scope(FakeApp(), 3, "group")

    assert group == "G"
    assert ids == [3, 4]


def test_draft_ids_for_scope_keeps_single_draft_without_group() -> None:
    class FakeApp:
        def get_draft(self, draft_id: int):
            return {"id": draft_id, "source_raw": {}}

    group, ids = draft_ids_for_scope(FakeApp(), 9, "group")

    assert group == ""
    assert ids == [9]


def test_variant_listing_status_requires_category_and_attributes() -> None:
    status = _variant_work_status(
        {
            "ozon_title": "Title",
            "description": "Desc",
            "category_id": "",
            "type_id": "",
            "attributes": [],
            "source_raw": {},
        }
    )

    assert status["listing"] is False
    assert status["missing"]["listing"] == ["category_id", "type_id", "attributes"]
    assert _stage_done(status, "listing") is False


def test_variant_listing_status_done_with_category_and_attributes() -> None:
    status = _variant_work_status(
        {
            "ozon_title": "Title",
            "description": "Desc",
            "category_id": "123",
            "type_id": "456",
            "attributes": [{"id": 1, "values": [{"value": "x"}]}],
            "source_raw": {},
        }
    )

    assert status["listing"] is True
    assert status["missing"]["listing"] == []
    assert _stage_done(status, "listing") is True
