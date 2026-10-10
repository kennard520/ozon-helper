"""task_runs: unified task index for workbench pipeline

Revision ID: 0009_task_runs
Revises: 0008_text_jobs
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

from ozon_common.dal.types import ISODateTime

revision = "0009_task_runs"
down_revision = "0008_text_jobs"
branch_labels = None
depends_on = None


def _longtext() -> sa.Text:
    return sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("draft_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_json", _longtext(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default=""),
        sa.Column("external_id", sa.String(64), nullable=True),
        sa.Column("created_at", ISODateTime(), nullable=False),
        sa.Column("updated_at", ISODateTime(), nullable=False),
        sa.Column("started_at", ISODateTime(), nullable=True),
        sa.Column("finished_at", ISODateTime(), nullable=True),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_task_runs_draft", "task_runs", ["user_id", "draft_id"])
    op.create_index("idx_task_runs_external", "task_runs", ["task_type", "source", "external_id"])
    op.create_index("idx_task_runs_status", "task_runs", ["user_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.drop_index("idx_task_runs_status", table_name="task_runs")
    op.drop_index("idx_task_runs_external", table_name="task_runs")
    op.drop_index("idx_task_runs_draft", table_name="task_runs")
    op.drop_table("task_runs")
