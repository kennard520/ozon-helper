"""协存冒烟:Store 裸连接 + dal 仓储池连接对同一 SQLite 文件共存(WAL)。"""
import tempfile
from pathlib import Path


def test_legacy_store_and_repo_coexist():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Path(tmp) / "co.db"
        import webui.store as store_mod
        store_mod.DEFAULT_DB = db
        st = store_mod.Store(db)   # Store.init() 建表 + bind_engine(WAL)
        try:
            # 经 Store(已转调仓储)写 settings —— 走池连接、自开 session、commit
            st.save_settings({"oss_bucket": "co-bucket"}, user_id=1)
            # 经 Store 读 settings(也走仓储)—— 应读回
            assert st.get_settings(1).get("oss_bucket") == "co-bucket"
            # 经 Store 裸连接路径写一条 draft(未转调,走 self.conn)
            from webui.drafts import create_draft_from_url
            draft_data = create_draft_from_url("https://detail.1688.com/offer/111122223333.html")
            d = st.insert_draft(draft_data)
            assert d["id"] >= 1
            # 再经仓储写该 draft 的图(走池连接),不死锁、可读回
            img_id = st.add_draft_image(d["id"], "http://x/1.jpg", type="白底")
            assert isinstance(img_id, int)
            # 裸连接读 draft_images 应看到(commit 后跨连接可见)
            got = st.get_draft(d["id"])
            assert got is not None
            assert "http://x/1.jpg" in got["images"]
        finally:
            st.close()
