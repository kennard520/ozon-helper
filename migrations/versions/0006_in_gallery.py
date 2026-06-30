"""0006 draft_images.in_gallery 两池标记

Revision ID: 0006_in_gallery
Revises: 0005_fk
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_in_gallery"
down_revision = "0005_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 走 baseline create_all,已含该列,跳过
    op.add_column(
        "draft_images",
        sa.Column("in_gallery", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.drop_column("draft_images", "in_gallery")
