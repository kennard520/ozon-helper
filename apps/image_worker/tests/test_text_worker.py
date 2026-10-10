from __future__ import annotations

import json
from contextlib import contextmanager

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


def test_run_understand_skips_1688_without_images(monkeypatch):
    monkeypatch.setattr(
        text_worker,
        "_get_draft",
        lambda draft_id: {
            "id": draft_id,
            "source_platform": "1688",
            "source_raw": {"attributes": [{"name": "重量", "value": "120g"}]},
            "images": [],
        },
    )
    monkeypatch.setattr(
        text_worker,
        "_settings",
        lambda *_args, **_kwargs: pytest.fail("No-image drafts should not call multimodal settings"),
    )

    result = text_worker._run_understand(1306)

    assert result == {"ok": True, "skipped": True, "reason": "no_images"}


def test_run_understand_skips_when_multimodal_access_is_denied(monkeypatch):
    monkeypatch.setattr(
        text_worker,
        "_get_draft",
        lambda draft_id: {
            "id": draft_id,
            "user_id": 1,
            "source_platform": "1688",
            "source_raw": {"attributes": [{"name": "weight", "value": "120g"}]},
            "images": ["http://example.test/image.jpg"],
        },
    )
    monkeypatch.setattr(text_worker, "_settings", lambda *_args, **_kwargs: {"ai_multimodal": {"api_key": "K"}})
    monkeypatch.setattr(text_worker, "_resolve_image", lambda url: url)
    monkeypatch.setattr(
        text_worker,
        "_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError('AI HTTP 403: {"error":{"type":"access_denied"}}')
        ),
    )
    monkeypatch.setattr(
        text_worker,
        "_update_draft",
        lambda *_args, **_kwargs: pytest.fail("access denied should not cache understanding"),
    )

    result = text_worker._run_understand(1306)

    assert result == {
        "ok": True,
        "skipped": True,
        "reason": "multimodal_access_denied",
        "error": 'AI HTTP 403: {"error":{"type":"access_denied"}}',
    }


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


def test_chat_uses_nvidia_for_text_and_multimodal(monkeypatch):
    calls = []

    def fake_chat(cfg, system, user):
        calls.append(("text", cfg, system, user))
        return "TEXT"

    def fake_vlm(cfg, system, user, images=None):
        calls.append(("vlm", cfg, system, user, images))
        return "VLM"

    monkeypatch.setattr("ozon_common.nvidia.nvidia_chat", fake_chat)
    monkeypatch.setattr("ozon_common.nvidia.nvidia_vlm_chat", fake_vlm)

    settings = {
        "ai_text": {"engine": "nvidia", "api_base": "https://ai.api.nvidia.com", "api_key": "K", "model": "nvidia/text"},
        "ai_multimodal": {"engine": "nvidia", "api_base": "https://ai.api.nvidia.com", "api_key": "K", "model": "google/paligemma"},
    }

    assert text_worker._chat(settings, "S", "U", kind="text") == "TEXT"
    assert text_worker._chat(settings, "S", "U", images=["data:image/png;base64,QQ=="], kind="multimodal") == "VLM"
    assert calls[0][0] == "text"
    assert calls[1][0] == "vlm"


def test_chat_disables_deepseek_thinking(monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(req, timeout=0):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr(text_worker, "urlopen", fake_urlopen)

    settings = {
        "ai_platforms": [{"name": "DeepSeek", "base": "https://api.deepseek.com/v1", "key": "K"}],
        "ai_text": {"platform": "DeepSeek", "model": "deepseek-v4-flash"},
    }

    assert text_worker._chat(settings, "S", "U", kind="text") == "ok"
    assert captured["body"]["thinking"] == {"type": "disabled"}


def test_chat_deepseek_does_not_enable_agnes_thinking_when_engine_is_stale(monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(req, timeout=0):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr(text_worker, "urlopen", fake_urlopen)

    settings = {
        "ai_text": {
            "engine": "agnes",
            "api_base": "https://api.deepseek.com/v1",
            "api_key": "K",
            "model": "deepseek-v4-flash",
        },
    }

    assert text_worker._chat(settings, "S", "U", kind="text") == "ok"
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert "chat_template_kwargs" not in captured["body"]


def test_handle_text_job_retries_when_job_is_not_visible_yet(monkeypatch):
    calls = {"get": 0, "pipeline": 0}
    updates = []
    job = {"id": 98, "draft_id": 1312, "user_id": 1, "status": "queued", "steps_done": ""}

    @contextmanager
    def fake_session_scope():
        yield

    class FakeTextJobRepo:
        def get(self, job_id):
            assert job_id == 98
            calls["get"] += 1
            return None if calls["get"] == 1 else dict(job)

        def update_status(self, job_id, patch):
            assert job_id == 98
            updates.append(dict(patch))
            job.update(patch)
            return dict(job)

    class FakeTaskRunRepo:
        def get_by_external(self, *_args):
            return None

        def upsert_external(self, *_args, **_kwargs):
            return None

    def fake_run_text_pipeline(draft_id, **_kwargs):
        assert draft_id == 1312
        calls["pipeline"] += 1

    monkeypatch.setattr(text_worker, "session_scope", fake_session_scope)
    monkeypatch.setattr(text_worker, "TextJobRepo", FakeTextJobRepo)
    monkeypatch.setattr(text_worker, "TaskRunRepo", FakeTaskRunRepo)
    monkeypatch.setattr(text_worker, "_get_draft", lambda draft_id, user_id=1: {
        "id": draft_id,
        "user_id": user_id,
        "category_id": "1",
        "type_id": "2",
    })
    monkeypatch.setattr(text_worker, "run_text_pipeline", fake_run_text_pipeline)
    monkeypatch.setattr(text_worker.time, "sleep", lambda _seconds: None)

    text_worker.handle_text_job(98, 1312)

    assert calls["get"] == 2
    assert calls["pipeline"] == 1
    assert updates[0] == {"status": "running"}
    assert updates[-1] == {"status": "done", "current_step": "attrs"}
