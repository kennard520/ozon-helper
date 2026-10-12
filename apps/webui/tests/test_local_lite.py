from types import SimpleNamespace

from ozon_common.dal.engine import engine_for
from webui.services._auth import AuthMixin
from webui.services._publish import PublishMixin


def test_lite_collect_keeps_source_but_excludes_uneditable_video_and_rich(monkeypatch):
    from webui.services._ext import prepare_collect_data
    monkeypatch.setenv("OZON_LOCAL_LITE", "1")
    source = {"video_url": "https://wb.example/video.mp4", "source_raw": {
        "rich_content_json": {"content": [{"img": {"src": "https://wb.example/a.jpg"}}]},
    }}
    result = prepare_collect_data(source)
    assert result["video_url"] == ""
    assert "rich_content_json" not in result["source_raw"]
    assert result["source_raw"]["collected_video_url"] == source["video_url"]
    assert source["source_raw"]["rich_content_json"]


def test_lite_ignores_inherited_mysql(monkeypatch, tmp_path):
    monkeypatch.setenv("OZON_LOCAL_LITE", "1")
    monkeypatch.setenv("OZON_MYSQL_HOST", "must-not-connect.invalid")
    engine = engine_for(str(tmp_path / "lite.db"))
    assert engine.dialect.name == "sqlite"
    engine.dispose()


def test_lite_has_no_publish_fee(monkeypatch):
    monkeypatch.setenv("OZON_LOCAL_LITE", "1")
    app = AuthMixin()
    app.store = SimpleNamespace(get_settings=lambda: {"publish_fee": 99})
    assert app.publish_fee() == 0


def test_normal_mode_preserves_fee(monkeypatch):
    monkeypatch.delenv("OZON_LOCAL_LITE", raising=False)
    app = AuthMixin()
    app.store = SimpleNamespace(get_settings=lambda: {"publish_fee": 99})
    assert app.publish_fee() == 99


def test_lite_never_dispatches_auto_publish(monkeypatch):
    monkeypatch.setenv("OZON_LOCAL_LITE", "1")
    app = PublishMixin()
    calls = []
    app.store = SimpleNamespace(
        get_settings=lambda: {"auto_publish": True},
        get_draft=lambda _: {"status": "draft", "media_status": "done"},
    )
    app._dispatch_auto_publish = calls.append
    app._maybe_auto_publish(1)
    assert calls == []


def test_wb_lite_media_callback_leaves_publishable_media_without_oss(monkeypatch, tmp_path):
    import webui.store as store_mod
    from webui.app_service import App
    from webui.media_rehost import needs_rehost

    monkeypatch.setenv("OZON_LOCAL_LITE", "1")
    monkeypatch.setattr(store_mod, "DEFAULT_DB", tmp_path / "app.db")
    app = App()
    monkeypatch.setattr(app, "_auto_match_category", lambda _: None)
    try:
        app.store.save_settings({"auto_publish": True})
        result = app.ext_collect_parsed({"url": "https://www.wildberries.ru/catalog/100/detail.aspx", "data": {
            "source_platform": "wb", "title": "Товар", "price": "100",
            "images": ["https://wb.example/a.jpg", "https://wb.example/b.jpg"],
            "video_url": "https://wb.example/video.mp4",
            "source_raw": {"rich_content_json": {"content": [{"img": {"src": "https://wb.example/a.jpg"}}]}},
        }})
        assert result["auto_publish"] is False
        did = result["created"][0]["id"]
        app.update_draft_media({"draft_id": did, "media_map": {"https://wb.example/a.jpg": "https://ir.ozone.ru/a.jpg"}})
        assert any(d["id"] == did for d in app.pending_media_drafts()["drafts"])
        app.update_draft_media({"draft_id": did, "media_map": {"https://wb.example/b.jpg": "https://ir.ozone.ru/b.jpg"}})
        draft = app.store.get_draft(did)
        assert not needs_rehost(draft)
        assert not any(d["id"] == did for d in app.pending_media_drafts()["drafts"])
        assert draft["source_raw"]["collected_video_url"]
    finally:
        app.store.close()
