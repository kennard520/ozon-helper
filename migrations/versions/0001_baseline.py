"""baseline: 从 dal.schema metadata 建全部表(当前最终 schema)。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-27
"""

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from ozon_common.dal.schema import metadata

    metadata.create_all(op.get_bind())


def downgrade() -> None:
    from ozon_common.dal.schema import metadata

    metadata.drop_all(op.get_bind())
