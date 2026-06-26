"""GenJobRepo 单测 — 覆盖 12 个方法的核心路径。

测试模式参照 test_settings_repo.py:
  - 每个 test_* 函数独立 SQLite 临时库
  - try/finally: eng.dispose() 保证 Windows 文件句柄释放
"""
import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.gen_job_repo import GenJobRepo
from ozon_common.dal.schema import metadata


def _bind(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'g.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


# ---------------------------------------------------------------------------
# create / get / get_latest / list / has_active
# ---------------------------------------------------------------------------

def test_create_and_get():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                job = repo.create_gen_job(draft_id=1, target=5, user_id=2)
                assert job is not None
                assert job["draft_id"] == 1
                assert job["target"] == 5
                assert job["user_id"] == 2
                assert job["status"] == "queued"
                assert job["total"] == 0
                assert job["succeeded"] == 0
                assert job["failed"] == 0
                assert "id" in job
                assert "created_at" in job
                assert "updated_at" in job

                fetched = repo.get_gen_job(job["id"])
                assert fetched == job
        finally:
            eng.dispose()


def test_get_nonexistent_returns_none():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                assert GenJobRepo().get_gen_job(9999) is None
        finally:
            eng.dispose()


def test_get_latest_gen_job():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j1 = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                j2 = repo.create_gen_job(draft_id=1, target=7, user_id=1)

                latest = repo.get_latest_gen_job(draft_id=1, user_id=1)
                assert latest is not None
                assert latest["id"] == j2["id"]  # 最新的是 j2

                # 不同 user_id 不应该出现
                assert repo.get_latest_gen_job(draft_id=1, user_id=99) is None
        finally:
            eng.dispose()


def test_list_gen_jobs():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j1 = repo.create_gen_job(draft_id=10, target=3, user_id=1)
                j2 = repo.create_gen_job(draft_id=10, target=5, user_id=1)
                # 其他 draft_id 不应混入
                repo.create_gen_job(draft_id=99, target=1, user_id=1)

                jobs = repo.list_gen_jobs(draft_id=10, user_id=1)
                assert len(jobs) == 2
                # id 降序
                assert jobs[0]["id"] == j2["id"]
                assert jobs[1]["id"] == j1["id"]
        finally:
            eng.dispose()


def test_has_active_gen_job_true():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                repo.create_gen_job(draft_id=1, target=3, user_id=1)  # status=queued
                assert repo.has_active_gen_job(draft_id=1, user_id=1) is True
        finally:
            eng.dispose()


def test_has_active_gen_job_false_after_done():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                repo.set_gen_job_status(j["id"], "done")
                assert repo.has_active_gen_job(draft_id=1, user_id=1) is False
        finally:
            eng.dispose()


def test_has_active_gen_job_false_after_failed():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                repo.set_gen_job_status(j["id"], "failed")
                assert repo.has_active_gen_job(draft_id=1, user_id=1) is False
        finally:
            eng.dispose()


def test_has_active_gen_job_designing():
    """status=designing 也属于 active。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                repo.set_gen_job_status(j["id"], "designing")
                assert repo.has_active_gen_job(draft_id=1, user_id=1) is True
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# update_gen_job / set_gen_job_status
# ---------------------------------------------------------------------------

def test_update_gen_job():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                updated = repo.update_gen_job(j["id"], {"succeeded": 3, "total": 5})
                assert updated is not None
                assert updated["succeeded"] == 3
                assert updated["total"] == 5
                # id 不变
                assert updated["id"] == j["id"]
        finally:
            eng.dispose()


def test_update_gen_job_empty_patch():
    """空 patch(只有 id)应直接返回当前行。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                result = repo.update_gen_job(j["id"], {"id": j["id"]})
                assert result is not None
                assert result["id"] == j["id"]
        finally:
            eng.dispose()


def test_set_gen_job_status():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                repo.set_gen_job_status(j["id"], "running")
                updated = repo.get_gen_job(j["id"])
                assert updated["status"] == "running"
        finally:
            eng.dispose()


# ---------------------------------------------------------------------------
# create_gen_job_images / get_gen_job_images / update_gen_job_image /
# set_gen_job_image_status / count_gen_job_images_by_status
# ---------------------------------------------------------------------------

def test_create_and_get_gen_job_images():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                slots = [
                    {"slot_id": "main", "label": "主图"},
                    {"slot_id": "info1", "label": "信息图1"},
                    {"slot_id": "info2", "label": "信息图2"},
                ]
                repo.create_gen_job_images(j["id"], slots)

                images = repo.get_gen_job_images(j["id"])
                assert len(images) == 3
                # id 升序
                assert images[0]["slot_id"] == "main"
                assert images[0]["label"] == "主图"
                assert images[0]["status"] == "pending"
                assert images[0]["url"] is None
                assert images[0]["error"] is None
                assert "id" in images[0]
                assert "updated_at" in images[0]
        finally:
            eng.dispose()


def test_update_gen_job_image():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=2, user_id=1)
                repo.create_gen_job_images(j["id"], [{"slot_id": "s1", "label": "L1"}])
                images = repo.get_gen_job_images(j["id"])
                img_id = images[0]["id"]

                # update_gen_job_image 无返回值
                repo.update_gen_job_image(img_id, {"status": "running", "url": "http://x"})
                imgs2 = repo.get_gen_job_images(j["id"])
                assert imgs2[0]["status"] == "running"
                assert imgs2[0]["url"] == "http://x"
        finally:
            eng.dispose()


