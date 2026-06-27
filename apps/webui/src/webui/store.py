from __future__ import annotations

import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("ozon.app")
from webui.drafts import dumps_json, loads_json, utc_now_iso, validate_draft

# 当前请求的用户 ID（多用户隔离）。HTTP 中间件按 JWT 设置；非请求上下文(测试/启动)默认 1(admin)。
# store 方法 user_id 传 None 时读这里——让 App 各方法无需逐个加 user_id 参数就自动按当前用户隔离。
current_user_id: ContextVar[int] = ContextVar("current_user_id", default=1)


def _uid(user_id: int | None) -> int:
    return int(current_user_id.get() if user_id is None else user_id)


def _in_scope(fn):
    """在请求级 session 内执行 fn：已有 ambient session 直接用，否则自开一个。

    让 Store 转调仓储的方法既能跑在 HTTP 中间件 session 里，也能在请求外
    （测试/启动/worker 无中间件）自开 session 兜底。"""
    from ozon_common.dal.session import _current_session, session_scope  # noqa: PLC0415
    if _current_session.get() is not None:
        return fn()
    with session_scope():
        return fn()


def _gen_job_repo():
    """延迟构造 GenJobRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.gen_job_repo import GenJobRepo  # noqa: PLC0415
    return GenJobRepo()


def _catalog_cache_repo():
    """延迟构造 CatalogCacheRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.catalog_cache_repo import CatalogCacheRepo  # noqa: PLC0415
    return CatalogCacheRepo()


def _commission_repo():
    """延迟构造 CommissionRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.commission_repo import CommissionRepo  # noqa: PLC0415
    return CommissionRepo()


def _user_repo():
    """延迟构造 UserRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.user_repo import UserRepo  # noqa: PLC0415
    return UserRepo()


def _wallet_repo():
    """延迟构造 WalletRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.wallet_repo import WalletRepo  # noqa: PLC0415
    return WalletRepo()


def _warehouse_repo():
    """延迟构造 WarehouseRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.warehouse_repo import WarehouseRepo  # noqa: PLC0415
    return WarehouseRepo()


