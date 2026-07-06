"""AiCardMixin — AI 文案/草案/看图理解/物理量/固定属性/推荐 域方法。

从 app_service.App 整体剪切，方法体一字未改。
跨域 self.xxx() 调用（如 self._category_attrs / self._resolve_values /
self.update_draft / self._resolve_pairs_concurrent / self._ensure_attr_values /
self._settings_for_store）无需 import，同实例上由其他 Mixin 提供。
"""
from __future__ import annotations

import logging

from webui.drafts import (
    BRAND_ATTR_ID,
    NO_BRAND,
    collected_chars,
    match_chars_to_attributes,
    split_collection_value,
    utc_now_iso,
)
from webui.ozon_client_adapter import build_client
from webui.services._helpers import (
    _DIM_KW,
    _VOL_KW,
    _WEIGHT_KW,
    _has_cjk,
    _is_country_attr,
    _parse_dims_mm,
    _parse_volume_ml,
    _parse_weight_g,
    _to_int,
)

log = logging.getLogger("ozon.app")


class AiCardMixin:
    def _physical_facts(self, draft: dict) -> dict:
        """提取确定的物理量(尽量多来源、跨品类)：净重(g)、包装尺寸(mm)、产品尺寸(mm)、容量(ml)。
        包装尺寸/净重优先用草稿结构化字段；其余从 understanding.specs + 1688 原始参数广扫——
        键名各品类不一(容量/净含量/规格/重量/尺寸…)，只在**值带对应单位/LxWxH 格式**时才采纳，
        避免把型号/规格描述里的裸数字误当物理量。"""
        facts: dict = {}
        wg = _to_int(draft.get("weight_g"))
        if wg:
            facts["weight_g"] = wg
        L, W, H = (_to_int(draft.get("length_mm")), _to_int(draft.get("width_mm")),
                   _to_int(draft.get("height_mm")))
        if L and W and H:
            facts["pkg_dims_mm"] = (L, W, H)
        # 候选(键,值)对：理解 specs + 1688 原始属性
        sr = draft.get("source_raw") if isinstance(draft.get("source_raw"), dict) else {}
        und = sr.get("understanding") if isinstance(sr.get("understanding"), dict) else {}
        specs = und.get("specs") if isinstance(und.get("specs"), dict) else {}
        pairs: list = list(specs.items()) if isinstance(specs, dict) else []
        for a in (sr.get("attributes") or []):
            if isinstance(a, dict):
                pairs.append((str(a.get("name") or ""), a.get("value")))

        def _scan(keywords: tuple, parse) -> object:
            for k, v in pairs:
                if any(w in str(k) for w in keywords):
                    out = parse(v)
                    if out:
                        return out
            return None
        if "volume_ml" not in facts:
            ml = _scan(("容量", "体积", "容积", "净含量", "规格", "毫升", "升"), _parse_volume_ml)
            if ml:
                facts["volume_ml"] = ml
        if "weight_g" not in facts:
            g = _scan(("重量", "净重", "毛重", "克重", "净含量", "规格"), _parse_weight_g)
            if g:
                facts["weight_g"] = g
        if "prod_dims_mm" not in facts:
            dm = _scan(("尺寸", "规格", "大小", "长宽高", "外形"), _parse_dims_mm)
            if dm:
                facts["prod_dims_mm"] = dm
        return facts

    @staticmethod
    def _is_physical_attr(attr: dict) -> bool:
        """是否「重量/尺寸/容量」类数字物理属性(代码确定填，不让 AI 猜)。仅限非字典。"""
        if attr.get("dictionary_id"):
            return False
        name = str(attr.get("name") or "").lower()
        return any(k in name for k in (_WEIGHT_KW + _DIM_KW + _VOL_KW))

    def _physical_attr_value(self, attr: dict, facts: dict) -> str | None:
        """按属性名/描述的单位从 facts 算出该填的值；无法判定/无数据→None。单位写在名字或描述里。
        重量→克/千克(按单位)；尺寸→含"包装"用包装尺寸否则产品尺寸,按 mm/cm 输出 LxWxH；容量→毫升/升(按单位)。"""
        import re  # noqa: PLC0415
        name = str(attr.get("name") or "").lower()
        hint = (name + " " + str(attr.get("description") or "")).lower()   # 单位常写在名字「体积，升」或描述里
        if any(k in name for k in _WEIGHT_KW):
            wg = facts.get("weight_g")
            if not wg:
                return None
            # 先判千克(否则"кг"含"г"、"千克"含"克"会被当克)；都没写默认克
            if ("千克" in hint) or ("公斤" in hint) or ("кг" in hint) or re.search(r"(?<![a-zа-яё])kg(?![a-zа-яё])", hint):
                return f"{wg / 1000:g}"   # 单位千克
            return str(int(wg))           # 默认克(克/г/g)
        if any(k in name for k in _DIM_KW):
            # "包装"只在名字里判：描述常含"不带包装"会误判(如 #4382「不带包装的尺寸」是产品尺寸)
            is_pkg = ("包装" in name) or ("упаковк" in name)
            dims = facts.get("pkg_dims_mm") if is_pkg else (facts.get("prod_dims_mm") or facts.get("pkg_dims_mm"))
            if not dims:
                return None
            if ("厘米" in hint) or ("см" in hint) or ("cm" in hint):   # mm→cm
                return "x".join((str(v // 10) if v % 10 == 0 else f"{v / 10:.1f}") for v in dims)
            return "x".join(str(int(v)) for v in dims)
        if any(k in name for k in _VOL_KW):
            ml = facts.get("volume_ml")
            if not ml:
                return None
            # 先判毫升(否则"毫升"含"升"会被当升)；再判升;都没写默认毫升
            if ("毫升" in hint) or ("мл" in hint) or ("ml" in hint):
                return str(int(ml))       # 单位毫升
            if ("升" in hint) or ("литр" in hint) or re.search(r"(?<![а-яё])л(?![а-яё])", hint):
                return f"{ml / 1000:g}"   # 单位升 → ml 换算(如 20000ml→20)
            return str(int(ml))           # 没写单位默认毫升
        return None

    @staticmethod
    def _is_annotation_attr(attr: dict) -> bool:
        """「简介/Аннотация」类长文本营销字段——复用文案步骤的俄语描述，不让属性 AI 逐模型乱翻。"""
        if attr.get("dictionary_id"):
            return False
        name = str(attr.get("name") or "").lower().strip()
        return ("简介" in name) or ("аннотац" in name) or (name == "описание")

    def ai_fill_attributes(self, draft_id: int) -> dict:
        """用 AI 按草稿**当前类目**填属性(不重新导航类目，避免 AI 选错类目)。
        字典(选项)属性：把该属性的**全部合法选项**(id+俄文值)连同「单选/多选+上限」一起发给 AI，
        让它从选项里选、直接返回 dictionary_value_id —— 比旧「AI 自由写俄语词→逐值实时搜」准得多，
        也省掉实时搜。选项超大(oversized 或 >OPTION_CAP)回退「自由写俄语+实时搜」。
        非字典按 type 提示 AI：String→俄语文本 / Boolean→true·false。
        **重量/尺寸/容量等物理数字不让 AI 猜**：从 AI 清单剔除，由 _physical_* 按 Ozon 单位
        (名字/描述里写明 mm/cm/克/ml)从草稿+specs 确定填——单位永不出错、毛重不漏。
        已特殊处理的 9048/23171/85 不动；其余 AI 填的覆盖/补充。"""
        import json as _json  # noqa: PLC0415

        from webui.ai_card import _SYS_ATTRS_PICK, _SYS_TRANSLATE_RU, _extract_json, build_profile  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        cat = int(str(draft.get("category_id") or "0") or 0)
        typ = int(str(draft.get("type_id") or "0") or 0)
        if not cat or not typ:
            return {"error": "请先选好类目（类别识别）再用 AI 填特征"}
        raw = draft.get("source_raw") if isinstance(draft.get("source_raw"), dict) else {}
        settings = self.store.get_settings()
        profile = build_profile(raw or {}, understanding=(raw or {}).get("understanding"))
        # 本变体的区别规格(1688 spec_attrs，如「美式20升」)——喂给 AI 按本变体填区别特征(is_aspect)
        variant_spec = str((raw or {}).get("spec_attrs") or (raw or {}).get("variant_label") or "").strip()
        all_attrs = [a for a in (self._category_attrs(cat, typ) or []) if int(a.get("id") or 0) != 85]
        facts = self._physical_facts(draft)
        # 只把「代码真能填出值」的物理属性排除出 AI 并由代码填；提取不到值的**留给 AI**(避免两头落空)
        phys_fill: dict = {}
        for a in all_attrs:
            if self._is_physical_attr(a):
                v = self._physical_attr_value(a, facts)
                if v:
                    phys_fill[int(a.get("id") or 0)] = (a.get("name"), v)
        required = [a for a in all_attrs if a.get("is_required")]
        ordered = required + [a for a in all_attrs if not a.get("is_required")]
        OPTION_CAP = 150   # 选项数 ≤ 此值才整列发给 AI；超过则回退自由写+实时搜(绝不截断选项)
        brief: list[dict] = []
        opt_index: dict = {}   # aid -> {value_id: 俄文值}；AI 选 id 后据此回填 value(免实时搜)
        for a in ordered[:80]:
            aid = int(a.get("id") or 0)
            if not aid:
                continue
            if aid in phys_fill:
                continue   # 物理量代码已能确定填(下面填)；提取不到的物理属性仍留给 AI
            if self._is_annotation_attr(a):
                continue   # 简介(Аннotация)复用文案描述，不发给 AI
            item = {"id": aid, "name": a.get("name"), "required": bool(a.get("is_required")),
                    "is_aspect": bool(a.get("is_aspect")),   # 变体区别维度(颜色/尺寸/规格)，按本变体 spec 填
                    "hint": str(a.get("description") or "")[:100]}
            t = str(a.get("type") or "").strip().lower()
            if a.get("dictionary_id"):
                values, oversized = self._ensure_attr_values(cat, typ, aid, language="RU")
                if values and not oversized and len(values) <= OPTION_CAP:
                    opt_index[aid] = {int(v["id"]): str(v.get("value") or "")
                                      for v in values if int(v.get("id") or 0)}
                    item["kind"] = "select_many" if a.get("is_collection") else "select_one"
                    if a.get("is_collection") and a.get("max_value_count"):
                        item["max_values"] = int(a["max_value_count"])
                    item["options"] = [{"id": vid, "value": val} for vid, val in opt_index[aid].items()]
                else:
                    item["kind"] = "text_ru"   # 超大字典/选项过多 → 自由写俄语，事后实时搜
            elif t in ("decimal", "integer", "float", "number"):
                item["kind"] = "number"
            elif t == "boolean":
                item["kind"] = "boolean"
            else:
                item["kind"] = "text_ru"
            brief.append(item)
        chat = self._card_chat(settings, draft)
        try:
            user = "Attribute list:\n" + _json.dumps(brief, ensure_ascii=False) + "\n\nProduct:\n" + profile
            # 结构化变体维度(每轴一条)：1688 给 {axis}、Ozon 给 {aspect,aspect_key}、后端推导给 {aspect_key}
            # ——三源都读到轴名喂 AI(来源无关)。
            sel_aspects = (raw or {}).get("selected_aspects")
            axes_txt = ""
            if isinstance(sel_aspects, list) and sel_aspects:
                def _axis_name(a):
                    ax = a.get("axis") or a.get("aspect")
                    if ax:
                        return str(ax)
                    return {"color": "颜色", "size": "尺寸"}.get(str(a.get("aspect_key") or "").lower(), "维度")
                pairs = [f"{_axis_name(a)}={a.get('value')}" for a in sel_aspects
                         if isinstance(a, dict) and a.get("value")]
                axes_txt = "; ".join(pairs)
            if variant_spec or axes_txt:
                user += (f"\n\nThis is ONE VARIANT of the product. "
                         + (f"Its variant dimensions (axis=value, from 1688): {axes_txt}. " if axes_txt else "")
                         + (f"Its distinguishing spec (Chinese):「{variant_spec}」. " if variant_spec else "")
                         + "Fill the attributes marked is_aspect (the variant-distinguishing ones: color/size/volume/"
                         "material/cap/type) to match THIS variant — map each variant dimension to the matching aspect "
                         "attribute and value (e.g. 颜色=哑光白→color; 规格=20升→volume 20 L; 铝盖→cap aluminium). "
                         "Pick from each aspect's options when given; translate values to Russian.")
            card = _extract_json(chat(_SYS_ATTRS_PICK, user))
        except Exception as exc:  # noqa: BLE001
            return {"error": f"AI 属性输出解析失败: {exc}"}
        by_meta = {int(a["id"]): a for a in all_attrs if a.get("id") is not None}
        new_attrs: list[dict] = []
        mapped: list[dict] = []
        unmapped: list[dict] = []
        cjk_pending: list[tuple] = []   # 自由文本里 AI 照抄的中文(aid,name,val)→ 事后批量翻成俄语
        for ca in (card.get("attributes") or []):
            try:
                aid = int(ca.get("id"))
            except (TypeError, ValueError):
                continue
            meta = by_meta.get(aid)
            if not meta:
                continue
            if aid in phys_fill:
                continue   # 该物理量由代码填，忽略 AI 输出(提取不到的物理属性不在此集合,照常收 AI)
            if self._is_annotation_attr(meta):
                continue   # 简介复用文案描述，忽略 AI 输出
            if aid in opt_index:   # 选项属性：AI 返回 value_ids，按 id 直接回填(无需实时搜)
                ids = ca.get("value_ids")
                if not isinstance(ids, list):
                    ids = [ids] if ids not in (None, "") else []
                vals = []
                for i in ids:
                    try:
                        vid = int(i)
                    except (TypeError, ValueError):
                        continue
                    if vid in opt_index[aid]:
                        vals.append({"dictionary_value_id": vid, "value": opt_index[aid][vid]})
                if not meta.get("is_collection"):
                    vals = vals[:1]
                if vals:
                    new_attrs.append({"id": aid, "values": vals})
                    mapped.append({"id": aid, "name": meta.get("name"),
                                   "value": ", ".join(v["value"] for v in vals)})
                else:
                    unmapped.append({"id": aid, "name": meta.get("name"),
                                     "value": str(ca.get("value_ids") or ca.get("value") or "")})
                continue
            val = str(ca.get("value") or ca.get("value_ru") or "").strip()   # 容错:有的模型用 value_ru
            if not val:
                continue
            if meta.get("dictionary_id"):   # 超大字典回退：自由值→实时搜
                texts = [x.strip() for x in val.replace("，", ",").split(",") if x.strip()]
                resolved = self._resolve_values(cat, typ, aid, texts, bool(meta.get("is_collection")))
                if resolved:
                    new_attrs.append({"id": aid, "values": resolved})
                    mapped.append({"id": aid, "name": meta.get("name"), "value": val})
                else:
                    unmapped.append({"id": aid, "name": meta.get("name"), "value": val})
            elif _has_cjk(val):   # AI 没遵守"必须俄语"，自由文本照抄了中文 → 延后批量翻译，绝不直接填中文
                cjk_pending.append((aid, meta.get("name"), val))
            else:   # 自由文本/数字/布尔
                new_attrs.append({"id": aid, "values": [{"value": val}]})
                mapped.append({"id": aid, "name": meta.get("name"), "value": val})
        # 兜底翻译：自由文本里 AI 照抄的中文 → 一次性翻成俄语再填(如"配套/комплектация")；翻译失败的不填中文
        if cjk_pending:
            ru_map: dict = {}
            try:
                items = [{"id": a, "name": nm, "value_zh": v} for a, nm, v in cjk_pending]
                tr = _extract_json(chat(_SYS_TRANSLATE_RU, _json.dumps(items, ensure_ascii=False)))
                for x in (tr.get("items") or []):
                    try:
                        ru_map[int(x.get("id"))] = str(x.get("value_ru") or "").strip()
                    except (TypeError, ValueError):
                        continue
            except Exception:  # noqa: BLE001  翻译失败 → 全部记未映射，不填中文
                ru_map = {}
            for aid, nm, v in cjk_pending:
                ru = ru_map.get(aid, "")
                if ru and not _has_cjk(ru):
                    new_attrs.append({"id": aid, "values": [{"value": ru}]})
                    mapped.append({"id": aid, "name": nm, "value": ru})
                else:
                    unmapped.append({"id": aid, "name": nm, "value": v})
        # 物理量(重量/尺寸/容量)由代码按 Ozon 单位确定填——不经 AI，单位永不出错、毛重不漏
        for aid, (nm, v) in phys_fill.items():
            new_attrs.append({"id": aid, "values": [{"value": v}]})
            mapped.append({"id": aid, "name": nm, "value": v})
        # 简介(Аннотация)复用文案步骤生成的俄语描述，避免属性 AI 逐模型乱翻/重复；文案未跑则留空
        desc = str(draft.get("description") or "").strip()
        if desc:
            for a in all_attrs:
                if self._is_annotation_attr(a):
                    aid = int(a["id"])
                    new_attrs.append({"id": aid, "values": [{"value": desc}]})
                    mapped.append({"id": aid, "name": a.get("name"), "value": desc[:80]})
        keep = {9048, 23171, BRAND_ATTR_ID}  # 型号名/标签/品牌另有处理，AI 不动
        ai_ids = {int(a["id"]) for a in new_attrs if a.get("id") is not None} - keep
        existing = [a for a in (draft.get("attributes") or []) if isinstance(a, dict)]
        merged = [a for a in existing if not (a.get("id") is not None and int(a.get("id")) in ai_ids)]
        merged += [a for a in new_attrs if int(a.get("id")) not in keep]
        # 型号名称(9048,合并为一张卡用)：变体组**强制** = variant_group(整组一致→Ozon 合并)，覆盖任何旧值；
        # 非变体则随机 M-XXXX(每个单品独立卡)、已填则不覆盖。类目无此属性则不塞。
        import uuid  # noqa: PLC0415

        from webui.variant_publish import MODEL_NAME_ATTR_ID  # noqa: PLC0415  # 9048
        cat_has_model = any(_to_int(a.get("id")) == MODEL_NAME_ATTR_ID for a in all_attrs)
        sr = draft.get("source_raw")
        vg = str((sr or {}).get("variant_group") or "").strip() if isinstance(sr, dict) else ""
        extra_patch: dict = {}
        if cat_has_model:
            mv = ""
            if vg:
                mv = vg   # 变体组：强制 = variant_group
            else:
                has_model = any(_to_int(a.get("id")) == MODEL_NAME_ATTR_ID
                                and any(str(v.get("value") or "").strip() for v in (a.get("values") or []))
                                for a in merged)
                if not has_model:
                    mv = "M-" + uuid.uuid4().hex[:8].upper()
            if mv:
                merged = [a for a in merged if _to_int(a.get("id")) != MODEL_NAME_ATTR_ID]  # 去重旧 9048
                merged.append({"id": MODEL_NAME_ATTR_ID, "values": [{"value": mv}]})
                mapped.append({"id": MODEL_NAME_ATTR_ID, "name": "型号名称", "value": mv})
        # 货号：变体组里若该变体货号为空 → 随机 SP-，保证每个变体唯一货号(Ozon SKU 需唯一)
        if vg and not str(draft.get("offer_id") or "").strip():
            extra_patch["offer_id"] = "SP-" + uuid.uuid4().hex[:8].upper()
        updated = self.store.update_draft(draft_id, {"attributes": merged, **extra_patch})
        return {"ok": True, "draft": updated, "mapped_count": len(mapped),
                "mapped": mapped, "unmapped": unmapped}

    def auto_map_attributes(self, draft_id: int) -> dict:
        """采集特征(俄文) → 按俄文名对到类目属性(也取俄文) → 解析字典值，自动填进上架属性。
        属性 ID 与语言无关，填进去后中文界面的必填校验照样会减少。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        cat = str(draft.get("category_id") or "").strip()
        typ = str(draft.get("type_id") or "").strip()
        if not cat or not typ:
            return {"error": "请先选好类目再自动填充"}
        cat_i, typ_i = int(cat), int(typ)
        # 采集数据是俄文，属性表也取俄文才能按名对上；走 RU 维度缓存（_category_attrs 已带
        # 缓存+写回），避免每次采集都跨境拉一遍俄文属性表（实测每次省 ~5s）。不污染界面 ZH 缓存。
        meta = self._category_attrs(cat_i, typ_i, language="RU")
        pairs = match_chars_to_attributes(collected_chars(draft), meta)

        # 现有上架格式条目（{id, values}），按 id 索引，便于覆盖/合并
        raw = draft.get("attributes") if isinstance(draft.get("attributes"), list) else []
        publish_by_id: dict[int, dict] = {}
        passthrough: list[dict] = []
        for a in raw:
            if isinstance(a, dict) and "id" in a and "values" in a:
                publish_by_id[_to_int(a.get("id"))] = a
            elif isinstance(a, dict):
                passthrough.append(a)  # 采集来的 {name,value} 参考，原样保留

        mapped: list[dict] = []
        unmapped: list[dict] = []
        dict_tasks: list[tuple[int, list[str], bool]] = []     # (aid, texts, is_collection)
        dict_meta: dict[int, dict] = {}                        # aid -> {name, text}
        free_text: list[tuple[int, str, str]] = []             # (aid, text, name)
        for p in pairs:
            attr, ch = p["attr"], p["char"]
            aid = _to_int(attr.get("id"))
            if aid == BRAND_ATTR_ID:
                continue
            text = str(ch.get("value") or "")
            if attr.get("dictionary_id"):
                dict_tasks.append((aid, split_collection_value(text), bool(attr.get("is_collection"))))
                dict_meta[aid] = {"name": attr.get("name"), "text": text}
            else:  # 自由文本属性
                free_text.append((aid, text, str(attr.get("name") or "")))

        resolved = self._resolve_pairs_concurrent(cat_i, typ_i, dict_tasks)
        for aid, m in dict_meta.items():
            values = resolved.get(aid) or []
            if not values:
                unmapped.append({"id": aid, "name": m["name"], "value": m["text"]})
                continue
            publish_by_id[aid] = {"id": aid, "values": values}
            mapped.append({"id": aid, "name": m["name"],
                           "value": " , ".join(v["value"] for v in values)})
        for aid, text, name in free_text:
            publish_by_id[aid] = {"id": aid, "values": [{"value": text}]}
            mapped.append({"id": aid, "name": name, "value": text})

        self._force_country_to_china(cat_i, typ_i, meta, publish_by_id, mapped)  # 原产国一律中国
        self._fill_model_name(meta, draft, publish_by_id, mapped)  # 型号名称：单品自动填唯一随机值
        new_attributes = passthrough + list(publish_by_id.values())
        brand_id = draft.get("brand_id") if str(draft.get("brand_name") or "").strip() == NO_BRAND else None
        patch: dict = {
            "attributes": new_attributes,
            "brand_id": brand_id if _to_int(brand_id) > 0 else None,
            "brand_name": NO_BRAND,
        }
        updated = self.store.update_draft(draft_id, patch)
        return {"draft": updated, "mapped": mapped, "unmapped": unmapped,
                "mapped_count": len(mapped)}

    def _force_country_to_china(self, cat: int, typ: int, meta: list[dict],
                                publish_by_id: dict, mapped: list[dict]) -> None:
        """原产国一律「中国」：类目里只要有原产国属性(俄文名含 Страна)，就把它的值强制
        设成 Китай(中国)、覆盖竞品采到的任何值；竞品没采到也主动填。与采集内容无关。"""
        for attr in meta:
            if "страна" not in str(attr.get("name") or "").lower():
                continue
            caid = _to_int(attr.get("id"))
            if not caid or caid == BRAND_ATTR_ID:
                continue
            cvals = self._resolve_values(cat, typ, caid, ["Китай"], False)
            if cvals:
                publish_by_id[caid] = {"id": caid, "values": cvals}
                mapped.append({"id": caid, "name": attr.get("name"), "value": "Китай"})

    def _ensure_fixed_attrs(self, draft: dict) -> dict:
        """发布前**写死**：品牌=无品牌、原产国/制造国=中国(Китай)，覆盖采集/AI 的任何值。
        不在「特征」让用户填，要改去 Ozon 后台改。即使没跑过自动填充也保证这几项就位。"""
        cat = int(str(draft.get("category_id") or "0") or 0)
        typ = int(str(draft.get("type_id") or "0") or 0)
        if not cat or not typ:
            return draft
        try:
            meta = self._category_attrs(cat, typ, language="RU")
        except Exception:  # noqa: BLE001  拉不到属性表就不强填(不阻断发布)
            return draft
        attrs = [a for a in (draft.get("attributes") or []) if isinstance(a, dict)]
        patch: dict = {}
        # 原产国 / 制造国 等所有「国家」属性 → Китай(全部覆盖，不只第一个；非国家字典里"Китай"解析不到则跳过)
        country_ids = [_to_int(a.get("id")) for a in meta
                       if _is_country_attr(a) and _to_int(a.get("id")) not in (0, BRAND_ATTR_ID)]
        country_changed = False
        for cid in dict.fromkeys(country_ids):   # 去重保序
            cvals = self._resolve_values(cat, typ, cid, ["Китай"], False)
            if cvals:
                attrs = [a for a in attrs if _to_int(a.get("id")) != cid]
                attrs.append({"id": cid, "values": cvals})
                country_changed = True
        if country_changed:
            patch["attributes"] = attrs
        # 品牌 → 无品牌(brand_id 没解析过才解析一次)
        if not (_to_int(draft.get("brand_id")) > 0
                and str(draft.get("brand_name") or "").strip() == NO_BRAND):
            bvals = self._resolve_values(cat, typ, BRAND_ATTR_ID, [NO_BRAND], False)
            if bvals:
                patch["brand_id"] = bvals[0]["dictionary_value_id"]
                patch["brand_name"] = NO_BRAND
        if patch:
            return self.store.update_draft(int(draft["id"]), patch)
        return draft

    def map_attributes(self, draft_id: int) -> dict:
        """Map collected attributes into Ozon attributes.

        1688 should first build a visual/text understanding, then use AI to fill
        attributes for the recognized Ozon category. WB already has structured
        Russian drawer features, so it goes straight to AI attribute filling.
        Other platforms keep the fast name-based mapper.
        """
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw") if isinstance(draft.get("source_raw"), dict) else {}
        platform = str(draft.get("source_platform") or sr.get("source_platform") or "").strip().lower()
        if platform == "1688":
            if not (isinstance(sr.get("understanding"), dict) and sr.get("understanding")):
                self.understand_draft(draft_id)
            result = self.ai_fill_attributes(draft_id)
            if isinstance(result, dict):
                result.setdefault("mapped_by", "ai")
            return result
        if platform == "wb":
            result = self.ai_fill_attributes(draft_id)
            if isinstance(result, dict):
                result.setdefault("mapped_by", "ai")
            return result
        result = self.auto_map_attributes(draft_id)
        if isinstance(result, dict):
            result.setdefault("mapped_by", "rules")
        return result

    def _fill_model_name(self, meta: list[dict], draft: dict,
                         publish_by_id: dict, mapped: list[dict]) -> None:
        """型号名称(9048)：单品自动填一个唯一随机值，让每个单品成独立卡片、并满足必填。
        - 已有 9048（用户填过/竞品采到）不动；
        - 类目没有 9048 这个属性则不填（不塞无效属性）；
        - 变体组草稿跳过：其 9048 在合并发布时由 variant_group 统一填（保证组内合并为一张卡）。"""
        from webui.variant_publish import MODEL_NAME_ATTR_ID  # noqa: PLC0415  # 9048
        if MODEL_NAME_ATTR_ID in publish_by_id:
            return
        if not any(_to_int(a.get("id")) == MODEL_NAME_ATTR_ID for a in (meta or [])):
            return
        sr = draft.get("source_raw")
        vg = str((sr or {}).get("variant_group") or "").strip() if isinstance(sr, dict) else ""
        if vg:
            # 变体组草稿：型号名(9048)= variant_group，组内一致 → Ozon 合并为一张卡。
            # 单条发布也填(原来 return 跳过 → 单发变体时 9048 空缺、型号名发不上去)。
            publish_by_id[MODEL_NAME_ATTR_ID] = {"id": MODEL_NAME_ATTR_ID, "values": [{"value": vg}]}
            mapped.append({"id": MODEL_NAME_ATTR_ID, "name": "型号名称", "value": vg})
            return
        import uuid  # noqa: PLC0415
        token = "M-" + uuid.uuid4().hex[:8].upper()
        publish_by_id[MODEL_NAME_ATTR_ID] = {"id": MODEL_NAME_ATTR_ID, "values": [{"value": token}]}
        mapped.append({"id": MODEL_NAME_ATTR_ID, "name": "型号名称", "value": token})

    def _no_brand_value(self, cat: int, typ: int) -> dict | None:
        """解析"无品牌"(Нет бренда)的字典值，attr 85。找不到返回 None。"""
        vals = self._resolve_values(cat, typ, 85, [NO_BRAND], False)
        return vals[0] if vals else None

    def _category_roots_ru(self, settings: dict) -> list:
        client = None if self.catalog_ru.has_tree_cache() else build_client(settings)
        return self.catalog_ru.raw_tree(client)

    def _category_roots_zh(self, settings: dict) -> list:
        """中文(ZH_HANS)类目树根，喂给 AI 做类目下钻。产品 profile 是中文，
        中文↔中文匹配远比中文↔俄语可靠：「智能喂食器」直接对上「宠物餐具→宠物自动喂食器」，
        不会被摄像头/远程等电子卖点带去「宠物小工具→驱虫器」。返回的 cat/type_id 与语言无关。"""
        client = None if self.catalog.has_tree_cache() else build_client(settings)
        return self.catalog.raw_tree(client)

    def _card_chat(self, settings: dict, draft: dict):
        """卡片/类目下钻/提示词生成用的 chat 函数。
        - engine=agnes：agnes_chat；多模态时附公网主图
        - engine=openai：deepseek_chat；多模态时附公网主图(OpenAI vision)
        多模态由 ai_text.multimodal 决定（取代旧 ai_card_vision）。"""
        from webui.settings_migrate import ai_config, migrate_ai  # noqa: PLC0415
        engine = ai_config(settings, "text")["engine"]
        multimodal = bool(migrate_ai(settings)["ai_text"].get("multimodal"))
        images = None
        if multimodal:
            from webui import agnes  # noqa: PLC0415
            sr = (draft or {}).get("source_raw") or {}
            pics = agnes.pick_public_images((draft or {}).get("images"), sr.get("detail_images"), cap=4) or []
            images = pics[:4] or None      # 多模态最多看 4 张图，覆盖卖点/参数图
        if engine == "agnes":
            from webui import agnes  # noqa: PLC0415
            return lambda s, u: agnes.agnes_chat(settings, s, u, images=images)
        from webui.ai_card import deepseek_chat  # noqa: PLC0415  单测会 monkeypatch 该属性
        return lambda s, u: deepseek_chat(settings, s, u, images=images)

    def ai_generate(self, draft_id: int) -> dict:
        """生成 AI 卡片提案，但 **不写入草稿**。

        返回:
          {"ok": True,
           "proposal": { ...所有将被应用的字段... },
           "report": {"category_fallback":..., "brand_warning":...,
                      "unmapped":..., "mapped":..., "keywords":...,
                      "category_path":...}}

        调用方（前端）应向用户展示预览；用户点「应用」后把 proposal 字段发往
        PATCH /api/drafts/{id}（update_draft），点「放弃」则丢弃。
        """
        from webui.ai_card import generate_card  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        raw_sr = draft.get("source_raw") or {}
        if isinstance(raw_sr, str):
            from webui.drafts import loads_json  # noqa: PLC0415
            raw_sr = loads_json(raw_sr, {})
        raw = dict(raw_sr or {})
        if not str(raw.get("title", "")).strip():
            raw["title"] = draft.get("source_title") or draft.get("ozon_title") or ""
        # 1688 采集 source_raw.attributes = [{name,value}] → params；缺则用草稿 Ozon 格式兜底
        if not raw.get("params"):
            raw["params"] = raw.get("attributes") or (draft.get("attributes") if isinstance(draft.get("attributes"), list) else [])
        if not str(raw.get("description_text", "")).strip():
            raw["description_text"] = draft.get("description") or ""
        settings = self.store.get_settings()
        r = generate_card(
            raw,
            chat=self._card_chat(settings, draft),
            # AI 从根类目逐层下钻到末级类型（取代旧的"关键词→搜索候选→选一个"两步）。
            # 喂中文树：中文↔中文匹配，避免被电子卖点带偏类目（喂食器≠驱虫器）。
            category_roots=self._category_roots_zh(settings),
            fetch_required_attrs=self._category_attrs,
            resolve_values=self._resolve_values,
            # 理解层事实(若已生成)并入 profile：让文案基于图上卖点写，简介更厚
            understanding=(raw.get("understanding") if isinstance(raw, dict) else None),
        )
        if not r.get("ok"):
            return r
        cat, typ = int(r["category_id"]), int(r["type_id"])
        # 构造 proposal（仅包含将要被应用的字段，不写 DB）
        proposal: dict = {
            "category_id": r["category_id"],
            "type_id": r["type_id"],
            "ozon_title": r["ozon_title"],
            "description": r["description"],
            "attributes": r["attributes"],
        }
        # AI 从参数表解析到的毛重/尺寸：仅在 >0 时纳入 proposal
        for k in ("weight_g", "length_mm", "width_mm", "height_mm"):
            if _to_int(r.get(k)) > 0:
                proposal[k] = _to_int(r.get(k))
        nb = self._no_brand_value(cat, typ)
        brand_warning: str | None = None
        if nb:
            proposal["brand_id"] = nb["dictionary_value_id"]
            proposal["brand_name"] = nb["value"]
        else:
            proposal["brand_name"] = NO_BRAND
            brand_warning = "无品牌(Нет бренда)未能解析为字典值，发布前请手动确认品牌属性"
        unmapped = list(r["unmapped"])
        if brand_warning:
            unmapped = [{"id": 85, "name": "Бренд", "value": brand_warning}] + unmapped
        report = {
            "category_path": r.get("category_path"),
            "category_fallback": r.get("category_fallback", False),
            "brand_warning": brand_warning,
            "unmapped": unmapped,
            "mapped": r["mapped"],
            "keywords": [],   # 已改树形下钻，不再有关键词步骤（保留键以兼容下游）
        }
        # 组装待确认草案（含缺失必填/可选属性）
        from webui.ai_card import build_proposal_draft  # noqa: PLC0415
        try:
            attrs = self._category_attrs(cat, typ)
            required = [a for a in attrs if a.get("is_required")]
            optional = [a for a in attrs if not a.get("is_required")]
        except Exception:  # noqa: BLE001
            required, optional = [], []
        draft_json = build_proposal_draft(proposal, report, required, optional, ts=utc_now_iso())
        is_auto = bool(settings.get("ai_auto_apply"))
        self.store.set_ai_proposal(draft_id, draft_json)
        if is_auto:
            applied = self.apply_ai_proposal(draft_id)
            return {"ok": True, "mode": "applied", "draft": applied["draft"],
                    "unmapped": applied["unmapped"], "report": report}
        return {"ok": True, "mode": "draft", "proposal": draft_json, "report": report}

    def ai_copy(self, draft_id: int) -> dict:
        """只生成文案(标题/简介/标签)——**1 次 LLM 调用**，不下钻类目、不映射属性，比 ai_generate 快得多。
        结果写 ai_proposal(预览)，用户确认后应用。类目/属性走自动匹配或 Ozon 复制，单独处理。"""
        from webui.ai_card import (  # noqa: PLC0415
            _SYS_TITLE,
            NO_BRAND,
            _extract_json,
            build_profile,
            build_proposal_draft,
            clean_hashtags,
        )
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        raw_sr = draft.get("source_raw") or {}
        if isinstance(raw_sr, str):
            from webui.drafts import loads_json  # noqa: PLC0415
            raw_sr = loads_json(raw_sr, {})
        raw = dict(raw_sr or {})
        if not str(raw.get("title", "")).strip():
            raw["title"] = draft.get("source_title") or draft.get("ozon_title") or ""
        # 1688 采集 source_raw.attributes = [{name,value}] → params；缺则用草稿 Ozon 格式兜底
        if not raw.get("params"):
            raw["params"] = raw.get("attributes") or (draft.get("attributes") if isinstance(draft.get("attributes"), list) else [])
        if not str(raw.get("description_text", "")).strip():
            raw["description_text"] = draft.get("description") or ""
        understanding = raw.get("understanding") if isinstance(raw, dict) else None
        profile = build_profile(raw, understanding=understanding)
        chat = self._card_chat(self.store.get_settings(), draft)
        raw = ""
        try:
            log.info(f"[ai_copy] draft={draft_id} requesting, profile={(profile[:500])}")
            raw = chat(_SYS_TITLE, "Product:\n" + profile)
            log.info(f"[ai_copy] draft={draft_id} response, raw={(str(raw)[:500])}")
            if not str(raw).strip():
                log.error(f"[ai_copy] draft={draft_id} LLM returned empty")
                return {"ok": False, "error": "AI 文案输出为空（模型/网关异常）"}
            body = _extract_json(raw)
            log.info(f"[ai_copy] draft={draft_id} OK title={len(str(body.get('ozon_title','')))} desc={len(str(body.get('description','')))}")
        except Exception as exc:  # noqa: BLE001
            log.exception(f"[ai_copy] draft={draft_id} LLM error, raw={str(raw)[:1000]}")
            return {"ok": False, "error": f"AI 文案输出解析失败: {exc}"}
        proposal: dict = {"ozon_title": str(body.get("ozon_title") or ""),
                          "description": str(body.get("description") or ""),
                          "attributes": []}   # 文案只出 标题/简介/标签，不提取品牌/类型
        tags_value = clean_hashtags(body.get("hashtags"))
        mapped: list = []
        if tags_value:
            proposal["attributes"].append({"id": 23171, "values": [{"value": tags_value}]})
            mapped.append({"id": 23171, "name": "#Хештеги", "value": tags_value})
        report = {"category_path": "", "category_fallback": False, "brand_warning": None,
                  "unmapped": [], "mapped": mapped, "keywords": []}
        draft_json = build_proposal_draft(proposal, report, [], [], ts=utc_now_iso())
        for k in ("category_id", "type_id", "category_path", "brand_name", "brand_id"):
            (draft_json.get("fields") or {}).pop(k, None)
        # 自动应用模式：直接写入草稿，跳过人工确认
        if bool(self.store.get_settings().get("ai_auto_apply")):
            updated = self.apply_ai_proposal(draft_id)
            return {"ok": True, "mode": "applied", "draft": updated}
        self.store.set_ai_proposal(draft_id, draft_json)
        return {"ok": True, "mode": "draft", "proposal": draft_json, "report": report}

    def _multimodal_chat(self, settings: dict):
        """理解层多模态 chat。优先用单独配的「多模态 AI」槽;**没配则自动复用「文本 AI」**
        ——Agnes 本就多模态,翻译那套配置直接拿来看图理解,用户无需再配一个模型。
        返回 chat(system, user, image_urls) -> str。"""
        from webui.settings_migrate import ai_config  # noqa: PLC0415
        kind = "multimodal" if ai_config(settings, "multimodal").get("key") else "text"
        engine = ai_config(settings, kind)["engine"]
        if engine == "agnes":
            from webui import agnes  # noqa: PLC0415
            return lambda s, u, images: agnes.agnes_chat(settings, s, u, images=images, kind=kind)
        from webui.ai_card import deepseek_chat  # noqa: PLC0415
        return lambda s, u, images: deepseek_chat(settings, s, u, images=images, kind=kind)

    def understand_draft(self, draft_id: int, *, force: bool = False) -> dict:
        """理解层:多模态"看图理解"→ understanding,缓存 source_raw.understanding。
        force=True 重抽;已有缓存且非 force → 直接返回(cached=True)。图先经 _resolve_image_input
        转成模型可取链接(http 直用 / /media/ 转 data URI)。"""
        from webui.drafts import loads_json  # noqa: PLC0415
        from ozon_common.text_pipeline.understand import understand  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = dict(sr or {})
        cached = isinstance(sr.get("understanding"), dict) and bool(sr["understanding"])
        if force or not cached:
            chat_fn = self._multimodal_chat(self.store.get_settings())
            u = understand(draft, chat_fn, resolve_image=self._resolve_image_input)
            sr["understanding"] = u
        else:
            u = sr["understanding"]
        # 把理解到的尺寸/克重 + 默认定价写进结构化草稿字段（即使缓存命中也回填，便于补旧草稿）
        patch = self._autofill_from_understanding(draft, u)
        patch["source_raw"] = sr
        updated = self.store.update_draft(draft_id, patch)
        autofill = {k: v for k, v in patch.items() if k != "source_raw"}
        return {"ok": True, "understanding": u, "cached": cached and not force,
                "draft": updated, "autofill": autofill}

    def _cost_basis_cny(self, draft: dict) -> float | None:
        """进价(CNY)：cost_cny>0 优先；否则取 1688 采集的 price_display 区间最低价。"""
        try:
            c = float(draft.get("cost_cny") or 0)
            if c > 0:
                return c
        except (TypeError, ValueError):
            pass
        import re  # noqa: PLC0415

        from webui.drafts import loads_json  # noqa: PLC0415
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = sr if isinstance(sr, dict) else {}
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(sr.get("price_display") or ""))]
        return min(nums) if nums else None

    def _autofill_from_understanding(self, draft: dict, understanding: dict) -> dict:
        """理解 → 结构化字段补丁：尺寸/克重以**采集的包装件重尺为准**，理解(看图)的值仅在草稿没有时兜底
        (看图读到的多是产品尺寸而非物流箱尺寸，Ozon 要的是包装尺寸)；默认定价仅当售价为空时填。"""
        from webui.listing_build import default_pricing, parse_dims_mm, parse_weight_g  # noqa: PLC0415
        specs = (understanding or {}).get("specs") or {}
        patch: dict = {}

        def _empty(v):
            return v in (None, 0, "", "0")
        dims = parse_dims_mm(specs.get("尺寸") or specs.get("size") or "")
        if dims and all(_empty(draft.get(k)) for k in ("length_mm", "width_mm", "height_mm")):
            patch["length_mm"], patch["width_mm"], patch["height_mm"] = dims
        w = parse_weight_g(specs.get("重量") or specs.get("weight") or "")
        if w and _empty(draft.get("weight_g")):
            patch["weight_g"] = w
        if not str(draft.get("price") or "").strip():   # 不覆盖用户已填的售价
            cost = self._cost_basis_cny(draft)
            pr = default_pricing(cost) if cost else None
            if pr:
                patch["price"], patch["old_price"] = str(pr[0]), str(pr[1])
                try:
                    has_cost = float(draft.get("cost_cny") or 0) > 0
                except (TypeError, ValueError):
                    has_cost = False
                if not has_cost:
                    patch["cost_cny"] = cost   # 进价回填，便于用户看到/二次定价稳定
        return patch

    def recommend(self, draft_id: int) -> dict:
        """智能推荐(纯逻辑,不调 AI):据来源 + 缓存的 understanding → 推荐路径(复制/俄化/重做)
        + 逐图默认处理。understanding 未生成时 per_image 为空、仅按来源给路径默认。"""
        from webui.drafts import loads_json  # noqa: PLC0415
        from webui.recommend import recommend_path  # noqa: PLC0415
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        sr = draft.get("source_raw")
        if isinstance(sr, str):
            sr = loads_json(sr, {})
        sr = sr if isinstance(sr, dict) else {}
        understanding = sr.get("understanding") if isinstance(sr.get("understanding"), dict) else None
        source = draft.get("source") or draft.get("source_platform") or ""
        rec = recommend_path(source=source, understanding=understanding, copyable=None)
        return {"ok": True, "recommendation": rec, "has_understanding": understanding is not None}

    def apply_ai_proposal(self, draft_id: int) -> dict:
        """把草稿的 AI 待确认草案合并进正式字段，清空草案。
        - fields 里存在的 key 才覆盖（删除的 key 保留正式原值）
        - attributes 有 value 的项解析成上架格式并按 id 合并；空 value 跳过
        返回 {ok, draft, unmapped}。无草案 → ValueError。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        proposal = draft.get("ai_proposal")
        if not proposal:
            raise ValueError("没有待确认的 AI 草案")
        fields = dict(proposal.get("fields") or {})
        patch: dict = {}
        for k in ("ozon_title", "description", "category_id", "type_id",
                  "weight_g", "length_mm", "width_mm", "height_mm"):
            if k in fields:
                patch[k] = fields[k]
        brand_id = fields.get("brand_id", draft.get("brand_id"))
        brand_name = str(fields.get("brand_name") or draft.get("brand_name") or "").strip()
        patch["brand_id"] = brand_id if brand_name == NO_BRAND and _to_int(brand_id) > 0 else None
        patch["brand_name"] = NO_BRAND
        cat = int(str(patch.get("category_id") or draft.get("category_id") or 0) or 0)
        typ = int(str(patch.get("type_id") or draft.get("type_id") or 0) or 0)
        new_attrs: list[dict] = []
        unmapped: list[dict] = []
        for a in (proposal.get("attributes") or []):
            val = str(a.get("value") or "").strip()
            if not val:
                continue
            aid = _to_int(a.get("id"))
            if aid <= 0:
                continue
            if aid == BRAND_ATTR_ID:
                continue
            if aid == 23171:   # #Хештеги 是自由文本，整串直存，不走字典解析(否则有类目时会被解析丢弃)
                new_attrs.append({"id": 23171, "values": [{"value": val}]})
                continue
            texts = [t.strip() for t in val.replace("，", ",").split(",") if t.strip()]
            vals = self._resolve_values(cat, typ, aid, texts, False) if cat and typ else [{"value": val}]
            if vals:
                new_attrs.append({"id": aid, "values": vals})
            else:
                unmapped.append({"id": aid, "name": a.get("name"), "value": val})
        attr_list = draft.get("attributes") if isinstance(draft.get("attributes"), list) else []
        passthrough = [a for a in attr_list if isinstance(a, dict) and not ("id" in a and "values" in a)]
        existing_pub = [a for a in attr_list if isinstance(a, dict) and "id" in a and "values" in a]
        merged = {_to_int(a["id"]): a for a in existing_pub if _to_int(a.get("id")) > 0}
        for a in new_attrs:
            merged[_to_int(a["id"])] = a
        patch["attributes"] = passthrough + list(merged.values())
        self.store.update_draft(draft_id, patch)
        self.store.set_ai_proposal(draft_id, None)
        updated = self.store.get_draft(draft_id)
        return {"ok": True, "draft": updated, "unmapped": unmapped}

    def patch_ai_proposal(self, draft_id: int, patch: dict) -> dict:
        """编辑/删除草案某项，或 discard 清空整份草案，写回 ai_proposal_json。
        op: edit_field{key,value} / delete_field{key} / edit_attr{id,value} /
            delete_attr{id} / discard。无草案 → ValueError；未知 op → ValueError。"""
        draft = self.store.get_draft(draft_id)
        if draft is None:
            raise KeyError(f"draft {draft_id} not found")
        proposal = draft.get("ai_proposal")
        if not proposal:
            raise ValueError("没有待确认的 AI 草案")
        op = str((patch or {}).get("op") or "")
        if op == "discard":
            self.store.set_ai_proposal(draft_id, None)
            return {"ok": True, "proposal": None}
        fields = dict(proposal.get("fields") or {})
        attrs = list(proposal.get("attributes") or [])
        if op == "edit_field":
            fields[str(patch["key"])] = patch.get("value")
        elif op == "delete_field":
            fields.pop(str(patch.get("key")), None)
        elif op == "edit_attr":
            aid = _to_int(patch.get("id")); val = str(patch.get("value") or "")
            for a in attrs:
                if _to_int(a.get("id")) == aid:
                    a["value"] = val
                    break
        elif op == "delete_attr":
            aid = _to_int(patch.get("id"))
            attrs = [a for a in attrs if _to_int(a.get("id")) != aid]
        else:
            raise ValueError(f"未知操作: {op}")
        proposal["fields"] = fields
        proposal["attributes"] = attrs
        self.store.set_ai_proposal(draft_id, proposal)
        return {"ok": True, "proposal": proposal}
