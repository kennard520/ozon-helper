"""draft_images.local_url

Revision ID: 0007_draft_image_local_url
Revises: 0006_in_gallery
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_draft_image_local_url"
down_revision = "0006_in_gallery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 走 baseline create_all,已含该列,跳过
    op.add_column(
        "draft_images",
        sa.Column("local_url", sa.String(1024), nullable=False, server_default=""),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.drop_column("draft_images", "local_url")
