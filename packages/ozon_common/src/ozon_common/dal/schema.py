"""数据访问层全表 schema(SQLAlchemy Core Table 元数据)。

M1 只如实翻译现有 SQLite/MySQL 表结构,不改类型语义、不加 ForeignKey:
- 钱仍用 Float、时间仍用 Text。
- 列集合以 `webui/store.py` 的 SQLite 最终形态(CREATE + _ensure_column + _migrate_* 重建)
  为准,并与 `ozon_common/db.py` 的 MYSQL_DDL 交叉验证。
正确性由 `apps/webui/tests/test_schema_fidelity.py` 保真 diff 测试守护。
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT

from ozon_common.dal.types import ISODateTime

metadata = MetaData()


def _longtext() -> Text:
    """大 JSON/文本列:MySQL 用 LONGTEXT(普通 TEXT 仅 64KB,装不下目录缓存/抓取原文等),
    SQLite 仍是 TEXT(无大小限制)。对应老库 MYSQL_DDL 里的 longtext 列,保真不缩水。"""
    return Text().with_variant(LONGTEXT(), "mysql")

# 多用户 settings:(user_id, key) 复合主键;user_id=0 为系统级全局。
settings = Table(
    "settings", metadata,
    Column("user_id", Integer, primary_key=True, nullable=False, server_default="0"),
    Column("key", String(255), primary_key=True, nullable=False),
    Column("value", _longtext(), nullable=False),
)

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(191), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(32), nullable=False, server_default="user"),
    Column("status", String(32), nullable=False, server_default="active"),
    Column("created_at", ISODateTime, nullable=False),
    # _ensure_column 追加
    Column("max_stores", Integer, nullable=False, server_default="1"),
)

accounts = Table(
    "accounts", metadata,
    Column(
        "user_id", Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("balance", Numeric(18, 4, asdecimal=True), nullable=False, server_default="0"),
    Column("total_recharge", Numeric(18, 4, asdecimal=True), nullable=False, server_default="0"),
    Column("total_consume", Numeric(18, 4, asdecimal=True), nullable=False, server_default="0"),
    Column("updated_at", ISODateTime),
)

account_txns = Table(
    "account_txns", metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "user_id", Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("txn_type", Text, nullable=False),
    Column("amount", Numeric(18, 4, asdecimal=True), nullable=False),
    Column("balance_after", Numeric(18, 4, asdecimal=True)),
    Column("biz_no", Text),
    Column("remark", Text),
    Column("created_at", ISODateTime, nullable=False),
    Index("idx_txn_user", "user_id"),
)

# drafts 列序按 SQLite 实际形态:CREATE 原始列 + 一连串 _ensure_column 追加列;
# user_id 由 _migrate_drafts_multiuser 重建时前置、store_client_id 由 _migrate_drafts_store_scoped 追加。
# 保真测试只比列名集合,顺序不影响。
drafts = Table(
    "drafts", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, server_default="1"),
    Column("source_platform", String(32), nullable=False, server_default="1688"),
    Column("source_url", String(1024), nullable=False),
    Column("source_offer_id", Text),
    Column("source_title", Text, nullable=False),
    Column("purchase_url", String(1024), nullable=False, server_default=""),
    Column("purchase_note", Text, nullable=True),
    Column("ozon_title", Text, nullable=False),
    Column("description", _longtext(), nullable=False),
    Column("category_id", Text, nullable=False),
    Column("price", Text, nullable=False),
    Column("old_price", Text, nullable=False),
    Column("stock", Integer, nullable=False),
    Column("images_json", _longtext(), nullable=False),
    Column("attributes_json", _longtext(), nullable=False),
    Column("status", String(32), nullable=False),
    Column("validation_errors_json", _longtext(), nullable=False),
    Column("publish_response_json", _longtext()),
    Column("created_at", ISODateTime, nullable=False),
    Column("updated_at", ISODateTime, nullable=False),
    # _ensure_column 追加列
    Column("weight_g", Integer),
    Column("length_mm", Integer),
    Column("width_mm", Integer),
    Column("height_mm", Integer),
    Column("type_id", String(64), nullable=False, server_default=""),
    Column("brand_id", BigInteger),
    Column("brand_name", String(255), nullable=False, server_default=""),
    Column("cost_cny", Numeric(18, 4, asdecimal=True)),
    Column("video_url", Text),
    Column("local_images_json", _longtext()),
    Column("pricing_json", _longtext()),
    Column("source", String(64), nullable=False, server_default=""),
    Column("ozon_product_id", BigInteger),
    Column("offer_id", String(191), nullable=False, server_default=""),
    Column("supplier", String(255), nullable=False, server_default=""),
    Column("warehouse_id", BigInteger),
    Column("source_raw_json", _longtext()),
    Column("ai_proposal_json", _longtext()),
    Column("media_status", String(16), nullable=False, server_default="done"),
    Column("variant_group", String(255), nullable=False, server_default=""),
    # _migrate_drafts_store_scoped 追加
    Column("store_client_id", String(64), nullable=False, server_default=""),
    Index(
        "uq_draft", "user_id", "store_client_id", "source_url",
        unique=True, mysql_length={"source_url": 255},
    ),
    Index("idx_drafts_variant_group", "variant_group"),
    Index("idx_drafts_offer_id", "offer_id"),
    Index("idx_drafts_user_status", "user_id", "status"),
    Index("idx_drafts_ozon_pid", "ozon_product_id"),
    Index("idx_drafts_media_status", "media_status"),
)

commission_map = Table(
    "commission_map", metadata,
    Column("description_category_id", BigInteger, primary_key=True),
    Column("type_id", BigInteger, primary_key=True),
    Column("parent_en", Text),
    Column("sub_en", Text),
    Column("rfbs_json", _longtext()),
    Column("updated_at", ISODateTime),
)

catalog_cache = Table(
    "catalog_cache", metadata,
    Column("language", String(32), primary_key=True),
    Column("leaves_json", _longtext(), nullable=False),
    Column("fetched_at", ISODateTime, nullable=False),
)

catalog_tree_cache = Table(
    "catalog_tree_cache", metadata,
    Column("language", String(32), primary_key=True),
    Column("tree_json", _longtext(), nullable=False),
    Column("fetched_at", ISODateTime, nullable=False),
)

category_attr_values_cache = Table(
    "category_attr_values_cache", metadata,
    Column("description_category_id", BigInteger, primary_key=True),
    Column("type_id", BigInteger, primary_key=True),
    Column("attribute_id", BigInteger, primary_key=True),
    Column("language", String(32), primary_key=True, nullable=False, server_default="RU"),
    Column("values_json", _longtext(), nullable=False),
    Column("oversized", Integer, nullable=False, server_default="0"),
    Column("fetched_at", ISODateTime, nullable=False),
)

attribute_values_cache = Table(
    "attribute_values_cache", metadata,
    Column("description_category_id", BigInteger, primary_key=True),
    Column("type_id", BigInteger, primary_key=True),
    Column("attribute_id", BigInteger, primary_key=True),
    Column("language", String(32), primary_key=True, nullable=False, server_default="ZH_HANS"),
    Column("dictionary_value_id", BigInteger, primary_key=True),
    Column("value", String(1024)),
    Column("info", Text),
    Column("fetched_at", ISODateTime),
    Index(
        "idx_av_cache",
        "description_category_id", "type_id", "attribute_id", "language", "value",
        mysql_length={"value": 100},
    ),
)

category_attr_cache = Table(
    "category_attr_cache", metadata,
    Column("description_category_id", BigInteger, primary_key=True),
    Column("type_id", BigInteger, primary_key=True),
    Column("language", String(32), primary_key=True, nullable=False, server_default="ZH_HANS"),
    Column("attrs_json", _longtext(), nullable=False),
    Column("fetched_at", ISODateTime, nullable=False),
)

warehouses = Table(
    "warehouses", metadata,
    Column("warehouse_id", BigInteger, primary_key=True),
    Column("name", String(255), nullable=False, server_default=""),
    Column("is_rfbs", Integer, nullable=False, server_default="0"),
    Column("status", String(64), nullable=False, server_default=""),
    Column("is_default", Integer, nullable=False, server_default="0"),
    Column("fetched_at", ISODateTime),
    # _ensure_column 追加
    Column("store_client_id", String(64), nullable=False, server_default=""),
)

delivery_methods = Table(
    "delivery_methods", metadata,
    Column("delivery_method_id", BigInteger, primary_key=True),
    Column("warehouse_id", BigInteger),
    Column("name", String(255), nullable=False, server_default=""),
    Column("status", String(64), nullable=False, server_default=""),
    Column("provider_id", BigInteger),
    Column("template_id", BigInteger),
    Column("tpl_integration_type", Text),
    Column("is_express", Integer),
    Column("cutoff", Text),
    Column("sla_cut_in", Integer),
    Column("dropoff_name", Text),
    Column("dropoff_code", Text),
    Column("dropoff_address", Text),
    Column("dropoff_lat", Float),
    Column("dropoff_lng", Float),
    Column("created_at", ISODateTime),
    Column("updated_at", ISODateTime),
    Column("fetched_at", ISODateTime),
    Column("store_client_id", String(64), nullable=False, server_default=""),
    Column("raw_json", _longtext()),
    Index("idx_dm_store_wh", "store_client_id", "warehouse_id"),
)

postings = Table(
    "postings", metadata,
    Column("posting_number", String(128), primary_key=True),
    Column("ozon_order_id", Text),
    Column("status", Text),
    Column("ship_by", Text),
    Column("products_json", _longtext(), nullable=True),
    Column("warehouse_id", BigInteger),
    Column("raw_json", _longtext()),
    Column("synced_at", ISODateTime),
    # _ensure_column 追加
    Column("store_client_id", String(64), nullable=False, server_default=""),
)

procurement = Table(
    "procurement", metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "posting_number", String(128),
        ForeignKey("postings.posting_number", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("offer_id", String(191), nullable=False),
    Column("qty", Integer, nullable=False, server_default="1"),
    Column("purchase_state", String(32), nullable=False, server_default="待采购"),
    Column("supplier", String(255), nullable=False, server_default=""),
    Column("purchase_url", String(1024), nullable=False, server_default=""),
    Column("cost_cny", Numeric(18, 4, asdecimal=True)),
    Column("note", Text, nullable=True),
    Column("updated_at", ISODateTime),
    # _ensure_column 追加
    Column("store_client_id", String(64), nullable=False, server_default=""),
    UniqueConstraint("posting_number", "offer_id"),
)

offer_snapshots = Table(
    "offer_snapshots", metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", String(191), nullable=False),
    Column("sku", Text),
    Column("captured_at", ISODateTime, nullable=False),
    Column("follow_count", Integer),
    Column("price_min", Numeric(18, 4, asdecimal=True)),
    Column("price_max", Numeric(18, 4, asdecimal=True)),
    Column("sellers_json", _longtext()),
    # _ensure_column 追加
    Column("store_client_id", String(64), nullable=False, server_default=""),
    Index("idx_offer_snap_pid", "product_id"),
)

draft_images = Table(
    "draft_images", metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "draft_id", Integer,
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("url", Text, nullable=False),
    Column("type", String(32), nullable=False, server_default=""),
    Column("source", String(32), nullable=False, server_default="collected"),
    Column("in_gallery", Integer, nullable=False, server_default="1"),
    Column("local_url", String(1024), nullable=False, server_default=""),
    Column("created_at", ISODateTime, nullable=False),
    Index("idx_dimg_draft", "draft_id", "position"),
)

gen_jobs = Table(
    "gen_jobs", metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "draft_id", Integer,
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("user_id", Integer, nullable=False, server_default="1"),
    Column("status", String(16), nullable=False, server_default="queued"),
    Column("target", Integer, nullable=False, server_default="10"),
    Column("total", Integer, nullable=False, server_default="0"),
    Column("succeeded", Integer, nullable=False, server_default="0"),
    Column("failed", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Column("created_at", ISODateTime, nullable=False),
    Column("updated_at", ISODateTime, nullable=False),
    Index("idx_gen_jobs_draft", "user_id", "draft_id"),
)

text_jobs = Table(
    "text_jobs", metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "draft_id", Integer,
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("user_id", Integer, nullable=False, server_default="1"),
    Column("status", String(16), nullable=False, server_default="queued"),
    Column("current_step", String(32)),
    Column("steps_done", Text),
    Column("error", Text),
    Column("created_at", ISODateTime, nullable=False),
    Column("updated_at", ISODateTime, nullable=False),
    Index("idx_text_jobs_draft", "user_id", "draft_id"),
)

gen_job_images = Table(
    "gen_job_images", metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "job_id", Integer,
        ForeignKey("gen_jobs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("slot_id", String(64), nullable=False, server_default=""),
    Column("label", String(255), nullable=False, server_default=""),
    Column("status", String(16), nullable=False, server_default="pending"),
    Column("url", Text),
    Column("error", Text),
    Column("updated_at", ISODateTime, nullable=False),
    Index("idx_gen_job_images_job", "job_id"),
)
