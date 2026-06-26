"""验证 worker 将走的仓储路径在 session_scope 下正常工作。

等价于 worker handle_job 的核心 DB 链路：
  create_gen_job → add_draft_image → get_latest_gen_job / load_draft_images
"""
import tempfile
from pathlib import Path

from ozon_common.dal import session as S
from ozon_common.dal.engine import build_engine
from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo
from ozon_common.dal.repositories.gen_job_repo import GenJobRepo
from ozon_common.dal.schema import metadata


def _bind(tmp: str):
    eng = build_engine(f"sqlite:///{Path(tmp) / 'w.db'}")
    metadata.create_all(eng)
    S.bind_engine(eng)
    return eng


def test_worker_repos_basic_path():
    """模拟 worker 写入路径：建 gen_job → 写 draft_image → 读回验证。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            # Step 1: 创建 gen_job（对应 worker 的 create_gen_job 或 update_gen_job）
            with S.session_scope():
                job = GenJobRepo().create_gen_job(draft_id=1, target=10, user_id=1)
            job_id = job["id"]
            assert job["status"] == "queued"
            assert job["draft_id"] == 1

            # Step 2: 写 draft_image（对应 worker _process_one 中 add_draft_image）
            with S.session_scope():
                new_id = DraftImageRepo().add_draft_image(1, "https://example.com/img.jpg", type="白底")
            assert isinstance(new_id, int) and new_id > 0

            # Step 3: 读回验证 gen_job（对应 worker 汇总时 get_latest_gen_job）
            with S.session_scope():
                got_job = GenJobRepo().get_latest_gen_job(draft_id=1, user_id=1)
            assert got_job is not None
            assert got_job["id"] == job_id
            assert got_job["target"] == 10

            # Step 4: 读回 draft_images（验证 add_draft_image 落库）
            with S.session_scope():
                imgs = DraftImageRepo().load_draft_images(1)
            assert len(imgs) == 1
            assert imgs[0]["url"] == "https://example.com/img.jpg"
            assert imgs[0]["type"] == "白底"
            assert imgs[0]["source"] == "generated"

        finally:
            eng.dispose()


def test_worker_gen_job_images_path():
    """模拟 worker 的 create_gen_job_images → get_gen_job_images → set_gen_job_image_status 链路。"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        eng = _bind(tmp)
        try:
            # 建 job
            with S.session_scope():
                job = GenJobRepo().create_gen_job(draft_id=2, target=3, user_id=1)
            job_id = job["id"]

            # 创建图片槽（模拟 worker 的设计阶段）
            slots = [
                {"slot_id": "s1", "label": "白底主图"},
                {"slot_id": "s2", "label": "场景图"},
            ]
            with S.session_scope():
                GenJobRepo().create_gen_job_images(job_id, slots)

            # 读槽位
            with S.session_scope():
                imgs = GenJobRepo().get_gen_job_images(job_id)
            assert len(imgs) == 2
            assert all(i["status"] == "pending" for i in imgs)

            # 模拟单图完成（逐写各自 scope，保持即时可见语义）
            img_id = imgs[0]["id"]
            with S.session_scope():
                GenJobRepo().set_gen_job_image_status(img_id, "done", url="https://oss.example.com/1.png")

            # 读回验证状态即时更新
            with S.session_scope():
                updated = GenJobRepo().get_gen_job_images(job_id)
            assert updated[0]["status"] == "done"
            assert updated[0]["url"] == "https://oss.example.com/1.png"
            assert updated[1]["status"] == "pending"

            # 统计（对应 worker 汇总阶段）
            with S.session_scope():
                counts = GenJobRepo().count_gen_job_images_by_status(job_id)
            assert counts.get("done", 0) == 1
            assert counts.get("pending", 0) == 1

        finally:
            eng.dispose()
