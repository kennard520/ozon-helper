"""CategoryMixin —— 类目/属性搜索 + 字典值解析 + 品牌搜索。"""
from __future__ import annotations

from webui.drafts import (
    BRAND_ATTR_ID,
    NO_BRAND,
    collected_chars,
    match_chars_to_attributes,
    missing_required_attributes,
    normalize_category_attrs,
    split_collection_value,
    validate_draft,
)
from webui.ozon_client_adapter import (
    build_client,
    get_attribute_values,
    get_category_attributes,
    search_attribute_values,
)
from webui.services._helpers import (
    _ATTR_EXCL,
    _DIM_KW,
    _VOL_KW,
    _WEIGHT_KW,
    _attr_language,
    _has_cjk,
    _is_country_attr,
    _is_manufacturer_attr,
    _to_int,
)


class CategoryMixin:
    def search_category(self, query: str, limit: int = 500) -> dict:
        # 本地缓存在就纯离线搜，不碰网络/不要求 API key；缓存为空才首次拉取
        client = None
        if not self.catalog.has_cache():
            client = build_client(self.store.get_settings())
        return {"results": self.catalog.search(client, query, limit=limit)}

    def category_tree(self) -> dict:
        # 本地缓存优先，无缓存才需 API key 首次拉取
        client = None
        if not self.catalog.has_tree_cache():
            client = build_client(self.store.get_settings())
        return {"tree": self.catalog.tree(client)}

    def resolve_category(self, cat_id: int, type_id: int) -> dict:
        # 按 ID 反查可读类目名（给前端回显用），本地缓存优先
        client = None
        if not self.catalog.has_cache():
            client = build_client(self.store.get_settings())
        leaf = self.catalog.find_leaf(client, cat_id, type_id)
        return {"leaf": leaf}

    def _auto_match_category(self, scraped: dict) -> None:
        """采集时按俄语类目路径自动猜 description_category_id + type_id。
        叶子名常有歧义(如 наушники=耳机/毛皮耳罩)，故取多候选、按候选完整路径与
        面包屑(含上级 Электроника/Одежда 等)的词重合度打分，选最吻合的那个消歧。"""
        path = str(scraped.get("category_path") or "").strip()
        if not path:
            return
        try:
            client = build_client(self.store.get_settings())
        except Exception:  # noqa: BLE001
            return  # 没配 key 就跳过
        segments = [s.strip() for s in path.split("/") if s.strip()]
        # 商品自己声明的「Тип(类型)」属性值——最精准的类型信号，优先用它搜
        type_seeds = [
            str(a.get("value")).strip()
            for a in (scraped.get("attributes") or [])
            if isinstance(a, dict) and str(a.get("name") or "").strip() in ("Тип", "Тип товара")
            and a.get("value")
        ]
        # 搜索种子：先 Тип 值(精准) → 再面包屑叶子往父回溯
        seeds = type_seeds + list(reversed(segments))
        if not seeds:
            return
        # 面包屑里所有词(俄语词形容错：长词去尾)，用于给候选路径打分消歧(电子 vs 服装)
        crumb_words = set()
        for s in segments:
            for w in s.lower().split():
                if len(w) >= 3:
                    crumb_words.add(w[:-1] if len(w) >= 5 else w)

        def _score(hit: dict) -> int:
            p = str(hit.get("path") or "").lower()
            return sum(1 for w in crumb_words if w in p)

        # 按种子顺序找，第一个有候选的种子那层选最佳(路径与面包屑域最吻合者)
        for seg in seeds:
            try:
                hits = self.catalog_ru.search(client, seg, limit=30)
            except Exception:  # noqa: BLE001
                return
            cands = [h for h in hits if h.get("description_category_id") and h.get("type_id")]
            if not cands:
                continue
            best = max(cands, key=_score)   # 路径与面包屑重合最多者(消歧)；并列取第一
            scraped["category_id"] = str(best["description_category_id"])
            scraped["type_id"] = str(best["type_id"])
            return

    def category_attributes(self, cat_id: int, type_id: int, language: str = "ZH_HANS") -> dict:
        lang = _attr_language(language)
        attrs = self._category_attrs(cat_id, type_id, language=lang)
        return {"result": attrs, "required": [a for a in attrs if a.get("is_required")], "language": lang}

    def _category_attrs(self, cat_id: int, type_id: int, language: str = "ZH_HANS") -> list[dict]:
        lang = _attr_language(language)
        # 本地优先：缓存命中直接用；没有再调 Ozon 拉取并写回缓存
        cached = self.store.load_category_attrs(cat_id, type_id, lang)
        # 旧缓存缺新增字段（description / category_dependent / is_aspect）→ 视为过期重拉。
        # category_dependent 用于排除"类型"；is_aspect 用于标出「区别特征」(变体维度)。
        if cached and not ("description" in cached[0] and "category_dependent" in cached[0]
                           and "is_aspect" in cached[0] and "max_value_count" in cached[0]):
            cached = None
        if cached is not None:
            return cached
        raw = get_category_attributes(self.store.get_settings(), cat_id, type_id, language=lang)
        attrs = normalize_category_attrs(raw)
        # 只缓存非空结果：空大概率是 API 抽风，缓存了会永久屏蔽必填校验
        if attrs:
            self.store.save_category_attrs(cat_id, type_id, attrs, lang)
        return attrs

    def required_check(self, draft_id: int, language: str = "ZH_HANS") -> dict:
        """结构校验 + 类目必填属性校验，给 UI 标记/提示用。"""
        lang = _attr_language(language)
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        errors = list(validate_draft(draft))
        required: list[dict] = []
        optional: list[dict] = []
        aspects: list[dict] = []
        missing: list[dict] = []
        cat, typ = str(draft.get("category_id") or "").strip(), str(draft.get("type_id") or "").strip()
        if cat and typ:
            try:
                attrs = self._category_attrs(int(cat), int(typ), language=lang)
                # 只排除「类型/Тип」这一个属性：它由 type_id 表达，单独填会显示一个填不了的"缺类型"。
                # ⚠️ 不能把所有 category_dependent 全删——「专为/颜色/材料/碗的类型」等真·必填/可选项
                # 也是 category_dependent(字典随类目变)，删了会导致必填项不显示、发布时被 Ozon 拒。
                attrs = [a for a in attrs if not (
                    a.get("category_dependent")
                    and str(a.get("name") or "").strip().lower() in ("类型", "тип", "type")
                )]
                # 品牌(85)写死「无品牌」、原产国写死「中国」、制造商写死 zqr——发布时强制填，
                # 不在属性区展示让用户填，要改自己去 Ozon 改。故从所有展示组里排除这些固定字段。
                attrs = [a for a in attrs if int(a.get("id") or 0) != 85
                         and not _is_country_attr(a) and not _is_manufacturer_attr(a)]
                # 「区别特征」(变体维度 is_aspect，如商品颜色)单列一组、置顶突出——合并成一张卡时
                # 各变体靠它区分，最关键，不该埋在折叠里。从必填/可选里拆出，避免重复展示。
                aspects = [a for a in attrs if a.get("is_aspect")]
                required = [a for a in attrs if a.get("is_required") and not a.get("is_aspect")]
                # 可选属性：非必填、非变体维度的全列出，供人工补充
                optional = [a for a in attrs if not a.get("is_required") and not a.get("is_aspect")]
                missing = missing_required_attributes(draft, attrs)
            except Exception as exc:  # noqa: BLE001
                # 没配 key / 拉取失败：不阻断，只提示
                return {"errors": errors, "required": [], "optional": [], "aspects": [], "missing": [],
                        "attr_warning": f"类目必填属性未校验：{exc}"}
        for m in missing:
            errors.append(f"缺必填属性：{m['name']}")
        return {"errors": errors, "required": required, "optional": optional, "aspects": aspects,
                "missing": missing, "language": lang}

    def _ensure_attr_values(self, cat: int, typ: int, attr_id: int,
                            language: str = "RU") -> tuple[list[dict], bool]:
        """确保本地有该属性的全部字典值。返回 (values, oversized)。
        命中缓存直接返回；未命中拉全量并存库；oversized 时 values 存空、走实时搜；
        拉取失败返回 ([], False)（不写缓存，调用方回退实时 search）。
        language：缓存按语言分别存(RU 用于发布时解析；ZH_HANS 用于前端下拉显示中文)。
        注：本方法使用「全量字典值缓存」(category_attr_values_cache 表, save/load_attr_values)，
        区别于前端 LIKE 模糊搜用的 attribute_values_cache 表 (save_attribute_values/find_attribute_values)。"""
        import webui.app_service as _app_svc  # noqa: PLC0415  延迟导入避免循环；测试可 patch _app_svc.get_attribute_values
        cached = self.store.load_attr_values(cat, typ, attr_id, language=language)
        if cached is not None:
            return cached
        try:
            out = _app_svc.get_attribute_values(self.store.get_settings(), cat, typ, attr_id,
                                       language=language, max_total=2000)
        except Exception:  # noqa: BLE001
            return ([], False)
        oversized = bool(out.get("oversized"))
        store_values: list[dict] = [] if oversized else (out.get("values") or [])
        self.store.save_attr_values(cat, typ, attr_id, store_values, oversized, language=language)
        return (store_values, oversized)

    def attribute_value_options(self, cat: int, typ: int, attr_id: int,
                                language: str = "ZH_HANS") -> dict:
        """某属性的**全量字典选项**(前端下拉用)：先查 DB 缓存，缺了拉 Ozon 全量并回写。
        oversized(字典过大>2000)时 values 为空、前端回退实时搜。"""
        lang = _attr_language(language)
        values, oversized = self._ensure_attr_values(int(cat), int(typ), int(attr_id), language=lang)
        opts = [{"id": int(v.get("id") or 0), "value": str(v.get("value") or "")}
                for v in (values or []) if int(v.get("id") or 0)]
        return {"values": opts, "oversized": oversized, "language": lang}

    @staticmethod
    def _local_match_value(values: list[dict], text: str) -> dict | None:
        """在缓存的字典值里按俄文精确匹配（strip+lower 相等）。
        命中返回 {"dictionary_value_id": id, "value": value}，否则 None。"""
        t = str(text or "").strip().lower()
        if len(t) < 2:
            return None
        for v in values:
            if str(v.get("value") or "").strip().lower() == t:
                vid = int(v.get("id") or 0)
                if vid:
                    return {"dictionary_value_id": vid, "value": str(v.get("value") or text)}
        return None

    def _resolve_values(self, cat: int, typ: int, attr_id: int, texts: list[str],
                        is_collection: bool) -> list[dict]:
        """把文本值解析成 Ozon 字典值 [{dictionary_value_id, value}]。
        **只走实时 search，不缓存俄文字典**(界面只缓存中文选项)——AI 出的属性值是俄文、
        且 Ozon 中文字典不全(如 薄荷绿/哑光白 中文库查无)，故匹配用实时搜，结果不落库。
        auto_map 已并发调用本方法，实时搜的额外耗时被并发摊平。"""
        out: list[dict] = []
        seen: set[int] = set()
        for t in (texts if is_collection else texts[:1]):
            if len(str(t).strip()) < 2:
                continue
            hit = self._search_one_value(cat, typ, attr_id, t)
            if not hit:
                continue
            vid = int(hit["dictionary_value_id"])
            if vid and vid not in seen:
                seen.add(vid)
                out.append({"dictionary_value_id": vid, "value": hit["value"]})
        return out

    def _search_one_value(self, cat: int, typ: int, attr_id: int, text: str) -> dict | None:
        """实时搜单个值（兜底）。精确优先，否则取第一个结果。失败/无结果返回 None。"""
        import webui.app_service as _app_svc  # noqa: PLC0415  延迟导入避免循环；测试可 patch _app_svc.search_attribute_values
        try:
            resp = _app_svc.search_attribute_values(self.store.get_settings(), cat, typ, attr_id, text, language="RU")
            res = resp.get("result") or []
        except Exception:  # noqa: BLE001
            return None
        if not res:
            return None
        t = str(text).strip().lower()
        hit = next((r for r in res if str(r.get("value") or "").strip().lower() == t), res[0])
        vid = _to_int(hit.get("id"))
        if not vid:
            return None
        return {"dictionary_value_id": vid, "value": str(hit.get("value") or text)}

    def _resolve_pairs_concurrent(self, cat: int, typ: int,
                                  tasks: list[tuple[int, list[str], bool]]) -> dict[int, list[dict]]:
        """并发解析多个字典属性的值。tasks = [(attr_id, texts, is_collection), ...]。
        返回 {attr_id: [{dictionary_value_id, value}, ...]}。本地命中不走网络，未命中并发实时搜。"""
        import contextvars  # noqa: PLC0415
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415
        if not tasks:
            return {}

        def _one(task: tuple[int, list[str], bool]) -> tuple[int, list[dict]]:
            aid, texts, is_coll = task
            return (aid, self._resolve_values(cat, typ, aid, texts, is_coll))

        # ThreadPoolExecutor 不会把父线程的 ContextVar(current_user_id)带进子线程，否则子线程
        # get_settings() 会拿到默认用户、用错 Ozon 凭证。给每个任务复制一份独立的父线程 context
        # （独立副本才能被多个子线程并发 run），在该 context 里执行解析。
        ctxs = [contextvars.copy_context() for _ in tasks]
        with ThreadPoolExecutor(max_workers=min(16, len(tasks))) as ex:
            return dict(ex.map(lambda c, t: c.run(_one, t), ctxs, tasks))

    def recognize_category(self, draft_id: int) -> dict:
        """AI 识别 Ozon 类别(description_category_id + type_id)并写入草稿。
        **特征是按类别来的**，故这是「特征值识别(auto_map)」的前置步骤。
        复用 navigate_category(只做类别下钻)，比「智能草案」轻——不生成文案/属性。
        没看图理解(understanding)就先自动跑一遍——靠外观判类目的品类(纯文本太薄)会更准。"""
        from webui.ai_card import build_profile, navigate_category  # noqa: PLC0415
        from webui.drafts import loads_json  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        raw = draft.get("source_raw")
        if isinstance(raw, str):
            raw = loads_json(raw, {})
        raw = dict(raw or {})
        und_auto = False
        is_wb_structured = str(draft.get("source_platform") or raw.get("source_platform") or "").strip().lower() == "wb"
        skip_understand = is_wb_structured and bool(raw.get("options") or raw.get("grouped_options") or raw.get("subj_name"))
        if not skip_understand and not (isinstance(raw.get("understanding"), dict) and raw.get("understanding")):
            # 没看图理解就先做一次(无图/失败则静默跳过，仍按纯文本下钻)
            try:
                self.understand_draft(draft_id)
                draft = self.store.get_draft(draft_id)
                raw2 = draft.get("source_raw")
                if isinstance(raw2, str):
                    raw2 = loads_json(raw2, {})
                raw = dict(raw2 or {})
                und_auto = isinstance(raw.get("understanding"), dict) and bool(raw.get("understanding"))
            except Exception:  # noqa: BLE001
                pass
        settings = self.store.get_settings()
        if not str(raw.get("title") or raw.get("imt_name") or "").strip():
            raw["title"] = draft.get("source_title") or draft.get("ozon_title") or ""
        if not raw.get("params"):
            raw["params"] = raw.get("attributes") or (draft.get("attributes") if isinstance(draft.get("attributes"), list) else [])
        if not str(raw.get("description_text") or raw.get("description") or "").strip():
            raw["description_text"] = draft.get("description") or ""
        profile = build_profile(raw or {}, understanding=(raw or {}).get("understanding"))
        roots = self._category_roots_zh(settings)
        nav = navigate_category(roots, self._card_chat(settings, draft), profile)
        if not nav or not nav.get("type_id"):
            return {"ok": False, "matched": False,
                    "note": "AI 没识别出类别，请手动选类目或用「智能草案」"}
        cat = int(nav["description_category_id"])
        typ = int(nav["type_id"])
        path = " / ".join(nav.get("path") or [])
        patch = {"category_id": str(cat), "type_id": str(typ)}
        if path:
            patch["category_path"] = path
        import logging  # noqa: PLC0415
        log = logging.getLogger("ozon.app")
        log.info(f"[recognize_category] draft={draft_id} cat={cat} type={typ} path={path}")
        updated = self.store.update_draft(draft_id, patch)
        # 同组变体合并成一张 Ozon 卡 → 把识别到的类别同步到整组
        synced = self._sync_group_category(updated, cat, typ, path)
        return {"ok": True, "matched": True, "category_id": cat, "type_id": typ,
                "category_path": path, "category_fallback": nav.get("category_fallback"),
                "understood": und_auto, "group_synced": synced, "draft": updated}

    def brand_search(self, cat_id: int, type_id: int, attr_id: int, query: str, language: str = "ZH_HANS") -> dict:
        lang = _attr_language(language)
        # 本地优先：命中即返回；本地没有再调 Ozon 并写回缓存
        local = self.store.find_attribute_values(cat_id, type_id, attr_id, query, lang)
        if local:
            return {"result": local, "source": "local", "count": len(local), "language": lang}
        # Ozon 要求搜索词 ≥2 个字符(runes)，不足就只给本地缓存，不打 API（否则 400）
        if len(query.strip()) < 2:
            return {"result": [], "source": "local", "count": 0,
                    "hint": "输入至少 2 个字符搜索品牌", "language": lang}
        resp = search_attribute_values(self.store.get_settings(), cat_id, type_id, attr_id, query, language=lang)
        values = resp.get("result") or []
        if values:
            self.store.save_attribute_values(cat_id, type_id, attr_id, values, lang)
        return {"result": values, "source": "ozon", "count": len(values), "language": lang}
