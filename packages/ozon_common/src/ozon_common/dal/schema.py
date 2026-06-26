"""数据访问层全表 schema(SQLAlchemy Core Table 元数据)。

M1 只如实翻译现有 SQLite/MySQL 表结构,不改类型语义、不加 ForeignKey:
- 钱仍用 Float、时间仍用 Text。
- 列集合以 `webui/store.py` 的 SQLite 最终形态(CREATE + _ensure_column + _migrate_* 重建)
  为准,并与 `ozon_common/db.py` 的 MYSQL_DDL 交叉验证。
正确性由 `apps/webui/tests/test_schema_fidelity.py` 保真 diff 测试守护。
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

# 多用户 settings:(user_id, key) 复合主键;user_id=0 为系统级全局。
settings = Table(
    "settings", metadata,
    Column("user_id", Integer, primary_key=True, nullable=False, server_default="0"),
    Column("key", String(255), primary_key=True, nullable=False),
    Column("value", Text, nullable=False),
)

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", Text, nullable=False, server_default="user"),
    Column("status", Text, nullable=False, server_default="active"),
    Column("created_at", Text, nullable=False),
    # _ensure_column 追加
    Column("max_stores", Integer, nullable=False, server_default="1"),
)

accounts = Table(
    "accounts", metadata,
    Column("user_id", Integer, primary_key=True),
    Column("balance", Float, nullable=False, server_default="0"),
    Column("total_recharge", Float, nullable=False, server_default="0"),
    Column("total_consume", Float, nullable=False, server_default="0"),
    Column("updated_at", Text),
)

account_txns = Table(
    "account_txns", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False),
    Column("txn_type", Text, nullable=False),
    Column("amount", Float, nullable=False),
    Column("balance_after", Float),
    Column("biz_no", Text),
    Column("remark", Text),
    Column("created_at", Text, nullable=False),
    Index("idx_txn_user", "user_id"),
)

# drafts 列序按 SQLite 实际形态:CREATE 原始列 + 一连串 _ensure_column 追加列;
# user_id 由 _migrate_drafts_multiuser 重建时前置、store_client_id 由 _migrate_drafts_store_scoped 追加。
# 保真测试只比列名集合,顺序不影响。
drafts = Table(
    "drafts", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, nullable=False, server_default="1"),
    Column("source_platform", Text, nullable=False, server_default="1688"),
    Column("source_url", Text, nullable=False),
    Column("source_offer_id", Text),
    Column("source_title", Text, nullable=False),
    Column("purchase_url", Text, nullable=False, server_default=""),
    Column("purchase_note", Text, nullable=False, server_default=""),
    Column("ozon_title", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("category_id", Text, nullable=False),
    Column("price", Text, nullable=False),
    Column("old_price", Text, nullable=False),
    Column("stock", Integer, nullable=False),
    Column("images_json", Text, nullable=False),
    Column("attributes_json", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("validation_errors_json", Text, nullable=False),
    Column("publish_response_json", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    # _ensure_column 追加列
    Column("weight_g", Integer),
    Column("length_mm", Integer),
    Column("width_mm", Integer),
    Column("height_mm", Integer),
    Column("type_id", Text, nullable=False, server_default=""),
    Column("brand_id", Integer),
    Column("brand_name", Text, nullable=False, server_default=""),
    Column("cost_cny", Float),
    Column("video_url", Text),
    Column("local_images_json", Text),
    Column("pricing_json", Text),
    Column("source", Text, nullable=False, server_default=""),
    Column("ozon_product_id", Integer),
    Column("offer_id", Text, nullable=False, server_default=""),
    Column("supplier", Text, nullable=False, server_default=""),
    Column("warehouse_id", Integer),
    Column("source_raw_json", Text),
    Column("ai_proposal_json", Text),
    Column("media_status", Text, nullable=False, server_default="done"),
    Column("variant_group", Text, nullable=False, server_default=""),
    # _migrate_drafts_store_scoped 追加
    Column("store_client_id", Text, nullable=False, server_default=""),
    UniqueConstraint("user_id", "store_client_id", "source_url"),
    Index("idx_drafts_variant_group", "variant_group"),
)

commission_map = Table(
    "commission_map", metadata,
    Column("description_category_id", Integer, primary_key=True),
    Column("type_id", Integer, primary_key=True),
    Column("parent_en", Text),
    Column("sub_en", Text),
    Column("rfbs_json", Text),
    Column("updated_at", Text),
)

catalog_cache = Table(
    "catalog_cache", metadata,
    Column("language", Text, primary_key=True),
    Column("leaves_json", Text, nullable=False),
    Column("fetched_at", Text, nullable=False),
)

catalog_tree_cache = Table(
    "catalog_tree_cache", metadata,
    Column("language", Text, primary_key=True),
    Column("tree_json", Text, nullable=False),
    Column("fetched_at", Text, nullable=False),
)

category_attr_values_cache = Table(
    "category_attr_values_cache", metadata,
    Column("description_category_id", Integer, primary_key=True),
    Column("type_id", Integer, primary_key=True),
    Column("attribute_id", Integer, primary_key=True),
    Column("language", Text, primary_key=True, nullable=False, server_default="RU"),
    Column("values_json", Text, nullable=False),
    Column("oversized", Integer, nullable=False, server_default="0"),
    Column("fetched_at", Text, nullable=False),
)

attribute_values_cache = Table(
    "attribute_values_cache", metadata,
    Column("description_category_id", Integer, primary_key=True),
    Column("type_id", Integer, primary_key=True),
    Column("attribute_id", Integer, primary_key=True),
    Column("language", Text, primary_key=True, nullable=False, server_default="ZH_HANS"),
    Column("dictionary_value_id", Integer, primary_key=True),
    Column("value", Text),
    Column("info", Text),
    Column("fetched_at", Text),
    Index(
        "idx_av_cache",
        "description_category_id", "type_id", "attribute_id", "language", "value",
    ),
)

category_attr_cache = Table(
    "category_attr_cache", metadata,
    Column("description_category_id", Integer, primary_key=True),
    Column("type_id", Integer, primary_key=True),
    Column("language", Text, primary_key=True, nullable=False, server_default="ZH_HANS"),
    Column("attrs_json", Text, nullable=False),
    Column("fetched_at", Text, nullable=False),
)

warehouses = Table(
    "warehouses", metadata,
    Column("warehouse_id", Integer, primary_key=True),
    Column("name", Text, nullable=False, server_default=""),
    Column("is_rfbs", Integer, nullable=False, server_default="0"),
    Column("status", Text, nullable=False, server_default=""),
    Column("is_default", Integer, nullable=False, server_default="0"),
    Column("fetched_at", Text),
    # _ensure_column 追加
    Column("store_client_id", Text, nullable=False, server_default=""),
)

delivery_methods = Table(
    "delivery_methods", metadata,
    Column("delivery_method_id", Integer, primary_key=True),
    Column("warehouse_id", Integer),
    Column("name", Text, nullable=False, server_default=""),
    Column("status", Text, nullable=False, server_default=""),
    Column("provider_id", Integer),
    Column("template_id", Integer),
    Column("tpl_integration_type", Text),
    Column("is_express", Integer),
    Column("cutoff", Text),
    Column("sla_cut_in", Integer),
    Column("dropoff_name", Text),
    Column("dropoff_code", Text),
    Column("dropoff_address", Text),
    Column("dropoff_lat", Float),
    Column("dropoff_lng", Float),
    Column("created_at", Text),
    Column("updated_at", Text),
    Column("fetched_at", Text),
    Column("store_client_id", Text, nullable=False, server_default=""),
    Column("raw_json", Text),
    Index("idx_dm_store_wh", "store_client_id", "warehouse_id"),
)

postings = Table(
    "postings", metadata,
    Column("posting_number", Text, primary_key=True),
    Column("ozon_order_id", Text),
    Column("status", Text),
    Column("ship_by", Text),
    Column("products_json", Text, nullable=False, server_default="[]"),
    Column("warehouse_id", Integer),
    Column("raw_json", Text),
    Column("synced_at", Text),
    # _ensure_column 追加
    Column("store_client_id", Text, nullable=False, server_default=""),
)

procurement = Table(
    "procurement", metadata,
    Column("id", Integer, primary_key=True),
    Column("posting_number", Text, nullable=False),
    Column("offer_id", Text, nullable=False),
    Column("qty", Integer, nullable=False, server_default="1"),
    Column("purchase_state", Text, nullable=False, server_default="待采购"),
    Column("supplier", Text, nullable=False, server_default=""),
    Column("purchase_url", Text, nullable=False, server_default=""),
    Column("cost_cny", Float),
    Column("note", Text, nullable=False, server_default=""),
    Column("updated_at", Text),
    # _ensure_column 追加
    Column("store_client_id", Text, nullable=False, server_default=""),
    UniqueConstraint("posting_number", "offer_id"),
)

offer_snapshots = Table(
    "offer_snapshots", metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Text, nullable=False),
    Column("sku", Text),
    Column("captured_at", Text, nullable=False),
    Column("follow_count", Integer),
    Column("price_min", Float),
    Column("price_max", Float),
    Column("sellers_json", Text),
    # _ensure_column 追加
    Column("store_client_id", Text, nullable=False, server_default=""),
    Index("idx_offer_snap_pid", "product_id"),
)

draft_images = Table(
    "draft_images", metadata,
    Column("id", Integer, primary_key=True),
    Column("draft_id", Integer, nullable=False),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("url", Text, nullable=False),
    Column("type", Text, nullable=False, server_default=""),
    Column("source", Text, nullable=False, server_default="collected"),
    Column("created_at", Text, nullable=False),
    Index("idx_dimg_draft", "draft_id", "position"),
)

gen_jobs = Table(
    "gen_jobs", metadata,
    Column("id", Integer, primary_key=True),
    Column("draft_id", Integer, nullable=False),
    Column("user_id", Integer, nullable=False, server_default="1"),
    Column("status", Text, nullable=False, server_default="queued"),
    Column("target", Integer, nullable=False, server_default="10"),
    Column("total", Integer, nullable=False, server_default="0"),
    Column("succeeded", Integer, nullable=False, server_default="0"),
    Column("failed", Integer, nullable=False, server_default="0"),
    Column("error", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_gen_jobs_draft", "user_id", "draft_id"),
)

gen_job_images = Table(
    "gen_job_images", metadata,
    Column("id", Integer, primary_key=True),
    Column("job_id", Integer, nullable=False),
    Column("slot_id", Text, nullable=False, server_default=""),
    Column("label", Text, nullable=False, server_default=""),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("url", Text),
    Column("error", Text),
    Column("updated_at", Text, nullable=False),
    Index("idx_gen_job_images_job", "job_id"),
)
