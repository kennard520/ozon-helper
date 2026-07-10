from __future__ import annotations

import re
from urllib.parse import urlparse

from ozon_common.oss import OssClient
from webui.services._helpers import _money_to_float, _to_int

WB_PRICE_RULE = "cny_x3_sale_old_x3_v2"
WB_PRICE_RULE_LEGACY = "cny_x3_v1"
_WB_VIDEO_NM_RE = re.compile(r"/(\d+)/mp4/", re.IGNORECASE)
_WB_CATALOG_NM_RE = re.compile(r"/catalog/(\d+)", re.IGNORECASE)


def _scale_money_text(value, multiplier: float) -> str:
    try:
        n = float(str(value or "").strip())
    except (TypeError, ValueError):
        n = 0.0
    if n <= 0:
        return ""
    out = round(n * multiplier, 2)
    return str(int(out)) if float(out).is_integer() else str(out)


def _normalize_wb_price_rule(scraped: dict, incoming_source_raw: dict) -> bool:
    if incoming_source_raw.get("wb_price_rule") in {WB_PRICE_RULE, WB_PRICE_RULE_LEGACY}:
        sale = _scale_money_text(scraped.get("price"), 1)
    else:
        sale = _scale_money_text(scraped.get("price"), 3)
    if not sale:
        return False
    old = _scale_money_text(sale, 3)
    changed = scraped.get("price") != sale or scraped.get("old_price") != old
    scraped["price"] = sale
    scraped["old_price"] = old
    return changed


def _build_wb_rich_content_from_images(images: object) -> dict | None:
    urls = [str(u or "").strip() for u in (images or []) if str(u or "").strip()] if isinstance(images, list) else []
    if not urls:
        return None
    from webui.listing_build import build_rich_content  # noqa: PLC0415
    return build_rich_content(urls)


def _wb_nm_from_collect_url(url: str) -> str:
    m = _WB_CATALOG_NM_RE.search(str(url or ""))
    return m.group(1) if m else ""


def _wb_video_matches_nm(video_url: object, nm: object) -> bool:
    url = str(video_url or "").strip()
    current_nm = str(nm or "").strip()
    if not url or not current_nm:
        return True
    m = _WB_VIDEO_NM_RE.search(urlparse(url).path)
    return not m or m.group(1) == current_nm


def _oss_key_from_public_url(url: str, oss: OssClient) -> str:
    u = str(url or "").strip()
    if not u:
        return ""
    if u.startswith("ozon-media/"):
        return u
    bases = [
        str(getattr(oss, "public_base", "") or "").rstrip("/"),
        f"https://{oss.bucket_name}.{oss.endpoint}".rstrip("/"),
    ]
    for base in [b for b in bases if b]:
        if u.startswith(base + "/"):
            return u[len(base) + 1:]
    path = urlparse(u).path.lstrip("/")
    return path if path.startswith("ozon-media/") else ""


