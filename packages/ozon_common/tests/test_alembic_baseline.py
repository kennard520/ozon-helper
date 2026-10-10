import sqlite3
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_baseline_upgrade_creates_tables():
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "a.db")
        cfg = Config()
        cfg.set_main_option("script_location", "migrations")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
        command.upgrade(cfg, "head")
        con = sqlite3.connect(db)
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert {"settings", "drafts", "gen_jobs", "draft_images", "users"} <= names
