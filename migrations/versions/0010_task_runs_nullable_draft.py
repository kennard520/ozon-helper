"""allow global task_runs without a draft

Revision ID: 0010_task_runs_nullable_draft
Revises: 0009_task_runs
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_task_runs_nullable_draft"
down_revision = "0009_task_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column("task_runs", "draft_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.alter_column("task_runs", "draft_id", existing_type=sa.Integer(), nullable=False)
