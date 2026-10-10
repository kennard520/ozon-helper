"""0003 money: Float -> Numeric(18,4)"""
import sqlalchemy as sa
from alembic import op

revision = "0003_money"
down_revision = "0002_indexes"
branch_labels = None
depends_on = None

_COLS = [
    ("accounts", "balance"), ("accounts", "total_recharge"), ("accounts", "total_consume"),
    ("account_txns", "amount"), ("account_txns", "balance_after"),
    ("drafts", "cost_cny"),
    ("offer_snapshots", "price_min"), ("offer_snapshots", "price_max"),
    ("procurement", "cost_cny"),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return  # SQLite 测试走 create_all;SQLite ALTER 类型受限,跳过
    for t, c in _COLS:
        op.alter_column(t, c, type_=sa.Numeric(18, 4), existing_type=sa.Float())


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    for t, c in _COLS:
        op.alter_column(t, c, type_=sa.Float(), existing_type=sa.Numeric(18, 4))
