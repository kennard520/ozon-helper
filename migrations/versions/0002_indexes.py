"""0002 indexes: drafts offer_id/(user_id,status)/ozon_product_id/media_status"""
from alembic import op

revision = "0002_indexes"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

_IDX = [
    ("idx_drafts_offer_id", ["offer_id"]),
    ("idx_drafts_user_status", ["user_id", "status"]),
    ("idx_drafts_ozon_pid", ["ozon_product_id"]),
    ("idx_drafts_media_status", ["media_status"]),
]


def upgrade() -> None:
    from sqlalchemy import inspect, text

    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))} if conn.dialect.name == "sqlite" else {idx["name"] for idx in inspect(conn).get_indexes("drafts")}
    for name, cols in _IDX:
        if name not in existing:
            op.create_index(name, "drafts", cols)


def downgrade() -> None:
    for name, _ in _IDX:
        op.drop_index(name, table_name="drafts")
