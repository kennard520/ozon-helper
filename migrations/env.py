from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Alembic Config 对象——提供 .ini 文件内容的访问。
config = context.config

# 读取日志配置（仅当有 .ini 文件时）。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 接入 dal.schema 的 metadata，支持 autogenerate。
from ozon_common.dal.schema import metadata  # noqa: E402

target_metadata = metadata


def _get_url() -> str:
    """优先用 config 中注入的 sqlalchemy.url（测试），否则从环境变量读 MySQL。"""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from ozon_common.dal.engine import mysql_url_from_env

    mysql = mysql_url_from_env()
    if mysql:
        return mysql
    raise RuntimeError("alembic: 未提供 sqlalchemy.url 且无 MySQL env")


def run_migrations_offline() -> None:
    """离线模式：仅输出 SQL，不真正连接数据库。"""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：建立真实连接后执行迁移。"""
    url = _get_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
