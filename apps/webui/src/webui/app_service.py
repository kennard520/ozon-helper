from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger("ozon.app")
if not log.handlers:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s [ozon] %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
log.propagate = False  # 不往 root logger 传播，避免被 uvicorn 吞掉

ROOT = Path(__file__).resolve().parents[2]   # apps/webui/(frontend dist 在此下)
REPO = ROOT.parents[1]
AUTH_ROOT = REPO / ".auth"
PROFILE_1688 = AUTH_ROOT / "1688_profile"
FRONTEND_DIST = ROOT / "frontend" / "dist"
_FONT_PATH = str(Path(__file__).resolve().parent / "assets" / "Montserrat-VF.ttf")  # 俄语信息图字体（随镜像）
_GEN_SIZE = "1024x1536"   # 全站统一生图尺寸(gpt-image 竖版,生成时即指定,不裁)；与 gen_image.DEFAULT_SIZE 一致

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time  # noqa: E402
import urllib.request  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

import webui.ai_video as ai_video  # noqa: E402
import webui.media as _media  # noqa: E402
from ozon_common.oss import OssClient  # noqa: E402
from webui.catalog import Catalog  # noqa: E402
from webui.drafts import (  # noqa: E402
    BRAND_ATTR_ID,
    NO_BRAND,
    collected_chars,
    create_draft_from_url,
    dimension_warnings,
    match_chars_to_attributes,
    missing_required_attributes,
    normalize_category_attrs,
    split_collection_value,
    to_ozon_import_item,
    utc_now_iso,
    validate_draft,
)
from webui.media_rehost import needs_rehost, rehost_draft_media  # noqa: E402
from webui.ozon_client_adapter import (  # noqa: E402
    build_client,
    get_attribute_values,
    get_category_attributes,
    get_import_info,
    publish_items,
    search_attribute_values,
)
from webui.settings_migrate import migrate_ai, normalize_stores  # noqa: E402
from webui.store import Store  # noqa: E402

# 钱包出口处 Decimal→float 的字段（DAL 内部保持 Decimal 精确，仅 API 边界转 number）
_ACCOUNT_MONEY_KEYS = ("balance", "total_recharge", "total_consume")
_TXN_MONEY_KEYS = ("amount", "balance_after")

from webui.services._helpers import (  # noqa: E402
    OZON_ATTRIBUTE_LANGUAGES,
    _ATTR_EXCL,
    _DIM_KW,
    _VOL_KW,
    _WEIGHT_KW,
    _attr_language,
    _download_bytes,
    _has_cjk,
    _img_type_from_label,
    _is_country_attr,
    _models_url,
    _money_to_float,
    _parse_dims_mm,
    _parse_volume_ml,
    _parse_weight_g,
    _to_int,
    step_flags,
)  # noqa
from webui.services._auth import AuthMixin  # noqa: E402
from webui.services._settings import SettingsMixin  # noqa: E402
from webui.services._category import CategoryMixin  # noqa: E402
from webui.services._drafts import DraftMixin  # noqa: E402
from webui.services._ozon_sync import OzonSyncMixin  # noqa: E402
from webui.services._publish import PublishMixin  # noqa: E402
from webui.services._ai_card import AiCardMixin  # noqa: E402
from webui.services._ai_image import AiImageMixin  # noqa: E402
from webui.services._ai_video import AiVideoMixin  # noqa: E402
from webui.services._gallery import GalleryMixin  # noqa: E402
from webui.services._ext import ExtMixin  # noqa: E402
from webui.services._genjob import GenJobMixin  # noqa: E402
from webui.services._pricing import PricingMixin  # noqa: E402
from webui.services._warehouse import WarehouseMixin  # noqa: E402
from webui.services._textjob import TextJobMixin  # noqa: E402
from webui.services._pipeline import PipelineMixin  # noqa: E402


class App(AuthMixin, SettingsMixin, CategoryMixin, DraftMixin, OzonSyncMixin, PublishMixin, AiCardMixin, AiImageMixin, AiVideoMixin, GalleryMixin, ExtMixin, GenJobMixin, PricingMixin, WarehouseMixin, TextJobMixin, PipelineMixin):
    def __init__(self) -> None:
        self.store = Store()
        self._cand_lock = threading.Lock()   # 候选区读-改-写串行化(图集并发出图时防丢候选)
        self.catalog = Catalog(store=self.store, language="ZH_HANS")
        # 俄语树用来对齐采集回来的俄语类目路径，做自动匹配
        self.catalog_ru = Catalog(store=self.store, language="RU")
        self._ensure_auth_bootstrap()

    # ---------- 鉴权（多用户）----------
    def _ensure_auth_bootstrap(self) -> None:
        """首次启动：生成稳定 JWT 密钥 + 建默认管理员 admin/admin(user_id=1，承接旧数据)。"""
        settings = self.store.get_settings()
        if not settings.get("jwt_secret"):
            self.store.save_settings({"jwt_secret": os.urandom(32).hex()})
        if self.store.count_users() == 0:
            from webui.auth import hash_password  # noqa: PLC0415
            self.store.create_user("admin", hash_password("admin"), role="admin")
