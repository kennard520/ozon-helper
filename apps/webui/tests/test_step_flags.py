from webui.app_service import step_flags


def _d(**kw):
    base = {
        "source_raw": {},
        "attributes": [],
        "category_id": "",
        "type_id": "",
        "ozon_title": "",
        "description": "",
        "images": [],
        "ozon_product_id": "",
        "status": "draft",
    }
    base.update(kw)
    return base


def test_understand():
    assert step_flags(_d(source_raw={"understanding": {"x": 1}}))["understand"] is True
    assert step_flags(_d())["understand"] is False


def test_category_copy_publish():
    assert step_flags(_d(category_id="1", type_id="2"))["category"] is True
    assert step_flags(_d(ozon_title="T", description="D"))["copy"] is True
    assert step_flags(_d(status="published"))["publish"] is True
    assert step_flags(_d(ozon_product_id="999"))["publish"] is True


def test_attrs_excludes_placeholders():
    # id 9048 是排除项(型号名占位符)
    assert step_flags(_d(attributes=[{"id": 9048, "values": [{"value": "x"}]}]))["attrs"] is False
    assert step_flags(_d(attributes=[{"id": 1234, "values": [{"value": "x"}]}]))["attrs"] is True


def test_images():
    assert step_flags(_d(images=["a.jpg"]))["images"] is True
    assert step_flags(_d(source_raw={"image_types": {"a": "主图"}}))["images"] is True
    assert step_flags(_d())["images"] is False


def test_returns_7_keys():
    assert set(step_flags(_d())) == {
        "understand", "category", "copy", "attrs", "images", "rich", "publish"
    }


def test_rich():
    assert step_flags(_d(source_raw={"rich_content_json": {"blocks": []}}))["rich"] is True
    assert step_flags(_d())["rich"] is False


def test_done_count():
    # category_id+type_id => category=True, ozon_title+description => copy=True → done=2
    assert (
        sum(
            step_flags(
                _d(category_id="1", type_id="2", ozon_title="T", description="D")
            ).values()
        )
        == 2
    )
