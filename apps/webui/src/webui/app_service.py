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
from webui.services._publish import PublishMixin  # noqa: E402
from webui.services._ai_card import AiCardMixin  # noqa: E402
from webui.services._ai_image import AiImageMixin  # noqa: E402
from webui.services._ai_video import AiVideoMixin  # noqa: E402


class App(AuthMixin, SettingsMixin, CategoryMixin, DraftMixin, PublishMixin, AiCardMixin, AiImageMixin, AiVideoMixin):
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

    # ---------- 插件桥接（/api/ext/*）----------
    def ext_ping(self) -> dict:
        # 带上 rub_cny 汇率：插件采集 Ozon 卢布价后据此换算成人民币再回传（后端统一 CNY）
        rate = self.store.get_settings().get("rub_cny")
        try:
            rate = float(rate) if rate not in (None, "") else None
        except (TypeError, ValueError):
            rate = None
        return {"ok": True, "name": "ozon-listing-webui", "version": "1", "rub_cny": rate}

    def _ext_cache_video(self, draft_id: int, video_url: str) -> None:
        """为草稿下载视频本地副本（同 collect 流程）：Ozon/1688 CDN 的 <video> 跨域会卡死，
        落 /media/ 同源才能播。best-effort，失败不影响采集。"""
        vurl = str(video_url or "")
        if not vurl.startswith("http"):
            return
        cur = self.store.get_draft(draft_id)
        sr = cur.get("source_raw") if cur else None
        if isinstance(sr, str):
            from webui.drafts import loads_json  # noqa: PLC0415
            sr = loads_json(sr, {})
        sr = sr if isinstance(sr, dict) else {}
        if sr.get("video_local"):
            return
        try:
            from webui.media import download_video  # noqa: PLC0415
            vloc = download_video(vurl, f"draft-{draft_id}")
            if vloc:
                self.store.update_draft(draft_id, {"source_raw": {**sr, "video_local": vloc}})
        except Exception:  # noqa: BLE001
            pass

    def ext_collect_parsed(self, payload: dict) -> dict:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("url required")
        data = payload.get("data") or {}
        _has_media = bool((data.get("images") or [])) or bool(str(data.get("video_url") or "").strip())
        from webui.drafts import create_draft_from_url  # noqa: PLC0415
        scraped = {
            "source_title": data.get("title"),
            "ozon_title": data.get("title"),  # Ozon 竞品标题已是俄语，直接用
            "description": data.get("description"),
            "price": data.get("price"),
            "old_price": data.get("old_price"),
            "images": data.get("images") or [],
            "video_url": data.get("video_url"),
            "weight_g": data.get("weight_g"),
            "length_mm": data.get("length_mm"),
            "width_mm": data.get("width_mm"),
            "height_mm": data.get("height_mm"),
            "category_path": data.get("category_path"),
        }
        # 采集的属性(名值对 {name,value}) → draft.attributes，供 collected_chars → auto-map/AI；
        # 发布时 to_ozon_import_item 只发 {id,values}，名值对自动丢弃（不会误发给 Ozon）。
        collected_attrs = [
            {"name": str(a["name"]).strip(), "value": str(a.get("value") or "").strip()}
            for a in (data.get("attributes") or [])
            if isinstance(a, dict) and a.get("name") and a.get("value")
        ]
        # 主题标签(webHashtags) → 属性 23171「#Хештеги」，多标签空格连接成单值（与 Ozon 卡片惯例一致）
        tags = [str(t).strip() for t in (data.get("hashtags") or []) if str(t).strip()]
        tag_attr = (
            {"id": 23171, "name": "#Хештеги", "values": [{"value": " ".join(tags)}]}
            if tags else None
        )
        attrs_list = list(collected_attrs)
        if tag_attr:
            attrs_list.append(tag_attr)
        if attrs_list:
            scraped["attributes"] = attrs_list
        # 按买家面包屑路径自动匹配卖家类目 → 填 category_id/type_id（没配 key/无匹配则跳过，回退编辑器手选）
        try:
            self._auto_match_category(scraped)   # 类目匹配走本地缓存，快(~0.06s)，保留
        except Exception:  # noqa: BLE001
            pass
        platform = str(data.get("source_platform") or "ozon").strip() or "ozon"
        # 1688 采集价=「进价」而非售价 → 进 cost_cny，按默认倍率算售价(进价×1.3×2)/划线价(售价×1.8)
        if platform == "1688":
            from webui.listing_build import default_pricing  # noqa: PLC0415
            try:
                cost = float(str(scraped.get("price") or "").strip() or 0)
            except (TypeError, ValueError):
                cost = 0.0
            if cost > 0:
                scraped["cost_cny"] = cost
                pr = default_pricing(cost)
                if pr:
                    scraped["price"], scraped["old_price"] = str(pr[0]), str(pr[1])
        new_draft = create_draft_from_url(url, source_platform=platform, scraped=scraped)
        # 草稿绑定店：插件带 store_client_id=当前店；缺省回退默认店(settings.ozon_client_id)，单店用户零感知
        store_cid = str(payload.get("store_client_id") or data.get("store_client_id") or "").strip()
        if not store_cid:
            store_cid = str((self.store.get_settings() or {}).get("ozon_client_id") or "")
        new_draft["store_client_id"] = store_cid
        det = data.get("detail_images") or []
        rcj = data.get("rich_content_json") or None
        vars_ = data.get("variants") or []
        vg = data.get("variant_group") or ""
        sa = data.get("selected_aspects") or []
        sr_new: dict = {}
        # 插件可直接带 source_raw（如 WB 的 options/brand_name，喂 auto-map/AI）
        incoming_sr = data.get("source_raw")
        if isinstance(incoming_sr, dict):
            sr_new.update(incoming_sr)
        if det:
            sr_new["detail_images"] = det
        if rcj:
            sr_new["rich_content_json"] = rcj  # 原始富文本(A+)，发布时复刻
        if vars_:
            sr_new["variants"] = vars_
        if vg:
            sr_new["variant_group"] = vg
        if sa:
            sr_new["selected_aspects"] = sa
        if sr_new:
            new_draft["source_raw"] = sr_new
        # 重复采集去重按店：同来源在不同店各存一份，刷新只补空当前店那一份。
        # 注意按完整 source_url 去重——多变体已由 normalize 保留 #sku 片段而各自唯一(各建一张草稿)，
        # 不能按 source_offer_id 兜底去重(那会把同商品的 N 个变体误并成一张)。
        existing = self.store.find_by_source_url(new_draft["source_url"], None, store_cid)
        if existing:
            # 重复采集：用新解析的源字段「补空」（不覆盖用户已编辑/已选的非空字段），
            # 这样旧的、缺描述/克重/尺寸的草稿能被重新采集刷新。
            patch = {}
            for k in ("ozon_title", "description", "price", "old_price", "images",
                      "video_url", "weight_g", "length_mm", "width_mm", "height_mm",
                      "category_id", "type_id"):
                cur = existing.get(k)
                is_empty = cur in (None, "", 0) or (isinstance(cur, list) and not cur)
                val = new_draft.get(k)
                has_val = val not in (None, "", 0) and not (isinstance(val, list) and not val)
                if is_empty and has_val:
                    patch[k] = val
            if sr_new:
                ex_sr = existing.get("source_raw")
                if not isinstance(ex_sr, dict):
                    ex_sr = {}
                merged = dict(ex_sr)
                for kk, vv in sr_new.items():
                    if not merged.get(kk):  # 旧草稿没有才补
                        merged[kk] = vv
                if merged != ex_sr:
                    patch["source_raw"] = merged
            # 属性/标签补空（不覆盖用户已填）：旧草稿没有采集名值对则补；没有 attr 23171 则补标签
            ex_attrs = existing.get("attributes")
            ex_attrs = ex_attrs if isinstance(ex_attrs, list) else []
            merged_attrs = list(ex_attrs)
            changed_attrs = False
            has_collected = any(a.get("name") and a.get("value") and "values" not in a for a in ex_attrs)
            if collected_attrs and not has_collected:
                merged_attrs = collected_attrs + merged_attrs
                changed_attrs = True
            if tag_attr and not any(_to_int(a.get("id")) == 23171 for a in ex_attrs):
                merged_attrs = merged_attrs + [tag_attr]
                changed_attrs = True
            if changed_attrs:
                patch["attributes"] = merged_attrs
            if patch:
                self.store.update_draft(existing["id"], patch)
            if _has_media and self._media_needs_upload(self.store.get_draft(existing["id"]) or existing):
                self.store.set_media_status(existing["id"], "pending")  # 媒体未传 OSS，待后台补
            self._auto_map_safe(existing["id"])   # 采集后自动映射属性（已本地缓存化，快）
            self._maybe_auto_publish(existing["id"])   # 开了 auto_publish 则后台发布
            return {"created": [{"id": existing["id"], "source_title": existing.get("source_title")}], "errors": [], "deduped": True,
                    "auto_publish": bool((self.store.get_settings() or {}).get("auto_publish"))}
        try:
            saved = self.store.insert_draft(new_draft)
        except Exception as exc:  # noqa: BLE001  兜底:并发同 url 重采等极端撞唯一键 → 找回同 url 已存在的,不再 500
            msg = str(exc)
            ex = (self.store.find_by_source_url(new_draft["source_url"], None, store_cid)
                  if (("uq_draft" in msg) or ("Duplicate" in msg) or ("UNIQUE" in msg)) else None)
            if ex:
                return {"created": [{"id": ex["id"], "source_title": ex.get("source_title")}],
                        "errors": [], "deduped": True,
                        "auto_publish": bool((self.store.get_settings() or {}).get("auto_publish"))}
            raise
        if _has_media and self._media_needs_upload(saved):
            self.store.set_media_status(saved["id"], "pending")  # 媒体未传 OSS，待后台补
        self._auto_map_safe(saved["id"])   # 采集后自动映射属性（已本地缓存化，快）
        self._maybe_auto_publish(saved["id"])   # 开了 auto_publish 则后台发布
        return {"created": [{"id": saved["id"], "source_title": saved.get("source_title")}], "errors": [],
                "auto_publish": bool((self.store.get_settings() or {}).get("auto_publish"))}

    def update_draft_media(self, payload: dict) -> dict:
        """插件后台把媒体传完 OSS 后回调：把草稿里命中的原 URL 换成 OSS URL，置 media_status=done。"""
        draft_id = _to_int(payload.get("draft_id"))
        media_map = payload.get("media_map") or {}
        if not draft_id:
            raise ValueError("draft_id required")
        self.store.apply_media_oss(draft_id, dict(media_map))
        self._maybe_auto_publish(draft_id)   # 媒体传完 → 开了 auto_publish 则后台发布
        return {"ok": True}

    def pending_media_drafts(self) -> dict:
        """当前用户媒体待传(pending)的草稿，供插件后台补传。"""
        from webui.store import current_user_id  # noqa: PLC0415
        return {"drafts": self.store.list_pending_media_drafts(current_user_id.get())}

    def ext_add_snapshot(self, payload: dict) -> dict:
        pid = str(payload.get("product_id") or "").strip()
        if not pid:
            raise ValueError("product_id required")
        fc = payload.get("follow_count")
        pmin = payload.get("price_min")
        pmax = payload.get("price_max")
        last = self.store.latest_offer_snapshot(pid)
        if last and last.get("follow_count") == fc and last.get("price_min") == pmin and last.get("price_max") == pmax:
            return {"id": last.get("id"), "deduped": True}
        from webui.drafts import dumps_json, utc_now_iso  # noqa: PLC0415
        snap = {
            "product_id": pid,
            "sku": (str(payload.get("sku")) if payload.get("sku") else None),
            "captured_at": utc_now_iso(),
            "follow_count": fc,
            "price_min": pmin,
            "price_max": pmax,
            "sellers_json": dumps_json(payload.get("sellers") or []),
        }
        return self.store.add_offer_snapshot(snap)

    def ext_snapshots(self, product_id: str) -> dict:
        # price_min/max 列已是 Numeric→Decimal；API 出口 float 化保证 JSON number（前端/插件期望 number）
        snaps = [
            _money_to_float(s, ("price_min", "price_max"))
            for s in self.store.list_offer_snapshots(str(product_id))
        ]
        return {"product_id": str(product_id), "snapshots": snaps}

    # ===== realFBS 运费路线表（CSV 可维护；存 settings kv 的 JSON blob，首次读灌种子）=====
    _REALFBS_FIELDS = [
        "scoringGroup", "serviceLevel", "provider", "deliveryMethod", "ozonRating",
        "etaDays", "rateText", "batteries", "liquids", "measurements",
        "weightMinG", "weightMaxG", "valueRangeRub", "tarification",
        "volumeFormula", "compensationRub",
    ]
    _REALFBS_NUM = {"ozonRating", "weightMinG", "weightMaxG", "compensationRub"}

    def _realfbs_seed_routes(self) -> list[dict]:
        import json as _json  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        seed = Path(__file__).resolve().parent / "realfbs_routes_seed.json"
        try:
            return _json.loads(seed.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []

    def realfbs_routes(self) -> dict:
        """返回 realFBS 运费路线给定价用。表空则灌种子(141 条)并持久化。"""
        routes = self.store.get_realfbs_routes()
        if routes is None:
            routes = self._realfbs_seed_routes()
            if routes:
                self.store.set_realfbs_routes(routes)
        return {"routes": routes or []}

    def import_realfbs_routes(self, csv_text: str) -> dict:
        """CSV 整表覆盖运费路线。表头须含 _REALFBS_FIELDS 各列；数值列空→None。"""
        import csv as _csv  # noqa: PLC0415
        import io as _io  # noqa: PLC0415

        def _num(v):
            s = str(v or "").strip()
            if s in ("", "None", "nan"):
                return None
            try:
                return float(s)
            except ValueError:
                return None

        reader = _csv.DictReader(_io.StringIO(csv_text or ""))
        routes: list[dict] = []
        for row in reader:
            r: dict = {}
            for f in self._REALFBS_FIELDS:
                raw = row.get(f)
                r[f] = _num(raw) if f in self._REALFBS_NUM else str(raw or "").strip()
            if not r.get("provider") and not r.get("deliveryMethod") and not r.get("rateText"):
                continue   # 跳过全空行
            routes.append(r)
        if not routes:
            raise ValueError("CSV 未解析到任何运费路线（请确认表头含 provider/rateText 等列）")
        self.store.set_realfbs_routes(routes)
        return {"count": len(routes)}

    def export_realfbs_routes_csv(self) -> str:
        """当前运费路线导出为 CSV（给用户下载→Excel 维护→再导入）。"""
        import csv as _csv  # noqa: PLC0415
        import io as _io  # noqa: PLC0415
        routes = self.realfbs_routes()["routes"]
        buf = _io.StringIO()
        w = _csv.DictWriter(buf, fieldnames=self._REALFBS_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in routes:
            w.writerow({f: ("" if r.get(f) is None else r.get(f)) for f in self._REALFBS_FIELDS})
        return buf.getvalue()

    # ===== realFBS 佣金类目表（Excel 可维护；存 settings kv 的 JSON blob，首次读灌种子）=====
    #   只取 RFBS(=FBS) 三价格档佣金；导入认两种 Excel：Ozon 官方 Tarifs、本工具导出的模板。
    _COMMISSION_PRICE_TIERS_RUB = [1500, 5000]
    _COMMISSION_HEADER_ALIASES = {
        "parentZh": ("父类目(中)", "父类目", "parentzh"),
        "parentEn": ("父类目(英)", "parenten"),
        "subZh": ("子类目(中)", "子类目", "subzh"),
        "subEn": ("子类目(英)", "suben"),
        "r0": ("佣金% 0-1500", "0-1500", "rfbs0", "rfbs_0_1500"),
        "r1": ("佣金% 1500-5000", "1500-5000", "rfbs1"),
        "r2": ("佣金% 5000+", "5000+", "rfbs2"),
    }

    def _commission_seed(self) -> list[dict]:
        import json as _json  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        seed = Path(__file__).resolve().parent / "commission_categories_seed.json"
        try:
            return _json.loads(seed.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []

    def commission_categories(self) -> dict:
        """返回佣金类目给定价用。表空则灌种子(80 类)并持久化。"""
        cats = self.store.get_commission_categories()
        if cats is None:
            cats = self._commission_seed()
            if cats:
                self.store.set_commission_categories(cats)
        return {"categories": cats or [], "priceTiersRub": list(self._COMMISSION_PRICE_TIERS_RUB)}

    @staticmethod
    def _commission_rate(v) -> float | None:
        """单元格 → 佣金小数：>1 视为百分比(/100)，否则视为小数；空/非数/≤0 → None。"""
        s = str(v).strip() if v is not None else ""
        if s in ("", "None", "nan"):
            return None
        try:
            x = float(s.replace("%", "").replace(",", "."))
        except ValueError:
            return None
        if x <= 0:
            return None
        return round(x / 100 if x > 1 else x, 4)

    def _parse_commission_ozon(self, wb) -> list[dict]:
        """认 Ozon 官方 Tarifs：sheet 'MP Tree Tarifs CN'，列 1=父EN 2=父ZH 4=子EN 5=子ZH 6-8=RFBS。"""
        name = next((s for s in wb.sheetnames if "MP Tree Tarifs" in s), None)
        if not name:
            return []
        ws = wb[name]
        out: list[dict] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i < 2 or len(row) < 9:        # 跳过首行('Starts from')与表头行；列数不足跳过
                continue
            sub_en = str(row[4] or "").strip()
            rfbs = [self._commission_rate(row[6]), self._commission_rate(row[7]), self._commission_rate(row[8])]
            if not sub_en or any(r is None for r in rfbs):
                continue
            out.append({
                "parentEn": str(row[1] or "").strip(), "parentZh": str(row[2] or "").strip(),
                "subEn": sub_en, "subZh": str(row[5] or "").strip(), "rfbs": rfbs,
            })
        return out

    def _parse_commission_template(self, wb) -> list[dict]:
        """认本工具导出的模板：按表头名定位列（中英别名），佣金可填百分比或小数。"""
        ws = wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return []
        norm = [str(h or "").strip().lower() for h in header]

        def col(key) -> int | None:
            for alias in self._COMMISSION_HEADER_ALIASES[key]:
                a = alias.strip().lower()
                if a in norm:
                    return norm.index(a)
            return None

        idx = {k: col(k) for k in self._COMMISSION_HEADER_ALIASES}
        if idx["subEn"] is None or idx["r0"] is None:    # 表头对不上→不是我们的模板
            return []

        def at(row, key):
            j = idx[key]
            return row[j] if (j is not None and j < len(row)) else None

        out: list[dict] = []
        for row in rows:
            sub_en = str(at(row, "subEn") or "").strip()
            rfbs = [self._commission_rate(at(row, "r0")),
                    self._commission_rate(at(row, "r1")),
                    self._commission_rate(at(row, "r2"))]
            if not sub_en or any(r is None for r in rfbs):
                continue
            out.append({
                "parentEn": str(at(row, "parentEn") or "").strip(),
                "parentZh": str(at(row, "parentZh") or "").strip(),
                "subEn": sub_en, "subZh": str(at(row, "subZh") or "").strip(), "rfbs": rfbs,
            })
        return out

    def import_commission_categories_xlsx(self, data: bytes) -> dict:
        """整表覆盖佣金类目。先认 Ozon 官方 Tarifs，再认本工具模板；只取 RFBS(FBS)。"""
        import io as _io  # noqa: PLC0415

        import openpyxl  # noqa: PLC0415
        try:
            wb = openpyxl.load_workbook(_io.BytesIO(data), data_only=True, read_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"无法读取 Excel：{exc}")
        try:
            cats = self._parse_commission_ozon(wb) or self._parse_commission_template(wb)
        finally:
            wb.close()
        if not cats:
            raise ValueError("未从 Excel 解析到任何佣金类目（请用 Ozon 官方 Tarifs 文件，或本工具导出的模板）")
        # 按 (parentEn, subEn) 去重，保最后一条、保出现顺序
        seen: dict = {}
        order: list = []
        for c in cats:
            k = (c["parentEn"], c["subEn"])
            if k not in seen:
                order.append(k)
            seen[k] = c
        final = [seen[k] for k in order]
        self.store.set_commission_categories(final)
        return {"count": len(final)}

    @staticmethod
    def _commission_pct(x):
        return None if x is None else round(float(x) * 100, 2)

    def export_commission_categories_xlsx(self) -> bytes:
        """当前佣金类目导出为模板 xlsx（中文表头 + 百分比，给用户改完再导入）。"""
        import io as _io  # noqa: PLC0415

        import openpyxl  # noqa: PLC0415
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "佣金表(FBS)"
        ws.append(["父类目(中)", "父类目(英)", "子类目(中)", "子类目(英)",
                   "佣金% 0-1500", "佣金% 1500-5000", "佣金% 5000+"])
        for c in self.commission_categories()["categories"]:
            rfbs = (c.get("rfbs") or []) + [None, None, None]
            ws.append([c.get("parentZh"), c.get("parentEn"), c.get("subZh"), c.get("subEn"),
                       self._commission_pct(rfbs[0]), self._commission_pct(rfbs[1]), self._commission_pct(rfbs[2])])
        buf = _io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def get_commission_map(self, cat_id: int, type_id: int) -> dict:
        """取某 Ozon 类目记住的 realFBS 佣金类目（命中返回 {parent_en, sub_en, rfbs}）。"""
        return self.store.load_commission_map(cat_id, type_id) or {}

    def save_commission_map(self, payload: dict) -> dict:
        cat = _to_int(payload.get("cat"))
        typ = _to_int(payload.get("type"))
        if not cat or not typ:
            return {"error": "cat/type 必填"}
        self.store.save_commission_map(
            cat, typ, str(payload.get("parent_en") or ""), str(payload.get("sub_en") or ""),
            payload.get("rfbs") if isinstance(payload.get("rfbs"), list) else [],
        )
        return {"ok": True}

    def _scid_of(self, store_client_id: str | None) -> str:
        """把(可能为空的)目标店解析成实际 client_id：空→默认店。仓库/订单按它隔离。"""
        return str(self._settings_for_store(store_client_id).get("ozon_client_id") or "")

    def _warehouses_with_delivery(self, scid: str) -> list[dict]:
        """仓库列表，每个仓库挂上它的配送方式（本地按 warehouse_id 分组）。"""
        warehouses = self.store.list_warehouses(scid)
        methods = self.store.list_delivery_methods(scid)
        by_wh: dict[int, list[dict]] = {}
        for m in methods:
            by_wh.setdefault(m.get("warehouse_id"), []).append(m)
        for w in warehouses:
            w["delivery_methods"] = by_wh.get(w.get("warehouse_id"), [])
        return warehouses

    def list_warehouses(self, store_client_id: str | None = None) -> dict:
        scid = self._scid_of(store_client_id)
        return {"warehouses": self._warehouses_with_delivery(scid)}

    def sync_warehouses(self, store_client_id: str | None = None) -> dict:
        from webui.ozon_client_adapter import (  # noqa: PLC0415
            fetch_delivery_methods,
            fetch_warehouses,
        )
        settings = self._settings_for_store(store_client_id)
        scid = str(settings.get("ozon_client_id") or "")
        items = fetch_warehouses(settings)
        self.store.upsert_warehouses(items, scid)
        # 配送方式挂在仓库下：仓库同步完后逐仓拉取，按店全量替换
        wids = [w.get("warehouse_id") for w in self.store.list_warehouses(scid)]
        methods = fetch_delivery_methods(settings, wids)
        self.store.replace_delivery_methods(methods, scid)
        return {
            "synced": len(items),
            "delivery_methods": len(methods),
            "warehouses": self._warehouses_with_delivery(scid),
        }

    def set_default_warehouse(self, warehouse_id: int, store_client_id: str | None = None) -> dict:
        scid = self._scid_of(store_client_id)
        self.store.set_default_warehouse(int(warehouse_id), scid)
        return {"warehouses": self._warehouses_with_delivery(scid)}

    # ---------- 功能⑤：FBS 备货发货 ----------
    def pull_fbs(self, status: str = "awaiting_packaging", days: int = 14,
                 store_client_id: str | None = None) -> dict:
        from webui.ozon_client_adapter import pull_fbs_postings  # noqa: PLC0415
        settings = self._settings_for_store(store_client_id)
        scid = str(settings.get("ozon_client_id") or "")
        items = pull_fbs_postings(settings, status, days)
        self.store.upsert_postings(items, scid)
        self.store.rebuild_procurement(scid)
        return {"synced": len(items), "procurement": self.store.list_procurement(scid)}

    def list_procurement(self, store_client_id: str | None = None) -> dict:
        scid = self._scid_of(store_client_id)
        return {"procurement": self.store.list_procurement(scid)}

    def set_procurement_state(self, pid: int, purchase_state: str, note: str = "",
                              store_client_id: str | None = None) -> dict:
        self.store.set_procurement_state(int(pid), purchase_state, note=note)
        return {"procurement": self.store.list_procurement(self._scid_of(store_client_id))}

    def ship_posting(self, posting_number: str, store_client_id: str | None = None) -> dict:
        """按 posting 的商品组成一个包发货。不可逆。
        Ozon 发货请求要 product_id（swagger 里与 sku 是不同 ID）；而待发货单只带
        offer_id/sku，没有 product_id。故先用 offer_id 反查真实 product_id（info.id），
        绝不拿 sku 顶替——否则会发错货或被 Ozon 拒。"""
        from webui.ozon_client_adapter import get_ozon_info, ship_fbs  # noqa: PLC0415
        posting = self.store.get_posting(posting_number)
        if not posting:
            raise KeyError(f"posting {posting_number} not found")
        items = posting.get("products") or []
        offer_ids = [str(p.get("offer_id")) for p in items if p.get("offer_id")]
        if not offer_ids:
            raise ValueError("该 posting 无 offer_id，无法解析 product_id")
        settings = self._settings_for_store(store_client_id)
        try:
            info = get_ozon_info(settings, offer_ids)   # {offer_id: {id=product_id, ...}}
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"拉取商品信息失败，无法发货: {exc}") from exc
        products, missing = [], []
        for p in items:
            oid = str(p.get("offer_id") or "")
            pid = (info.get(oid) or {}).get("id")
            if not pid:
                missing.append(oid or "?")
                continue
            products.append({"product_id": int(pid), "quantity": int(p.get("quantity") or 1)})
        if missing:
            raise ValueError(f"无法解析 product_id 的商品: {', '.join(missing)}")
        if not products:
            raise ValueError("该 posting 无可发货商品")
        # warehouse_id 不传给 Ozon：/v4/posting/fbs/ship 接口只接受 posting_number + packages，
        # Ozon 从 posting 本身推断仓库，无需（也不接受）warehouse_id 参数。
        r = ship_fbs(settings, posting_number, [{"products": products}])
        return {"result": r.get("result") or [], "shipped": True, "response": r}

    # ---------- 出图任务（gen_jobs）----------

    def submit_gen_job(self, draft_id: int, target: int) -> dict:
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        if self.store.has_active_gen_job(draft_id):
            raise ValueError("该草稿已有进行中的出图任务，请等待完成")
        job = self.store.create_gen_job(draft_id, target)
        try:
            from ozon_common.mq import publish_gen_job  # noqa: PLC0415
            publish_gen_job(job["id"], draft_id, target)
        except Exception as exc:
            self.store.update_gen_job(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")
        return {"job_id": job["id"], "status": job["status"]}

    def submit_gen_images_custom(self, draft_id: int, payload: dict) -> dict:
        """用户自定义出图（AiImageDialog）：选 N 张源图 + 提示词 + 可选参考图 → 建 gen_job → MQ → worker。
        每张源图一个槽，源图为空(文生图)则建 1 个空槽。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        source_urls = [str(u).strip() for u in (payload.get("source_urls") or []) if str(u).strip()]
        if not source_urls:
            source_urls = [""]   # text2img: 一个空槽
        ref_url = str(payload.get("ref_url") or "").strip() or None
        prompt = str(payload.get("prompt") or "").strip()
        size = str(payload.get("size") or "1024x1536").strip()
        as_main = bool(payload.get("as_main"))
        target = len(source_urls)
        job = self.store.create_gen_job(draft_id, target)
        # 构造 image_plan（worker 读它来获取 prompt 和 source_url）
        slots = []
        for i, surl in enumerate(source_urls):
            sid = f"custom_{i}"
            slots.append({
                "slot_id": sid, "label": f"自定义出图{i+1}",
                "action": "custom", "source_idx": 0,
                "prompt": prompt, "size": size, "as_main": (as_main and i == 0),
                "source_url": surl or None, "ref_url": ref_url,
            })
        self.store.create_gen_job_images(job["id"], slots)
        # 存 image_plan 到 source_raw 供 worker 读取
        sr = dict(draft.get("source_raw") or {})
        sr["image_plan"] = [(sr.get("image_plan") or []) + slots][0]
        self.store.update_draft(draft_id, {"source_raw": sr})
        try:
            from ozon_common.mq import publish_gen_job  # noqa: PLC0415
            publish_gen_job(job["id"], draft_id, target, mode="custom")
        except Exception as exc:
            self.store.update_gen_job(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")
        return {"job_id": job["id"], "status": job["status"]}

    def submit_batch_gen_job(self, draft_id: int, source_indices: list[int], action: str) -> dict:
        """批量出图（白底/俄化/场景/细节/重做）：每个 source_index 一个槽，走 worker 异步。"""
        from ozon_common.gen_image import (  # noqa: PLC0415
            LOCALIZE_PROMPT,
            SCENE_PROMPT,
            WHITE_MAIN_PROMPT,
            build_infographic_prompt,
        )
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        if self.store.has_active_gen_job(draft_id):
            raise ValueError("该草稿已有进行中的出图任务")
        indices = [int(i) for i in source_indices if isinstance(i, int)]
        if not indices:
            raise ValueError("未选择图片")
        label_map = {"white": "白底图", "localize": "俄化", "scene": "场景图",
                     "detail": "细节图", "redo": "重做"}
        label = label_map.get(action, action)
        job = self.store.create_gen_job(draft_id, len(indices))
        slots = []
        for si in indices:
            p = ""
            if action == "white":
                p = WHITE_MAIN_PROMPT
            elif action == "localize":
                p = LOCALIZE_PROMPT
            elif action == "scene":
                p = SCENE_PROMPT
            elif action in ("detail", "redo"):
                p = build_infographic_prompt(role="细节" if action == "detail" else "")
            sid = f"batch_{action}_{si}"
            slots.append({"slot_id": sid, "label": f"{label}#{si}", "action": "batch",
                         "source_idx": si, "prompt": p})
        self.store.create_gen_job_images(job["id"], slots)
        sr = dict(draft.get("source_raw") or {})
        sr["image_plan"] = (sr.get("image_plan") or []) + slots
        self.store.update_draft(draft_id, {"source_raw": sr})
        try:
            from ozon_common.mq import publish_gen_job  # noqa: PLC0415
            publish_gen_job(job["id"], draft_id, len(indices), mode="batch")
        except Exception as exc:
            self.store.update_gen_job(job["id"], {"status": "failed", "error": f"MQ 发送失败: {exc}"})
            raise RuntimeError(f"消息队列不可用: {exc}")
        return {"job_id": job["id"], "status": job["status"]}

    def get_gen_job_status(self, job_id: int) -> dict:
        job = self.store.get_gen_job(job_id)
        if job is None:
            raise KeyError(f"job {job_id} not found")
        images = self.store.get_gen_job_images(job_id)
        return {"job_id": job["id"], "status": job["status"],
                "target": job["target"], "total": job["total"],
                "succeeded": job["succeeded"], "failed": job["failed"],
                "error": job.get("error"), "created_at": job["created_at"],
                "updated_at": job["updated_at"],
                "images": [{"slot_id": i["slot_id"], "label": i["label"],
                            "status": i["status"], "url": i.get("url"),
                            "error": i.get("error")} for i in images]}

    def get_latest_gen_job(self, draft_id: int) -> dict:
        job = self.store.get_latest_gen_job(draft_id)
        if job is None:
            raise KeyError(f"draft {draft_id} 没有出图任务")
        return self.get_gen_job_status(job["id"])

    def batch_latest_gen_jobs(self, draft_ids: list[int]) -> dict:
        """批量查多个草稿的全部出图任务（卡片列表展示用）。返回 {draft_id: [jobs]}。"""
        out = {}
        for did in draft_ids:
            try:
                jobs = self.store.list_gen_jobs(did)
            except Exception:
                continue
            if jobs:
                summaries = []
                for j in jobs:
                    imgs = self.store.get_gen_job_images(j["id"])
                    done = sum(1 for i in imgs if i["status"] == "done")
                    fail = sum(1 for i in imgs if i["status"] == "failed")
                    run = sum(1 for i in imgs if i["status"] == "running")
                    summaries.append({
                        "job_id": j["id"], "status": j["status"],
                        "target": j["target"],
                        "total": j["total"] or len(imgs),
                        "succeeded": done, "failed": fail, "running": run,
                        "created_at": j.get("created_at"),
                        "updated_at": j.get("updated_at"),
                    })
                out[str(did)] = summaries
        return {"jobs": out}

    def copy_images_to_draft(self, draft_id, image_urls, target_draft_ids):
        if not image_urls:
            raise ValueError("未选择图片")
        targets = [int(t) for t in (target_draft_ids or []) if int(t)]
        if not targets:
            raise ValueError("未指定目标变体")
        src = self.store.get_draft(draft_id)
        if src is None:
            raise KeyError(f"draft {draft_id} not found")
        vg_src = str((src.get("source_raw") or {}).get("variant_group") or "")
        for tid in targets:
            tgt = self.store.get_draft(tid)
            if tgt is None:
                raise KeyError(f"draft {tid} not found")
            vg_tgt = str((tgt.get("source_raw") or {}).get("variant_group") or "")
            if vg_src and vg_src != vg_tgt:
                raise ValueError("只能在同一变体组内复制图片")
        added = self.store.copy_images(draft_id, image_urls, targets)
        return {"ok": True, "added": added}

    def gallery_add(self, draft_id, image_ids):
        self.store.gallery_add(int(draft_id), [int(i) for i in (image_ids or [])])
        return self.store.get_draft(int(draft_id))

    def gallery_remove(self, draft_id, image_ids):
        self.store.gallery_remove(int(draft_id), [int(i) for i in (image_ids or [])])
        return self.store.get_draft(int(draft_id))

    def gallery_reorder(self, draft_id, image_ids):
        self.store.gallery_reorder(int(draft_id), [int(i) for i in (image_ids or [])])
        return self.store.get_draft(int(draft_id))

    def gallery_delete(self, draft_id, image_id):
        self.store.gallery_delete(int(draft_id), int(image_id))
        return self.store.get_draft(int(draft_id))