class ExtMixin:
    """插件桥接 / 采集 / 媒体异步上传。"""

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

    def _promote_wb_images_to_gallery(self, draft_id: int, draft: dict) -> None:
        if str((draft or {}).get("source_platform") or "").strip().lower() != "wb":
            return
        images = [str(u or "").strip() for u in ((draft or {}).get("images") or []) if str(u or "").strip()]
        if not images:
            return
        source_raw = (draft or {}).get("source_raw")
        source_raw = source_raw if isinstance(source_raw, dict) else {}
        image_types = source_raw.get("image_types")
        image_types = image_types if isinstance(image_types, dict) else {}
        local_images = list((draft or {}).get("local_images") or [])
        for i, img_url in enumerate(images):
            self.store.add_draft_image(
                draft_id,
                img_url,
                type=str(image_types.get(img_url) or ""),
                source="collected",
                in_gallery=1,
                local_url=str(local_images[i] or "") if i < len(local_images) else "",
            )

    def ext_collect_parsed(self, payload: dict) -> dict:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise ValueError("url required")
        schema_version = str(payload.get("schema_version") or "").strip()
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
        incoming_sr = data.get("source_raw")
        incoming_sr = incoming_sr if isinstance(incoming_sr, dict) else {}
        if platform == "wb":
            current_nm = (
                incoming_sr.get("nm_id")
                or incoming_sr.get("sku_id")
                or data.get("nm_id")
                or data.get("sku_id")
                or _wb_nm_from_collect_url(url)
            )
            if not _wb_video_matches_nm(scraped.get("video_url"), current_nm):
                scraped["video_url"] = ""
                incoming_sr = {**incoming_sr, "video_url": "", "has_video": False}
        wb_price_rule_applied = platform == "wb" and _normalize_wb_price_rule(scraped, incoming_sr)
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
        rcj = data.get("rich_content_json") or incoming_sr.get("rich_content_json") or None
        if not rcj and platform == "wb":
            rcj = _build_wb_rich_content_from_images(scraped.get("images"))
        vars_ = data.get("variants") or []
        vg = data.get("variant_group") or ""
        sa = data.get("selected_aspects") or []
        sr_new: dict = {}
        if schema_version:
            sr_new["collect_schema_version"] = schema_version
        # 插件可直接带 source_raw（如 WB 的 options/brand_name，喂 auto-map/AI）
        if incoming_sr:
            sr_new.update(incoming_sr)
        if platform == "wb" and (wb_price_rule_applied or incoming_sr.get("wb_price_rule") == WB_PRICE_RULE):
            sr_new["wb_price_rule"] = WB_PRICE_RULE
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
            for k in ("ozon_title", "description", "price", "old_price",
                      "video_url", "weight_g", "length_mm", "width_mm", "height_mm",
                      "category_id", "type_id"):
                cur = existing.get(k)
                is_empty = cur in (None, "", 0) or (isinstance(cur, list) and not cur)
                val = new_draft.get(k)
                has_val = val not in (None, "", 0) and not (isinstance(val, list) and not val)
                if is_empty and has_val:
                    patch[k] = val
            ex_sr_for_price = existing.get("source_raw")
            ex_sr_for_price = ex_sr_for_price if isinstance(ex_sr_for_price, dict) else {}
            if (
                platform == "wb"
                and wb_price_rule_applied
                and (
                    existing.get("price") != new_draft.get("price")
                    or existing.get("old_price") != new_draft.get("old_price")
                    or ex_sr_for_price.get("wb_price_rule") != WB_PRICE_RULE
                )
            ):
                patch["price"] = new_draft.get("price")
                patch["old_price"] = new_draft.get("old_price")
            if sr_new:
                ex_sr = existing.get("source_raw")
                if not isinstance(ex_sr, dict):
                    ex_sr = {}
                merged = dict(ex_sr)
                for kk, vv in sr_new.items():
                    if kk == "wb_price_rule" or not merged.get(kk):  # 旧草稿没有才补；价格规则允许升级
                        merged[kk] = vv
                if platform == "wb" and sr_new.get("rich_content_json"):
                    merged["rich_content_json"] = sr_new["rich_content_json"]
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
            image_types = (new_draft.get("source_raw") or {}).get("image_types")
            image_types = image_types if isinstance(image_types, dict) else {}
            existing_urls = {str(m.get("url") or "") for m in (existing.get("materials") or [])}
            local_images = list(new_draft.get("local_images") or [])
            for i, raw_url in enumerate(new_draft.get("images") or []):
                img_url = str(raw_url or "").strip()
                if not img_url or img_url in existing_urls:
                    continue
                self.store.add_draft_image(
                    existing["id"],
                    img_url,
                    type=str(image_types.get(img_url) or "其他"),
                    source="collected",
                    in_gallery=0,
                    local_url=str(local_images[i] or "") if i < len(local_images) else "",
                )
            self._promote_wb_images_to_gallery(existing["id"], new_draft)
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
        self._promote_wb_images_to_gallery(saved["id"], new_draft)
        saved = self.store.get_draft(saved["id"]) or saved
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
        oss = OssClient(self.store.get_settings())
        missing: list[str] = []
        if oss.configured():
            for url in dict(media_map).values():
                key = _oss_key_from_public_url(str(url or ""), oss)
                if key and not oss.object_exists(key):
                    missing.append(key)
        if missing:
            sample = missing[0]
            more = f" 等 {len(missing)} 个" if len(missing) > 1 else ""
            raise ValueError(f"OSS 媒体尚未上传完成或对象不存在：{sample}{more}，请稍后重试上传")
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
