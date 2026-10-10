"""text_jobs: 文本生成 MQ 异步任务状态表

Revision ID: 0008_text_jobs
Revises: 0007_draft_image_local_url
"""
import sqlalchemy as sa
from alembic import op

from ozon_common.dal.types import ISODateTime

revision = "0008_text_jobs"
down_revision = "0007_draft_image_local_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 走 baseline create_all（已含本表），跳过
    op.create_table(
        "text_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(32), nullable=True),
        sa.Column("steps_done", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", ISODateTime(), nullable=False),
        sa.Column("updated_at", ISODateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["drafts.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("idx_text_jobs_draft", "text_jobs", ["user_id", "draft_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.drop_index("idx_text_jobs_draft", table_name="text_jobs")
    op.drop_table("text_jobs")