def _order_repo():
    """延迟构造 OrderRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.order_repo import OrderRepo  # noqa: PLC0415
    return OrderRepo()


def _draft_repo():
    """延迟构造 DraftRepo（避免模块级导入 dal）。"""
    from ozon_common.dal.repositories.draft_repo import DraftRepo  # noqa: PLC0415
    return DraftRepo()


def _random_offer_id() -> str:
    """随机货号(OZ+10位)。延迟导入 listing_build，避免循环依赖。"""
    from webui.listing_build import random_offer_id  # noqa: PLC0415
    return random_offer_id()


# OZ 随机占位货号(random_offer_id 生成的)模式：只有这种和空货号才会被重格式化，真实/已格式化货号不动
_OZ_PLACEHOLDER = re.compile(r"^OZ[A-Z0-9]{10}$")
# 货号片段清洗：去 HTML 实体 + 空白/斜杠/尖括号等不适合做货号的字符；连字符是分隔符故也去掉
_OID_STRIP = re.compile(r"[\s/\\><&;,|+]+")


def _oid_seg(value: Any) -> str:
    s = str(value or "").replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return _OID_STRIP.sub("", s).strip("-").strip()


def _offer_id_base(platform: Any, source_raw: Any) -> str:
    """按 {平台}-{变体维度值} 拼货号(可读，标明来源+哪个 SKU)：
    1688/ozon/wb + selected_aspects 各轴值，如 1688-红-XL；无变体维度退回 spec_attrs；再没有就平台+随机短码。"""
    plat = str(platform or "1688").strip() or "1688"
    sr = source_raw if isinstance(source_raw, dict) else {}
    parts = []
    aspects = sr.get("selected_aspects")
    if isinstance(aspects, list):
        for a in aspects:
            seg = _oid_seg((a or {}).get("value") if isinstance(a, dict) else "")
            if seg:
                parts.append(seg)
    if not parts:
        seg = _oid_seg(sr.get("spec_attrs") or sr.get("variant_label"))
        if seg:
            parts.append(seg)
    if parts:
        return plat + "-" + "-".join(parts)
    import uuid  # noqa: PLC0415
    return plat + "-" + uuid.uuid4().hex[:6].upper()


# 默认落 ozon-listing-webui/data/products.db（data/ 不随 backend/ 下移，故用 parents[1]）；
# 可用 OZON_WEBUI_DB 环境变量改指（测试/多库时不污染主库）
DEFAULT_DB = Path(os.environ.get("OZON_WEBUI_DB") or (Path(__file__).resolve().parents[1] / "data" / "products.db"))

# 系统级全局设置（不归任何用户，存 user_id=0）：JWT 密钥 + 服务级共享 OSS 桶配置。
# 其余设置（Ozon 凭证/AI 配置/汇率/店铺等）按用户隔离。
GLOBAL_SETTING_KEYS = {
    "jwt_secret",
    "oss_endpoint", "oss_bucket", "oss_access_key_id", "oss_access_key_secret", "oss_public_base",
}


def _parse_iso(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_int_or_none(value: Any) -> int | None:
    if value in (None, "", " "):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, "", " "):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Store:
    def __init__(self, path: Path | str | None = None) -> None:
        from ozon_common.dal.engine import mysql_url_from_env  # noqa: PLC0415
        # 部署到服务器(容器设了 OZON_MYSQL_*) 走 MySQL；否则本地 SQLite（行为不变）。
        # Store 不再持有裸连接：建表/回填/请求级 session 统一走 dal engine（见 init()）。
        self._is_mysql = bool(mysql_url_from_env())
        if self._is_mysql:
            self.path = None
        else:
            # 调用时读模块级 DEFAULT_DB（而非定义时绑定默认参数），
            # 这样测试 `store.DEFAULT_DB = 临时库` 能真正生效、不污染主库。
            self.path = Path(path) if path is not None else Path(DEFAULT_DB)
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def close(self) -> None:
        # 释放请求级 session 用的 engine 连接池（否则 Windows 下 SQLite 文件被占，临时库删不掉）。
        eng = getattr(self, "_session_engine", None)
        if eng is not None:
            eng.dispose()
            self._session_engine = None

    def init(self) -> None:
        # 建表权威切到 SQLAlchemy metadata（与老裸 SQL DDL schema 一致，已由保真测试证明）；
        # 历史数据回填仍 run-once、自限，剥到 webui.db_backfills。
        from ozon_common.dal.engine import engine_for  # noqa: PLC0415
        from ozon_common.dal.schema import metadata  # noqa: PLC0415
        from ozon_common.dal.session import bind_engine  # noqa: PLC0415
        from webui.db_backfills import run_backfills  # noqa: PLC0415
        eng = engine_for(self.path if not self._is_mysql else None)
        metadata.create_all(eng)          # 建全部表（替代老裸 SQL DDL / db.init_mysql）
        # 绑定请求级 session 的全局 sessionmaker（与本 Store 同一个库）：
        # 让 Store 转调仓储的方法在任何上下文（HTTP/测试/worker）都能自开 session 兜底。
        # 注意：这里不 dispose eng——它要留给 sessionmaker 用；存到 self 以便 close() 释放。
        self._session_engine = eng
        bind_engine(eng)
        run_backfills(eng)               # 数据回填，用 SQLAlchemy engine

    # ---------- 类目/属性值 本地缓存 ----------
    def save_catalog_leaves(self, language: str, leaves: list[dict[str, Any]]) -> None:
        _in_scope(lambda: _catalog_cache_repo().save_catalog_leaves(language, leaves))

    def load_catalog_leaves(self, language: str) -> list[dict[str, Any]] | None:
        return _in_scope(lambda: _catalog_cache_repo().load_catalog_leaves(language))

    def save_catalog_tree(self, language: str, tree: Any) -> None:
        _in_scope(lambda: _catalog_cache_repo().save_catalog_tree(language, tree))

    def load_catalog_tree(self, language: str) -> Any | None:
        return _in_scope(lambda: _catalog_cache_repo().load_catalog_tree(language))

    def save_category_attrs(self, cat: int, type_id: int, attrs: list[dict[str, Any]], language: str = "ZH_HANS") -> None:
        _in_scope(lambda: _catalog_cache_repo().save_category_attrs(cat, type_id, attrs, language))

    def load_category_attrs(
        self, cat: int, type_id: int, language: str = "ZH_HANS", *, max_age_days: int = 30
    ) -> list[dict[str, Any]] | None:
        return _in_scope(lambda: _catalog_cache_repo().load_category_attrs(cat, type_id, language, max_age_days=max_age_days))

    def save_attr_values(self, cat: int, type_id: int, attr_id: int,
                         values: list[dict[str, Any]], oversized: bool,
                         language: str = "RU") -> None:
        _in_scope(lambda: _catalog_cache_repo().save_attr_values(cat, type_id, attr_id, values, oversized, language))

    def load_attr_values(self, cat: int, type_id: int, attr_id: int,
                         language: str = "RU") -> tuple[list[dict[str, Any]], bool] | None:
        return _in_scope(lambda: _catalog_cache_repo().load_attr_values(cat, type_id, attr_id, language))

    # ---------- 佣金类目映射（按 Ozon 类目记住对应的 realFBS 佣金类目）----------
    def save_commission_map(
        self, cat: int, type_id: int, parent_en: str, sub_en: str, rfbs: list[float]
    ) -> None:
        _in_scope(lambda: _commission_repo().save_commission_map(cat, type_id, parent_en, sub_en, rfbs))

    def load_commission_map(self, cat: int, type_id: int) -> dict[str, Any] | None:
        return _in_scope(lambda: _commission_repo().load_commission_map(cat, type_id))

    def get_realfbs_routes(self) -> list[dict[str, Any]] | None:
        """realFBS 运费路线（全局，user_id=0）。无记录返回 None（由上层灌种子）。"""
        return _in_scope(lambda: _commission_repo().get_realfbs_routes())

    def set_realfbs_routes(self, routes: list[dict[str, Any]]) -> None:
        """整表覆盖 realFBS 运费路线（CSV 导入用）。存为全局 settings kv 的一个 JSON。"""
        _in_scope(lambda: _commission_repo().set_realfbs_routes(routes))

    def get_commission_categories(self) -> list[dict[str, Any]] | None:
        """realFBS 佣金类目表（全局，user_id=0）。无记录返回 None（由上层灌种子）。"""
        return _in_scope(lambda: _commission_repo().get_commission_categories())

    def set_commission_categories(self, cats: list[dict[str, Any]]) -> None:
        """整表覆盖佣金类目（Excel 导入用）。存为全局 settings kv 的一个 JSON。"""
        _in_scope(lambda: _commission_repo().set_commission_categories(cats))

    def save_attribute_values(
        self, cat: int, type_id: int, attr: int, values: list[dict[str, Any]], language: str = "ZH_HANS"
    ) -> int:
        return _in_scope(lambda: _catalog_cache_repo().save_attribute_values(cat, type_id, attr, values, language))

    def find_attribute_values(
        self, cat: int, type_id: int, attr: int, query: str, language: str = "ZH_HANS", *, limit: int = 30
    ) -> list[dict[str, Any]]:
        return _in_scope(lambda: _catalog_cache_repo().find_attribute_values(cat, type_id, attr, query, language, limit=limit))

    def get_settings(self, user_id: int | None = None) -> dict[str, Any]:
        """某用户的设置；自动并入系统级全局(user_id=0，如 OSS/jwt_secret)。"""
        from ozon_common.dal.repositories.settings_repo import SettingsRepo  # noqa: PLC0415
        uid = _uid(user_id)
        return _in_scope(lambda: SettingsRepo().get_settings(uid))

    def save_settings(self, settings: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        """写设置：全局键(GLOBAL_SETTING_KEYS)落 user_id=0，其余落该用户。"""
        from ozon_common.dal.repositories.settings_repo import SettingsRepo  # noqa: PLC0415
        uid = _uid(user_id)
        return _in_scope(lambda: SettingsRepo().save_settings(settings, uid))

    # ---- 用户（多用户鉴权）----
    def create_user(self, username: str, password_hash: str, role: str = "user",
                    max_stores: int = 1) -> dict[str, Any]:
        return _in_scope(lambda: _user_repo().create_user(username, password_hash, role, max_stores))

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return _in_scope(lambda: _user_repo().get_user_by_username(username))

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        return _in_scope(lambda: _user_repo().get_user_by_id(user_id))

    def count_users(self) -> int:
        return _in_scope(lambda: _user_repo().count_users())

    # ---- 用户管理（仅 admin 用；不返回 password_hash）----
    def list_users(self) -> list[dict[str, Any]]:
        return _in_scope(lambda: _user_repo().list_users())

    def set_max_stores(self, user_id: int, max_stores: int) -> None:
        return _in_scope(lambda: _user_repo().set_max_stores(user_id, max_stores))

    def set_status(self, user_id: int, status: str) -> None:
        return _in_scope(lambda: _user_repo().set_status(user_id, status))

    def set_password_hash(self, user_id: int, password_hash: str) -> None:
        return _in_scope(lambda: _user_repo().set_password_hash(user_id, password_hash))

    def delete_user(self, user_id: int) -> None:
        """硬删用户：连同 user_id 关联数据（草稿/钱包/流水/设置）+ 其店铺的
        store_client_id 关联数据（仓库/订单/采购/快照）一起删。不可逆。"""
        return _in_scope(lambda: _user_repo().delete_user(user_id))

    # ---- 钱包（按 user_id 隔离，contextvar 默认；转调 WalletRepo）----
    # recharge/deduct/refund「改余额 + 写流水」整体在一个 _in_scope 内完成 →
    # 单 session 单事务 → 原子（详见 wallet_repo.py）。
    def get_account(self, user_id: int | None = None) -> dict[str, Any]:
        """取账户，没有则开户（余额0）。"""
        user_id = _uid(user_id)
        return _in_scope(lambda: _wallet_repo().get_account(user_id))

    def recharge(self, amount: float, *, remark: str = "", biz_no: str | None = None,
                 user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        return _in_scope(
            lambda: _wallet_repo().recharge(amount, remark=remark, biz_no=biz_no, user_id=user_id)
        )

    def deduct(self, amount: float, *, biz_no: str | None = None, remark: str = "",
               user_id: int | None = None) -> bool:
        """原子扣款：仅 balance>=amount 才扣（条件 UPDATE 防并发超扣）。成功 True，余额不足 False。"""
        user_id = _uid(user_id)
        return _in_scope(
            lambda: _wallet_repo().deduct(amount, biz_no=biz_no, remark=remark, user_id=user_id)
        )

    def refund(self, amount: float, *, biz_no: str | None = None, remark: str = "",
               user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        return _in_scope(
            lambda: _wallet_repo().refund(amount, biz_no=biz_no, remark=remark, user_id=user_id)
        )

    def list_txns(self, user_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        user_id = _uid(user_id)
        return _in_scope(lambda: _wallet_repo().list_txns(user_id, limit))

    def insert_draft(self, draft: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        store_cid = str(draft.get("store_client_id") or "")
        # validate_draft / _offer_id_base 是 webui-only 逻辑，留在 Store 层算好再转调 repo
        errors = list(validate_draft(draft))
        status = "invalid" if errors else draft["status"]
        offer_id_base = _offer_id_base(draft.get("source_platform"), draft.get("source_raw"))
        return _in_scope(lambda: _draft_repo().insert_draft(
            draft, user_id=user_id, store_cid=store_cid,
            errors=errors, status=status, offer_id_base=offer_id_base,
        ))

    def set_media_status(self, draft_id: int, status: str) -> None:
        _in_scope(lambda: _draft_repo().set_media_status(draft_id, status))

    def apply_media_oss(self, draft_id: int, media_map: dict) -> None:
        """把草稿 images/video_url 里命中 media_map 的原 URL 换成 OSS URL，并置 media_status=done。
        从 draft_images 表读、_sync_draft_images 写。"""
        _in_scope(lambda: _draft_repo().apply_media_oss(draft_id, media_map))

    def list_pending_media_drafts(self, user_id: int) -> list[dict]:
        """当前用户 media_status=pending 的草稿，返回 [{id, images, video_url}]，供插件补传。"""
        return _in_scope(lambda: _draft_repo().list_pending_media_drafts(int(user_id)))

    def list_drafts(self, user_id: int | None = None) -> list[dict[str, Any]]:
        user_id = _uid(user_id)
        return _in_scope(lambda: _draft_repo().list_drafts(user_id))

    def count_by_status(self, user_id: int | None = None, store_client_id: str | None = None,
                        group: bool = False) -> dict[str, int]:
        """各状态计数 + all 总数（给前端 Tab 用，后端分页后前端无法自算）。
        store_client_id 非 None 时按当前店过滤（草稿绑定店后，列表/计数都是店级）。
        group=True：按变体组计数（一个组算一条，组的状态=代表/最新成员的状态），与分组列表对齐。"""
        user_id = _uid(user_id)
        return _in_scope(lambda: _draft_repo().count_by_status(
            user_id, store_client_id=store_client_id, group=group))

    def list_drafts_page(
        self, *, status: str = "all", page: int = 1, page_size: int = 20,
        user_id: int | None = None, store_client_id: str | None = None, group: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """真·后端分页：按 user_id + status (+当前店) 过滤 + LIMIT/OFFSET。返回 (当前页草稿, 该过滤下总数)。
        group=True：同一 variant_group 只出代表行(最新成员)+group_count，再对「组」分页；status 按组代表状态过滤
        （与 count_by_status(group=True) 同一口径，保证 Tab 数字 = 列表行数、不跨页重复）。"""
        user_id = _uid(user_id)
        return _in_scope(lambda: _draft_repo().list_drafts_page(
            status=status, page=page, page_size=page_size,
            user_id=user_id, store_client_id=store_client_id, group=group))

    def get_draft(self, draft_id: int, user_id: int | None = None) -> dict[str, Any] | None:
        user_id = _uid(user_id)
        return _in_scope(lambda: _draft_repo().get_draft(draft_id, user_id))

    def find_by_source_url(
        self, source_url: str, user_id: int | None = None, store_client_id: str | None = None
    ) -> dict[str, Any] | None:
        """按 (user, source_url) 查；store_client_id 非 None 时再按店过滤（草稿绑定店后去重要按店）。"""
        user_id = _uid(user_id)
        return _in_scope(lambda: _draft_repo().find_by_source_url(
            source_url, user_id, store_client_id))

    def find_by_offer_id(self, offer_id: str, user_id: int | None = None) -> dict[str, Any] | None:
        user_id = _uid(user_id)
        return _in_scope(lambda: _draft_repo().find_by_offer_id(str(offer_id), user_id))

    def update_draft(self, draft_id: int, patch: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        user_id = _uid(user_id)
        def _do() -> dict[str, Any]:
            repo = _draft_repo()
            current = repo.get_draft(draft_id, user_id)
            if current is None:
                raise KeyError(f"draft {draft_id} not found")
            updated = {**current, **patch, "updated_at": utc_now_iso()}
            errors = list(validate_draft(updated))
            # 调用方可显式传入额外校验错误（如发布时的"缺必填属性"），合并持久化
            for extra in patch.get("validation_errors") or []:
                if extra not in errors:
                    errors.append(extra)
            status = patch.get("status") or ("ready" if not errors else "invalid")
            return repo.update_draft(
                draft_id, updated, user_id=user_id,
                errors=errors, status=status, sync_images=("images" in patch))
        return _in_scope(_do)

    def set_ai_proposal(self, draft_id: int, proposal: dict | None) -> None:
        """写/清空草稿的 AI 待确认草案列；不触碰其它字段、不重算 status。"""
        _in_scope(lambda: _draft_repo().set_ai_proposal(draft_id, proposal))

    def delete_draft(self, draft_id: int, user_id: int | None = None) -> None:
        user_id = _uid(user_id)
        _in_scope(lambda: _draft_repo().delete_draft(draft_id, user_id))

    # ---------- 仓库（功能4）----------
    def upsert_warehouses(self, items: list[dict[str, Any]], store_client_id: str = "") -> None:
        _in_scope(lambda: _warehouse_repo().upsert_warehouses(items, store_client_id))

    def list_warehouses(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        return _in_scope(lambda: _warehouse_repo().list_warehouses(store_client_id))

    def set_default_warehouse(self, warehouse_id: int, store_client_id: str = "") -> None:
        """每店一个默认仓：只在该店范围内清旧默认、设新默认。"""
        _in_scope(lambda: _warehouse_repo().set_default_warehouse(warehouse_id, store_client_id))

    # ---------- 配送方式（功能4 附属，挂在仓库下）----------
    def replace_delivery_methods(self, items: list[dict[str, Any]], store_client_id: str = "") -> None:
        """按店全量替换配送方式：先清本店旧行，再插新行。Ozon 上被删/停用的本地随之消失。"""
        _in_scope(lambda: _warehouse_repo().replace_delivery_methods(items, store_client_id))

    def list_delivery_methods(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        return _in_scope(lambda: _warehouse_repo().list_delivery_methods(store_client_id))

    # ---------- 订单（功能5）----------
    def upsert_postings(self, items: list[dict[str, Any]], store_client_id: str = "") -> None:
        _in_scope(lambda: _order_repo().upsert_postings(items, store_client_id))

    def list_postings(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        return _in_scope(lambda: _order_repo().list_postings(store_client_id))

    def get_posting(self, posting_number: str) -> dict[str, Any] | None:
        return _in_scope(lambda: _order_repo().get_posting(posting_number))

    # ---------- 备货（功能5）----------
    def rebuild_procurement(self, store_client_id: str = "") -> None:
        """按 postings × drafts(offer_id) JOIN 重建待采购行；已存在的保留采购状态/备注。
        按店重建：只用该店 postings，offer_id 在该店草稿里找供应商/成本，采购行带 store_client_id。"""
        _in_scope(lambda: _order_repo().rebuild_procurement(store_client_id))

    def list_procurement(self, store_client_id: str | None = None) -> list[dict[str, Any]]:
        return _in_scope(lambda: _order_repo().list_procurement(store_client_id))

    def set_procurement_state(self, proc_id: int, state: str, *, note: str | None = None) -> None:
        _in_scope(lambda: _order_repo().set_procurement_state(proc_id, state, note=note))

    # ---------- 跟卖快照（插件用）----------
    def add_offer_snapshot(self, snap: dict[str, Any]) -> dict[str, Any]:
        from ozon_common.dal.repositories.offer_snapshot_repo import OfferSnapshotRepo  # noqa: PLC0415
        return _in_scope(lambda: OfferSnapshotRepo().add_offer_snapshot(snap))

    def latest_offer_snapshot(self, product_id: str) -> dict[str, Any] | None:
        from ozon_common.dal.repositories.offer_snapshot_repo import OfferSnapshotRepo  # noqa: PLC0415
        return _in_scope(lambda: OfferSnapshotRepo().latest_offer_snapshot(product_id))

    def list_offer_snapshots(self, product_id: str, limit: int = 500) -> list[dict[str, Any]]:
        from ozon_common.dal.repositories.offer_snapshot_repo import OfferSnapshotRepo  # noqa: PLC0415
        return _in_scope(lambda: OfferSnapshotRepo().list_offer_snapshots(product_id, limit))

    def list_drafts_by_variant_group(self, group: str) -> list[dict[str, Any]]:
        """返回同组草稿（按 id 升序）。走 variant_group 索引列，只取同组那几行，不扫全表。"""
        return _in_scope(lambda: _draft_repo().list_drafts_by_variant_group(group))

    def _unique_offer_id(self, base: str, exclude_id: int | None = None) -> str:
        """保证货号唯一：撞库就加 -2/-3。转调 DraftRepo（app_service.regenerate_offer_id 仍用）。"""
        return _in_scope(lambda: _draft_repo()._unique_offer_id(base, exclude_id=exclude_id))

    # ---------- draft_images 一对多表 ----------

    def add_draft_image(self, draft_id: int, url: str, *, type: str = "",
                        source: str = "generated") -> int:
        """直接插入一行 draft_images（position=当前最大+1），避免读改写 images_json 全数组。
        返回新行 id。"""
        from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo  # noqa: PLC0415
        return _in_scope(
            lambda: DraftImageRepo().add_draft_image(
                draft_id, url, type=type, source=source
            )
        )

    def gallery_add(self, draft_id: int, image_ids: list[int]) -> None:
        from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo  # noqa: PLC0415
        _in_scope(lambda: DraftImageRepo().add_to_gallery(draft_id, image_ids))

    def gallery_remove(self, draft_id: int, image_ids: list[int]) -> None:
        from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo  # noqa: PLC0415
        _in_scope(lambda: DraftImageRepo().remove_from_gallery(draft_id, image_ids))

    def gallery_delete(self, draft_id: int, image_id: int) -> None:
        from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo  # noqa: PLC0415
        _in_scope(lambda: DraftImageRepo().delete_image(draft_id, image_id))

    def gallery_reorder(self, draft_id: int, image_ids: list[int]) -> None:
        from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo  # noqa: PLC0415
        _in_scope(lambda: DraftImageRepo().reorder_gallery(draft_id, image_ids))

    def copy_images(self, src_draft_id: int, image_urls: list[str],
                    target_draft_ids: list[int]) -> dict[int, int]:
        from ozon_common.dal.repositories.draft_image_repo import DraftImageRepo  # noqa: PLC0415
        return _in_scope(lambda: DraftImageRepo().copy_images(
            src_draft_id, image_urls, target_draft_ids))

    # ---------- 出图任务（gen_jobs / gen_job_images）----------

    def create_gen_job(self, draft_id: int, target: int, user_id: int | None = None) -> dict[str, Any]:
        uid = _uid(user_id)
        return _in_scope(lambda: _gen_job_repo().create_gen_job(draft_id, target, uid))

    def get_gen_job(self, job_id: int) -> dict[str, Any] | None:
        return _in_scope(lambda: _gen_job_repo().get_gen_job(job_id))

    def get_latest_gen_job(self, draft_id: int, user_id: int | None = None) -> dict[str, Any] | None:
        uid = _uid(user_id)
        return _in_scope(lambda: _gen_job_repo().get_latest_gen_job(draft_id, uid))

    def list_gen_jobs(self, draft_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
        uid = _uid(user_id)
        return _in_scope(lambda: _gen_job_repo().list_gen_jobs(draft_id, uid))

    def has_active_gen_job(self, draft_id: int, user_id: int | None = None) -> bool:
        uid = _uid(user_id)
        return _in_scope(lambda: _gen_job_repo().has_active_gen_job(draft_id, uid))

    def update_gen_job(self, job_id: int, patch: dict[str, Any]) -> dict[str, Any] | None:
        return _in_scope(lambda: _gen_job_repo().update_gen_job(job_id, patch))

    def set_gen_job_status(self, job_id: int, status: str) -> None:
        return _in_scope(lambda: _gen_job_repo().set_gen_job_status(job_id, status))

    def create_gen_job_images(self, job_id: int, slots: list[dict[str, Any]]) -> None:
        return _in_scope(lambda: _gen_job_repo().create_gen_job_images(job_id, slots))

    def get_gen_job_images(self, job_id: int) -> list[dict[str, Any]]:
        return _in_scope(lambda: _gen_job_repo().get_gen_job_images(job_id))

    def update_gen_job_image(self, image_id: int, patch: dict[str, Any]) -> None:
        return _in_scope(lambda: _gen_job_repo().update_gen_job_image(image_id, patch))

    def set_gen_job_image_status(self, image_id: int, status: str, url: str | None = None,
                                 error: str | None = None) -> None:
        return _in_scope(
            lambda: _gen_job_repo().set_gen_job_image_status(image_id, status, url, error)
        )

    def count_gen_job_images_by_status(self, job_id: int) -> dict[str, int]:
        return _in_scope(lambda: _gen_job_repo().count_gen_job_images_by_status(job_id))
