"""0004 timestamps: TEXT(ISO) -> DATETIME(6)

把 22 个时间列从存 ISO 文本改为原生 DATETIME(6)。
对外仍是 ISO 字符串(由 ISODateTime TypeDecorator 在类型层透明转换),仓储/应用代码零改动。

⚠️ MySQL 数据转换是本阶段最易错处:必须在真实 MySQL 上演练验证(STR_TO_DATE 解析、空串置 NULL、列类型 ALTER)。
SQLite 测试走 create_all,SQLite ALTER 类型受限,直接跳过。
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime

revision = "0004_timestamps"
down_revision = "0003_money"
branch_labels = None
depends_on = None

# 全部 22 个时间列(表, 列)—— 与 schema.py 一致。
_COLS = [
    ("users", "created_at"),
    ("accounts", "updated_at"),
    ("account_txns", "created_at"),
    ("drafts", "created_at"),
    ("drafts", "updated_at"),
    ("commission_map", "updated_at"),
    ("catalog_cache", "fetched_at"),
    ("catalog_tree_cache", "fetched_at"),
    ("category_attr_values_cache", "fetched_at"),
    ("attribute_values_cache", "fetched_at"),
    ("category_attr_cache", "fetched_at"),
    ("warehouses", "fetched_at"),
    ("delivery_methods", "created_at"),
    ("delivery_methods", "updated_at"),
    ("delivery_methods", "fetched_at"),
    ("postings", "synced_at"),
    ("procurement", "updated_at"),
    ("offer_snapshots", "captured_at"),
    ("draft_images", "created_at"),
    ("gen_jobs", "created_at"),
    ("gen_jobs", "updated_at"),
    ("gen_job_images", "updated_at"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 测试走 create_all
    for t, c in _COLS:
        # 1) 把 ISO 文本规整成 MySQL DATETIME 可解析:裁掉时区(取 '+' 前)、'T'->空格;空串置 NULL。
        op.execute(
            f"UPDATE `{t}` SET `{c}` = "
            f"STR_TO_DATE(REPLACE(SUBSTRING_INDEX(`{c}`, '+', 1), 'T', ' '), '%Y-%m-%d %H:%i:%s.%f') "
            f"WHERE `{c}` IS NOT NULL AND `{c}` <> ''"
        )
        op.execute(f"UPDATE `{t}` SET `{c}` = NULL WHERE `{c}` = ''")
        # 2) 改列类型 -> DATETIME(6)
        op.alter_column(t, c, type_=MySQLDateTime(fsp=6), existing_type=sa.Text())


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    for t, c in _COLS:
        op.alter_column(t, c, type_=sa.Text(), existing_type=MySQLDateTime(fsp=6))
