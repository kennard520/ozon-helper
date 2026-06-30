"""0005 fk: 6 条外键 ON DELETE CASCADE(先清孤儿,再加 FK)。

让 DB 级联替代手写删子表(M4d)。6 条 FK:
  draft_images.draft_id    -> drafts.id
  gen_jobs.draft_id        -> drafts.id
  gen_job_images.job_id    -> gen_jobs.id
  accounts.user_id         -> users.id
  account_txns.user_id     -> users.id
  procurement.posting_number -> postings.posting_number

MySQL 路径:加 FK 前若子表存在父键缺失的孤儿行,ADD CONSTRAINT 会报错,故先
LEFT JOIN 清孤儿。清理前对每张子表 SELECT COUNT 将删行数并 print,避免静默删大量数据。

⚠️ 孤儿清理 + FK 添加需在真实 MySQL 上演练验证(本迁移仅 MySQL 生效)。
SQLite 测试走 create_all + PRAGMA foreign_keys=ON(engine 已开),不经此迁移,直接 return。
"""
from alembic import op
from sqlalchemy import text

revision = "0005_fk"
down_revision = "0004_timestamps"
branch_labels = None
depends_on = None

# (约束名, 子表, 子键, 父表, 父键)
_FKS = [
    ("fk_dimg_draft", "draft_images", "draft_id", "drafts", "id"),
    ("fk_genjobs_draft", "gen_jobs", "draft_id", "drafts", "id"),
    ("fk_genjobimg_job", "gen_job_images", "job_id", "gen_jobs", "id"),
    ("fk_accounts_user", "accounts", "user_id", "users", "id"),
    ("fk_acctxns_user", "account_txns", "user_id", "users", "id"),
    ("fk_proc_posting", "procurement", "posting_number", "postings", "posting_number"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 测试走 create_all + PRAGMA,不经此迁移

    # 1) 清孤儿:逐子表先统计将删行数(print),再 LEFT JOIN 删除。
    for _name, child, ckey, parent, pkey in _FKS:
        n = bind.execute(
            text(
                f"SELECT COUNT(*) FROM `{child}` c "
                f"LEFT JOIN `{parent}` p ON c.`{ckey}` = p.`{pkey}` "
                f"WHERE p.`{pkey}` IS NULL"
            )
        ).scalar()
        n = int(n or 0)
        print(f"[0005_fk] {child}.{ckey} 孤儿行将删: {n}")
        if n:
            op.execute(
                f"DELETE c FROM `{child}` c "
                f"LEFT JOIN `{parent}` p ON c.`{ckey}` = p.`{pkey}` "
                f"WHERE p.`{pkey}` IS NULL"
            )

    # 2) 加 6 条 FK(ON DELETE CASCADE)。
    for name, child, ckey, parent, pkey in _FKS:
        op.create_foreign_key(
            name, child, parent, [ckey], [pkey], ondelete="CASCADE"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    for name, child, _ckey, _parent, _pkey in _FKS:
        op.drop_constraint(name, child, type_="foreignkey")
