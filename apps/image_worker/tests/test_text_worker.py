from __future__ import annotations

import pytest

from image_worker import text_worker


def test_run_understand_skips_wb_without_ai(monkeypatch):
    monkeypatch.setattr(
        text_worker,
        "_get_draft",
        lambda draft_id: {
            "id": draft_id,
            "source_platform": "wb",
            "source_raw": {"source_platform": "wb", "options": [{"name": "Модель", "value": "Mini Jet Fan"}]},
        },
    )
    monkeypatch.setattr(
        text_worker,
        "_settings",
        lambda *_args, **_kwargs: pytest.fail("WB should not call multimodal settings"),
    )

    result = text_worker._run_understand(1280)

    assert result == {"ok": True, "skipped": True, "reason": "wb_text_features"}


def test_resolve_image_accepts_absolute_and_resolves_relative(monkeypatch):
    monkeypatch.setenv("TEXT_WORKER_MEDIA_BASE", "http://8.152.196.119:8585/")

    assert text_worker._resolve_image("https://cdn.test/a.jpg") == "https://cdn.test/a.jpg"
    assert text_worker._resolve_image("//cdn.test/a.jpg") == "https://cdn.test/a.jpg"
    assert (
        text_worker._resolve_image("/oss/ozon-media/a.jpg")
        == "http://8.152.196.119:8585/oss/ozon-media/a.jpg"
    )


def test_resolve_image_rejects_invalid_without_base(monkeypatch):
    monkeypatch.delenv("TEXT_WORKER_MEDIA_BASE", raising=False)
    monkeypatch.delenv("WEBUI_PUBLIC_BASE", raising=False)

    with pytest.raises(ValueError):
        text_worker._resolve_image("/oss/ozon-media/a.jpg")
    with pytest.raises(ValueError):
        text_worker._resolve_image("not-a-url")
