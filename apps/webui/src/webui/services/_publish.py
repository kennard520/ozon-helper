"""PublishMixin —— 发布/上架/拉 Ozon 商品/变体组发布/FBS 标签。"""
from __future__ import annotations

import time

import webui.media as _media
from webui.draft_state import blocking_errors, build_draft_checks, warning_messages
from webui.drafts import (
    loads_json,
    missing_required_attributes,
    to_ozon_import_item,
    video_publish_skip_reason,
)
from webui.media_rehost import needs_rehost, rehost_draft_media, rewrite_item_media
from webui.ozon_client_adapter import get_import_info
from webui.services._helpers import _has_cjk, _to_int


def _invalid_publish_media_urls(item: dict, settings: dict) -> list[str]:
    """Return media URLs that would still be invalid for Ozon after final rewrite."""
    rewritten = rewrite_item_media(item, settings)
    bad: list[str] = []
    for url in rewritten.get("images") or []:
        u = str(url or "").strip()
        if u and not u.lower().startswith("https://"):
            bad.append(u)
    return bad


class PublishMixin:
    def batch_publish(self, ids: list, store_client_id: str | None = None) -> dict:
        """批量发布：逐个调 publish（各自校验/扣费/媒体托管），单个失败不影响其它。
        返回 {results:[{id, published, errors}], published, failed}。"""
        results = []
        ok = 0
        for did in ids or []:
            try:
                r = self.publish(int(did), store_client_id)
                published = bool(r.get("published"))
                if published:
                    ok += 1
                results.append({"id": did, "published": published,
                                "errors": r.get("errors") or [], "warnings": r.get("warnings") or []})
            except Exception as exc:  # noqa: BLE001
                results.append({"id": did, "published": False, "errors": [str(exc)]})
        return {"results": results, "published": ok, "failed": len(results) - ok}

    def translate_draft(self, draft_id: int) -> dict:
        from webui.translate import get_engine  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        run = self.store.create_task_run(
            draft_id,
            "translate",
            status="running",
            progress_total=1,
            source="webui",
            result={"phase": "start"},
        )
        settings = self.store.get_settings()
        from webui.settings_migrate import ai_config, migrate_ai  # noqa: PLC0415
        _tm = migrate_ai(settings)["translate_mode"]
        # ai translate_mode 需要 key；无 key 时降级 manual（避免抛 RuntimeError）
        if _tm == "ai" and not ai_config(settings, "text")["key"]:
            _tm = "manual"
        engine = get_engine(_tm, settings)
        title = engine.translate(str(draft.get("ozon_title") or ""))
        desc = engine.translate(str(draft.get("description") or ""))
        updated = self.store.update_draft(draft_id, {"ozon_title": title, "description": desc})
        still = _has_cjk(title) or _has_cjk(desc)
        note = "" if not still else "仍含中文：manual 引擎只占位，请配置 remote 引擎或手动翻译"
        self.store.update_task_run(
            run["id"],
            {"status": "done", "progress_current": 1, "result": {"phase": "done", "engine": engine.name, "still_cjk": still}},
        )
        return {"draft": updated, "engine": engine.name, "still_cjk": still, "note": note}

    def _validate_and_build_item(self, draft: dict, store_settings: dict | None = None) -> tuple[list[str], list[str], dict | None]:
        """共享校验 + item 构建逻辑（publish 与 publish_preview 共用）。

        返回 (errors, warnings, item)：
        - errors: 技术性阻断错误列表；非空时 item 为 None
        - warnings: 发布前风险提示；不阻断用户继续发布
        - item: to_ozon_import_item 产出 + 币种换算后的 import item（pre-media-swap）

        注意：
        - 此方法不写 DB（不改 status、不写 validation_errors）——由调用方决定是否持久化
        - 媒体上传不在此方法里发生；media 检测仅验证 company_id / is_logged_in（is_ok 检查）
        - 返回的 item 仍使用 draft 里的原始 media URL（未上传替换），仅供预览；
          publish 会在校验通过后自行完成 upload + swap
        """
        checks = build_draft_checks(draft)
        warnings: list[str] = [*blocking_errors(checks), *warning_messages(checks)]
        source_raw = draft.get("source_raw") or {}
        if isinstance(source_raw, str):
            source_raw = loads_json(source_raw, {})
        ozon_sync = source_raw.get("ozon_sync") if isinstance(source_raw, dict) else {}
        variant_warning = (
            ozon_sync.get("variant_warning") if isinstance(ozon_sync, dict) else None
        )
        if variant_warning:
            warnings.append(str(variant_warning))
        technical_errors: list[str] = []
        video_warning = video_publish_skip_reason(draft.get("video_url"), draft.get("source_raw"))
        if video_warning:
            warnings.append(video_warning)
        # 1688 来源若标题/描述仍含中文，说明还没本地化（功能③的 AI 中译俄）——提示但允许继续
        if draft.get("source_platform") == "1688" and (
            _has_cjk(draft.get("ozon_title")) or _has_cjk(draft.get("description"))
        ):
            warnings.append("1688 商品未本地化（标题/描述仍含中文），Ozon 可能拒绝")
        # 类目必填属性：缺了只警告、不阻断——发到 Ozon 后在后台补(Ozon 卡片好编辑)
        cat, typ = str(draft.get("category_id") or "").strip(), str(draft.get("type_id") or "").strip()
        if cat and typ:
            try:
                attrs = self._category_attrs(int(cat), int(typ))
                for m in missing_required_attributes(draft, attrs):
                    warnings.append(f"缺必填属性：{m['name']}")
            except ValueError:
                pass  # 未配置 API key 等：不阻断
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"类目必填属性校验失败，无法确认是否缺失（可继续发布）：{exc}")
        # 合同货币汇率校验
        settings = store_settings if store_settings is not None else self.store.get_settings()
        currency = str(settings.get("contract_currency") or "CNY").upper()
        if currency == "RUB" and not settings.get("rub_cny"):
            technical_errors.append("未配置 RUB/CNY 汇率，无法换算合同币价格，请先在设置里填写汇率")
        if technical_errors:
            return technical_errors, warnings, None
        # 构建 item（用原始 URL，不做 upload/swap）
        try:
            item = to_ozon_import_item(draft, validate=False)
        except Exception as exc:  # noqa: BLE001
            return [f"发布 payload 构建失败：{exc}"], warnings, None
        # 内部 price/old_price 统一为 CNY 人民币。
        if currency == "RUB":
            # 合同币种=卢布 → CNY 换算成 RUB（rub_cny = CNY/RUB）
            rate = float(settings.get("rub_cny"))
            item["currency_code"] = "RUB"
            item["price"] = str(round(float(item["price"] or 0) / rate, 2))
            if item.get("old_price"):
                item["old_price"] = str(round(float(item["old_price"]) / rate, 2))
        else:
            # 合同币种=CNY → 价格已是人民币，直接发，不换算
            item["currency_code"] = currency
        return [], warnings, item

    def publish_preview(self, draft_id: int, store_client_id: str | None = None) -> dict:
        """预览将要发布的内容，不发送任何请求，不写 DB（无副作用）。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        target_store = str(draft.get("store_client_id") or "") or store_client_id
        errors, warnings, item = self._validate_and_build_item(draft, self._settings_for_store(target_store))
        checks = self.publish_preflight(draft_id)["checks"]
        if errors:
            return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks, "summary": None}
        # 构建摘要（item 已含换算后价格）
        images = item.get("images") or []
        attributes = item.get("attributes") or []
        has_video = bool(item.get("complex_attributes"))
        summary = {
            "offer_id": item.get("offer_id"),
            "name": item.get("name"),
            "description_len": len(str(item.get("description_category_id") and draft.get("description") or "")),
            "category_id": item.get("description_category_id"),
            "type_id": item.get("type_id"),
            "price": item.get("price"),
            "old_price": item.get("old_price"),
            "currency_code": item.get("currency_code"),
            "dims_mm": {
                "depth": item.get("depth"),
                "width": item.get("width"),
                "height": item.get("height"),
            },
            "weight_g": item.get("weight"),
            "images_count": len(images),
            "attributes_count": len(attributes),
            "has_video": has_video,
        }
        return {"ok": True, "errors": [], "warnings": warnings, "checks": checks, "summary": summary}

    def publish_preflight(self, draft_id: int) -> dict:
        """发布前核对清单：error=硬拦(不让发) / warn=建议 / verify=看图识别需人工核对 / passed=已就绪。
        硬拦复用 validate_draft;软项=尺寸密度警告 + 理解层标'图片识别'的数字 + 标题长度/图片数。"""
        from webui.drafts import loads_json  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = sr if isinstance(sr, dict) else {}
        und = sr.get("understanding") if isinstance(sr.get("understanding"), dict) else {}
        conf = und.get("confidence") if isinstance(und.get("confidence"), dict) else {}
        specs = und.get("specs") if isinstance(und.get("specs"), dict) else {}

        checks: list = [c.as_dict() for c in build_draft_checks(draft)]
        for key, c in conf.items():                            # 🟡 看图识别·待核对的数字(只列 specs 里有值的)
            if str(c) == "图片识别" and str(key).startswith("specs."):
                field = str(key).split(".", 1)[1]
                val = specs.get(field, "")
                if str(val).strip():
                    msg = f"核对 {field}: {val}（看图识别,易错,发布前请确认）"
                    checks.append({
                        "severity": "verify",
                        "label": msg,
                        "message": msg,
                        "code": "vision_verify",
                        "field": field,
                        "step": "details",
                        "fix_action": "review_specs",
                    })
        title = str(draft.get("ozon_title") or "")
        if len(title) > 150:
            msg = f"标题偏长({len(title)} 字),建议精简到 150 内"
            checks.append({
                "severity": "warn",
                "label": msg,
                "message": msg,
                "code": "title_too_long",
                "field": "ozon_title",
                "step": "content",
                "fix_action": "edit_title",
            })
        imgs = draft.get("images") or []
        if len(imgs) < 3:
            msg = f"图片偏少({len(imgs)} 张),Ozon 建议多张主图/细节"
            checks.append({
                "severity": "warn",
                "label": msg,
                "message": msg,
                "code": "few_images",
                "field": "images",
                "step": "media",
                "fix_action": "add_images",
            })

        passed: list = []
        if title and not any("标题" in c["label"] for c in checks if c["severity"] == "error"):
            passed.append(f"标题就绪({len(title)} 字)")
        if str(draft.get("brand_name") or "") == "Нет бренда":
            passed.append("品牌 = 无品牌 ✓")
        try:
            if float(draft.get("price") or 0) > 0:
                passed.append(f"售价 {draft.get('price')} ✓")
        except (TypeError, ValueError):
            pass
        if (draft.get("weight_g") or 0) and (draft.get("length_mm") or 0):
            passed.append("尺寸/重量已填 ✓")

        blocking = 1 if str(draft.get("media_status") or "done") == "pending" else 0
        risks = [c for c in checks if c.get("severity") in {"error", "warn", "verify"}]
        return {"ok": True, "checks": checks, "passed": passed,
                "risks": risks, "blocking": blocking, "can_publish": blocking == 0}

    def publish(self, draft_id: int, store_client_id: str | None = None) -> dict:
        import webui.app_service as _app_svc  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        publish_run = self.store.create_task_run(
            draft_id,
            "publish",
            status="running",
            progress_total=3,
            source="webui",
            result={"phase": "start"},
        )
        if str(draft.get("media_status") or "done") == "pending":
            self.store.update_task_run(
                publish_run["id"],
                {"status": "failed", "error": "媒体还在上传，请稍候再发布", "progress_current": 0},
            )
            raise ValueError("图片还在上传，请稍候再发布")
        # 草稿绑定店：优先发到草稿自带店；旧草稿(无 store_client_id)回退入参/默认店
        target_store = str(draft.get("store_client_id") or "") or store_client_id
        store_settings = self._settings_for_store(target_store)
        # 写死：品牌=无品牌、原产国=中国(覆盖任何采集/AI 值；要改去 Ozon 后台改)
        draft = self._ensure_fixed_attrs(draft)
        # 媒体托管：插件已把媒体传到卖家自己的 Ozon 店铺(ir.ozone.ru)时，全是 Ozon 原生链接、
        # 无需 OSS——跳过。只有存在非 Ozon 媒体(老路径/手动加图)时才用 OSS 兜底；未配 OSS 才硬拦。
        oss = _app_svc.OssClient(store_settings, local_reader=_media.read_media_bytes)
        rehost_stats = {"uploaded": 0, "failed": 0}
        if needs_rehost(draft):
            if not oss.configured():
                errs = ["有非 Ozon 来源的图片/视频需托管：请用插件把媒体传到你的 Ozon 店铺，或在设置里配置阿里云 OSS"]
                updated = self.store.update_draft(draft_id, {"status": "invalid", "validation_errors": errs})
                self.store.update_task_run(
                    publish_run["id"],
                    {"status": "failed", "error": errs[0], "progress_current": 1, "result": {"phase": "media"}},
                )
                return {"published": False, "draft": updated, "errors": errs}
            draft, rehost_stats = rehost_draft_media(draft, oss.upload_remote)
            # OSS URL 持久化回草稿（再发幂等；展示也变 OSS 图）
            self.store.update_draft(draft_id, {
                "images": draft.get("images") or [], "video_url": draft.get("video_url") or "",
                "source_raw": draft.get("source_raw") or {}})
        errors, warnings, item = self._validate_and_build_item(draft, store_settings)
        if errors:
            updated = self.store.update_draft(draft_id, {"status": "invalid", "validation_errors": errors})
            self.store.update_task_run(
                publish_run["id"],
                {"status": "failed", "error": errors[0], "progress_current": 1, "result": {"phase": "preflight", "errors": errors}},
            )
            return {"published": False, "draft": updated, "errors": errors, "warnings": warnings}
        if rehost_stats.get("failed"):
            errs = [f"{rehost_stats['failed']} 个媒体未能上传到 OSS，已停止发布，避免把无效图片 URL 提交给 Ozon"]
            updated = self.store.update_draft(draft_id, {"status": "invalid", "validation_errors": errs})
            self.store.update_task_run(
                publish_run["id"],
                {"status": "failed", "error": errs[0], "progress_current": 1, "result": {"phase": "media", "rehost": rehost_stats}},
            )
            return {"published": False, "draft": updated, "errors": errs, "warnings": [*warnings, *errs], "rehost": rehost_stats}
        bad_urls = _invalid_publish_media_urls(item, store_settings)
        if bad_urls:
            shown = bad_urls[0]
            more = f" 等 {len(bad_urls)} 个" if len(bad_urls) > 1 else ""
            errs = [f"图片 URL 不是 Ozon 可抓取的 HTTPS 公网地址{more}：{shown}。请重新上传图片或检查 OSS 公网地址配置"]
            updated = self.store.update_draft(draft_id, {"status": "invalid", "validation_errors": errs})
            self.store.update_task_run(
                publish_run["id"],
                {"status": "failed", "error": errs[0], "progress_current": 1, "result": {"phase": "media", "bad_urls": bad_urls[:5]}},
            )
            return {"published": False, "draft": updated, "errors": errs, "warnings": warnings, "rehost": rehost_stats}
        # 发布扣费（publish_fee>0 才扣；余额不足直接拦下不发布）
        fee = self.publish_fee()
        if fee > 0 and not self.store.deduct(fee, biz_no=f"publish:{draft_id}", remark="发布商品"):
            errs = ["余额不足，请先充值后再发布"]
            updated = self.store.update_draft(draft_id, {"status": "invalid", "validation_errors": errs})
            self.store.update_task_run(
                publish_run["id"],
                {"status": "failed", "error": errs[0], "progress_current": 1, "result": {"phase": "billing"}},
            )
            return {"published": False, "draft": updated, "errors": errs, "warnings": warnings}
        self.store.update_draft(draft_id, {"status": "publishing", "validation_errors": []})
        self.store.update_task_run(
            publish_run["id"],
            {"status": "running", "progress_current": 1, "result": {"phase": "ozon_submit"}},
        )
        try:
            response = _app_svc.publish_items(store_settings, [item])
        except Exception as exc:  # noqa: BLE001  Ozon 报错(如图片URL无效)别透成 500，落库+回前端
            if fee > 0:  # 调用失败把刚扣的费退回，不白扣
                self.store.refund(fee, biz_no=f"publish-refund:{draft_id}", remark="发布失败退款")
            msg = f"Ozon 拒收: {exc}"
            updated = self.store.update_draft(draft_id, {"status": "failed", "validation_errors": [msg]})
            self.store.update_task_run(
                publish_run["id"],
                {"status": "failed", "error": msg, "progress_current": 2, "result": {"phase": "ozon_submit"}},
            )
            return {"published": False, "draft": updated, "errors": [msg], "warnings": warnings}
        self.store.save_settings({"last_publish_store": str(store_settings.get("ozon_client_id") or "")})
        task_id = ((response.get("result") or {}).get("task_id"))
        self.store.update_task_run(
            publish_run["id"],
            {
                "status": "running",
                "progress_current": 2,
                "source": "ozon_import",
                "external_id": task_id,
                "result": {"phase": "ozon_poll", "task_id": task_id, "import": response},
            },
        )
        poll: dict = {}
        final_status = "draft"
        item_errors: list[str] = []
        if task_id:
            for _ in range(10):
                time.sleep(2)
                try:
                    info = get_import_info(store_settings, task_id)
                except Exception as exc:  # noqa: BLE001
                    poll = {"error": str(exc)}
                    break
                poll_items = (info.get("result") or {}).get("items") or []
                statuses = [it.get("status") for it in poll_items]
                if statuses and not any(s in ("pending", "not_started", "") for s in statuses):
                    poll = info
                    # ⚠️ Ozon 即使 status='imported' 也可能带 level='error' 的错误：卡片建了(有 product_id)
                    # 但不可售(如必填属性空)，不会出现在后台正常商品里。有 error 级错误 → 视为失败，
                    # 并把 Ozon 的具体原因带回前端，否则会误报"已发布"而后台实际没有。
                    for it in poll_items:
                        for e in (it.get("errors") or []):
                            if str(e.get("level") or "").lower() == "error":
                                aid = e.get("attribute_id")
                                desc = str(e.get("description") or e.get("code") or "未知错误")
                                item_errors.append(f"[属性{aid}] {desc}" if aid else desc)
                    # skipped = Ozon 跳过(变体单条发常见：变体须走「整组发布」；或内容无变化)。
                    # 既非成功也非失败，单独标记并提示，避免误报"已发布"或"失败"。
                    if statuses and all(s == "skipped" for s in statuses) and not item_errors:
                        final_status = "skipped"
                        item_errors.append("Ozon 跳过未更新：若是变体商品请用「整组发布」；单品则说明内容无变化")
                        break
                    ok = all(s in ("imported", "skipped") for s in statuses) and not item_errors
                    final_status = "published" if ok else "failed"
                    break
            else:
                poll = {"warning": "poll timeout — Ozon 仍在异步处理，稍后用 task_id 查"}
        updated = self.store.update_draft(draft_id, {
            "status": final_status,
            "validation_errors": item_errors or None,
            "publish_response": {"import": response, "poll": poll, "warnings": warnings,
                                 "store_client_id": str(store_settings.get("ozon_client_id") or ""),
                                 "rehost": rehost_stats},
            "offer_id": item["offer_id"],
        })
        if fee > 0 and final_status == "failed":   # Ozon 校验没过、卡片不可售 → 退发布费
            self.store.refund(fee, biz_no=f"publish-refund:{draft_id}", remark="发布未成功(Ozon 校验)退款")
        task_status = "done" if final_status == "published" else final_status
        if final_status == "draft" and poll.get("warning"):
            task_status = "running"
        self.store.update_task_run(
            publish_run["id"],
            {
                "status": task_status,
                "progress_current": 3 if task_status in {"done", "failed", "skipped"} else 2,
                "error": (item_errors[0] if item_errors else poll.get("error")),
                "result": {
                    "phase": "done" if task_status in {"done", "failed", "skipped"} else "ozon_poll",
                    "task_id": task_id,
                    "import": response,
                    "poll": poll,
                    "warnings": warnings,
                },
            },
        )
        return {"published": final_status == "published", "draft": updated, "response": response,
                "poll": poll, "task_id": task_id, "warnings": warnings, "rehost": rehost_stats,
                "errors": item_errors}

    def pull_ozon_products(
        self,
        visibility: str = "ALL",
        store_client_id: str | None = None,
    ) -> dict:
        """兼容旧调用顺序：visibility 在前，店铺 ID 在后。"""
        settings = self._settings_for_store(store_client_id)
        scid = str(store_client_id or settings.get("ozon_client_id") or "").strip()
        return self.sync_ozon_products(scid, visibility)

    def _auto_map_safe(self, draft_id: int) -> None:
        """采集后尽力自动映射属性(类目对上才有效)：把采集的名值对填进 Ozon 上架属性。
        无网/无key/无类目/失败都静默跳过，绝不阻断采集。"""
        try:
            d = self.store.get_draft(draft_id)
            if d and str(d.get("category_id") or "").strip() and str(d.get("type_id") or "").strip():
                self.map_attributes(draft_id)
        except Exception:  # noqa: BLE001
            pass

    def _media_needs_upload(self, draft: dict) -> bool:
        """草稿里是否还有未传到我们 OSS 的媒体（需后台上传 → media_status=pending）。
        插件同步流已把图直传 OSS（URL 在 oss_public_base 下）→ 不需要 → done；
        计划三异步流推原始 ir.ozone.ru 链接 → 需要 → pending。
        没配 oss_public_base 时，有媒体即按 pending（兼容旧行为/媒体异步测试）。
        两池化后采集图进 materials(in_gallery=0),需同时检查素材 URL。"""
        base = str((self.store.get_settings() or {}).get("oss_public_base") or "").rstrip("/")
        # 图集 URL(images) + 素材 URL(materials) 都检查
        urls = list(draft.get("images") or [])
        for m in draft.get("materials") or []:
            mu = str(m.get("url") or "").strip()
            if mu and mu not in urls:
                urls.append(mu)
        v = str(draft.get("video_url") or "").strip()
        if v:
            urls.append(v)
        urls = [str(u).strip() for u in urls if str(u or "").strip()]
        if not urls:
            return False
        return any(not (base and u.startswith(base)) for u in urls)

    def _maybe_auto_publish(self, draft_id: int) -> None:
        """采集/媒体就绪后，若用户开了 auto_publish 且草稿可发，则后台发布到 Ozon。
        守卫：开关开 + 草稿存在 + status!=published（幂等）+ media_status!=pending（等媒体）。
        best-effort：整段吞异常，发不出去的草稿原样留 webui 等人工。"""
        try:
            if not bool((self.store.get_settings() or {}).get("auto_publish")):
                return
            draft = self.store.get_draft(draft_id)
            if draft is None:
                return
            if str(draft.get("status") or "") == "published":
                return
            if str(draft.get("media_status") or "done") == "pending":
                return
            self._dispatch_auto_publish(draft_id)
        except Exception:  # noqa: BLE001
            pass

    def _dispatch_auto_publish(self, draft_id: int) -> None:
        """派发后台线程跑 publish()，不阻塞采集（publish 会轮询 Ozon ~20s）。
        复制父线程 context 把 current_user_id 带进子线程（否则用错 Ozon 凭证）。
        抽成单独方法：测试 monkeypatch 本方法即可同步断言、不起真线程。"""
        import contextvars  # noqa: PLC0415
        import threading  # noqa: PLC0415
        ctx = contextvars.copy_context()

        def _run() -> None:
            try:
                ctx.run(self.publish, draft_id)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_run, daemon=True).start()

    def publish_variant_group(
        self,
        variant_group: str,
        store_client_id: str | None = None,
        model_name: str | None = None,
    ) -> dict:
        """把同一 variant_group 的所有草稿合并成一张 Ozon 多变体卡批量发布（批量 import）。
        颜色/尺寸字典值通过 search_attribute_values 实时解析；型号名(9048)作合并 key。
        **不可逆外部写**，由路由层二次确认后调用。"""
        import webui.app_service as _app_svc  # noqa: PLC0415
        from webui.variant_publish import build_group_items  # noqa: PLC0415
        drafts = self.store.list_drafts_by_variant_group(variant_group)
        if not drafts:
            raise ValueError("该分组没有草稿")
        store_settings = self._settings_for_store(store_client_id)
        oss = _app_svc.OssClient(store_settings, local_reader=_media.read_media_bytes)
        rehost_totals = {"uploaded": 0, "failed": 0}
        rehosted_drafts: list[dict] = []
        for d in drafts:
            if needs_rehost(d):
                if not oss.configured():
                    raise ValueError("整组发布包含本地/非 Ozon 图片，需要先配置 OSS 或先把媒体上传成公网链接")
                nd, stats = rehost_draft_media(d, oss.upload_remote)
                rehost_totals["uploaded"] += int(stats.get("uploaded") or 0)
                rehost_totals["failed"] += int(stats.get("failed") or 0)
                if stats.get("failed"):
                    raise ValueError(f"草稿 {d.get('id')} 有 {stats['failed']} 个媒体上传 OSS 失败，已停止发布")
                self.store.update_draft(d["id"], {
                    "images": nd.get("images") or [],
                    "video_url": nd.get("video_url") or "",
                    "source_raw": nd.get("source_raw") or {},
                })
                rehosted_drafts.append(nd)
            else:
                rehosted_drafts.append(d)
        drafts = rehosted_drafts
        # 类目取第一条（同组同类目）
        first = drafts[0]
        cat = int(str(first.get("category_id") or "0") or 0)
        typ = int(str(first.get("type_id") or "0") or 0)
        if not cat or not typ:
            raise ValueError("草稿缺类目，无法合并发布（先在编辑器选类目/AI匹配）")
        category_attrs = self._category_attrs(cat, typ)
        # 型号名(合并 key)：默认用分组键(主 SKU)，保证组内一致→合并
        mname = (model_name or "").strip() or str(variant_group)

        # 变体维度：采集没给 selected_aspects 时，从各变体 spec_attrs 跨组推导(颜色/规格变化维度)，
        # 颜色值中文 → 翻成俄语(与俄语 listing 一致 + 能匹配 Ozon 颜色字典)，写回内存 selected_aspects。
        from webui.variant_publish import derive_group_aspects  # noqa: PLC0415
        if not any((d.get("source_raw") or {}).get("selected_aspects") for d in drafts):
            derived = derive_group_aspects(drafts)
            if derived:
                from webui.settings_migrate import ai_config, migrate_ai  # noqa: PLC0415
                from webui.translate import get_engine  # noqa: PLC0415
                _tm = migrate_ai(store_settings)["translate_mode"]
                if _tm == "ai" and not ai_config(store_settings, "text")["key"]:
                    _tm = "manual"
                _engine = get_engine(_tm, store_settings)
                _cache: dict[str, str] = {}

                def _ru(v: str) -> str:
                    v = (v or "").strip()
                    if not v or not _has_cjk(v):
                        return v
                    if v not in _cache:
                        try:
                            _cache[v] = (_engine.translate(v) or v).strip() or v
                        except Exception:  # noqa: BLE001
                            _cache[v] = v
                    return _cache[v]

                for d in drafts:
                    asp = derived.get(d.get("id")) or []
                    if not asp:
                        continue
                    sr = dict(d.get("source_raw") or {})
                    sr["selected_aspects"] = [{"aspect_key": a.get("aspect_key"),
                                               "value": _ru(a.get("value"))} for a in asp]
                    d["source_raw"] = sr

        def resolve_dict(attr_id: int, dictionary_id: int, text: str) -> dict | None:
            try:
                r = _app_svc.search_attribute_values(store_settings, cat, typ, int(attr_id), str(text), limit=5)
                vals = (r or {}).get("result") if isinstance(r, dict) else None
                vals = vals or []
                if vals:
                    v0 = vals[0]
                    vid = v0.get("id") or v0.get("dictionary_value_id")
                    if vid:
                        return {"dictionary_value_id": int(vid), "value": v0.get("value") or text}
            except Exception:  # noqa: BLE001
                return None
            return None

        items = build_group_items(drafts, category_attrs, mname, resolve_dict)
        # 币种换算（内部统一 CNY → 目标店币种；与 publish() 保持一致）
        currency = str(store_settings.get("contract_currency") or "CNY").upper()
        if currency == "RUB":
            rate = float(store_settings.get("rub_cny") or 0) or None
            if rate:
                for it in items:
                    it["currency_code"] = "RUB"
                    it["price"] = str(round(float(it.get("price") or 0) / rate, 2))
                    if it.get("old_price"):
                        it["old_price"] = str(round(float(it["old_price"]) / rate, 2))
        else:
            for it in items:
                it["currency_code"] = currency
        for idx, it in enumerate(items, start=1):
            bad_urls = _invalid_publish_media_urls(it, store_settings)
            if bad_urls:
                shown = bad_urls[0]
                more = f" 等 {len(bad_urls)} 个" if len(bad_urls) > 1 else ""
                raise ValueError(f"第 {idx} 个商品图片 URL 不是 Ozon 可抓取的 HTTPS 公网地址{more}：{shown}")
        response = _app_svc.publish_items(store_settings, items)
        return {
            "published": True,
            "count": len(items),
            "variant_group": variant_group,
            "model_name": mname,
            "rehost": rehost_totals,
            "response": response,
        }

    def fbs_label(self, posting_number: str, store_client_id: str | None = None) -> bytes:
        from webui.ozon_client_adapter import fbs_label_pdf  # noqa: PLC0415
        return fbs_label_pdf(self._settings_for_store(store_client_id), [posting_number])
