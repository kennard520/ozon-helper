from contextlib import contextmanager

from image_worker import worker


def test_gen_task_cancelled_opens_session_scope(monkeypatch):
    entered = []

    @contextmanager
    def fake_session_scope():
        entered.append(True)
        yield

    class FakeTaskRunRepo:
        def get_by_external(self, domain, external_table, external_id):
            assert entered
            assert (domain, external_table, external_id) == ("ai_image", "gen_jobs", 42)
            return {"status": "cancel_requested"}

    monkeypatch.setattr(worker, "session_scope", fake_session_scope)
    monkeypatch.setattr(worker, "TaskRunRepo", FakeTaskRunRepo)

    assert worker._gen_task_cancelled(42) is True
    assert entered == [True]