def test_update_gen_job_image_empty_patch():
    """空 patch 不报错。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=2, user_id=1)
                repo.create_gen_job_images(j["id"], [{"slot_id": "s1", "label": "L1"}])
                images = repo.get_gen_job_images(j["id"])
                img_id = images[0]["id"]
                # 不应抛出
                repo.update_gen_job_image(img_id, {})
                repo.update_gen_job_image(img_id, {"id": img_id})
        finally:
            eng.dispose()


def test_set_gen_job_image_status_done():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=2, user_id=1)
                repo.create_gen_job_images(
                    j["id"],
                    [{"slot_id": "main", "label": "主图"}, {"slot_id": "s2", "label": "副图"}],
                )
                images = repo.get_gen_job_images(j["id"])
                img_id = images[0]["id"]

                repo.set_gen_job_image_status(img_id, "done", url="https://oss/a.jpg")
                imgs2 = repo.get_gen_job_images(j["id"])
                assert imgs2[0]["status"] == "done"
                assert imgs2[0]["url"] == "https://oss/a.jpg"
                assert imgs2[0]["error"] is None
        finally:
            eng.dispose()


def test_set_gen_job_image_status_failed():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=2, user_id=1)
                repo.create_gen_job_images(j["id"], [{"slot_id": "s1", "label": "L"}])
                images = repo.get_gen_job_images(j["id"])
                img_id = images[0]["id"]

                repo.set_gen_job_image_status(img_id, "failed", error="timeout")
                imgs2 = repo.get_gen_job_images(j["id"])
                assert imgs2[0]["status"] == "failed"
                assert imgs2[0]["url"] is None
                assert imgs2[0]["error"] == "timeout"
        finally:
            eng.dispose()


def test_count_gen_job_images_by_status():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                slots = [
                    {"slot_id": "s1", "label": "L1"},
                    {"slot_id": "s2", "label": "L2"},
                    {"slot_id": "s3", "label": "L3"},
                ]
                repo.create_gen_job_images(j["id"], slots)
                images = repo.get_gen_job_images(j["id"])

                # 设第一张 done,第二张 failed,第三张保持 pending
                repo.set_gen_job_image_status(images[0]["id"], "done", url="https://u1")
                repo.set_gen_job_image_status(images[1]["id"], "failed", error="err")

                counts = repo.count_gen_job_images_by_status(j["id"])
                assert counts == {"done": 1, "failed": 1, "pending": 1}
        finally:
            eng.dispose()


def test_count_empty_job():
    """没有图片时返回空字典。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=1, target=3, user_id=1)
                assert repo.count_gen_job_images_by_status(j["id"]) == {}
        finally:
            eng.dispose()


def test_user_id_none_defaults_to_1():
    """user_id=None 应等同于 user_id=1。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            with S.session_scope():
                repo = GenJobRepo()
                j = repo.create_gen_job(draft_id=5, target=2)  # user_id=None
                assert j["user_id"] == 1

                latest = repo.get_latest_gen_job(draft_id=5)  # user_id=None
                assert latest is not None
                assert latest["id"] == j["id"]

                jobs = repo.list_gen_jobs(draft_id=5)  # user_id=None
                assert len(jobs) == 1

                assert repo.has_active_gen_job(draft_id=5) is True
        finally:
            eng.dispose()
