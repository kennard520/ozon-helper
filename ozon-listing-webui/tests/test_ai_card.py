from __future__ import annotations
import json
import unittest
from backend.ai_card import build_profile, generate_card


class AiCardPureTest(unittest.TestCase):
    def test_build_profile_truncates(self):
        raw = {"title": "车载支架", "params": [{"k": "材质", "v": "铝"}],
               "description_text": "x" * 10000}
        p = build_profile(raw, budget=200)
        self.assertIn("车载支架", p)
        self.assertIn("材质", p)
        self.assertLessEqual(len(p), 200)


class CategoryFallbackTest(unittest.TestCase):
    """generate_card 走树形下钻：AI 选不出有效 index 时退到 index 0，category_fallback=True。"""

    ROOTS = [{"description_category_id": 17028922, "category_name": "Авто", "children": [
        {"type_id": 94307, "type_name": "Держатель", "description_category_id": 17028922}]}]

    def _make_chat(self, *nav_responses):
        calls = {"i": 0}
        navs = list(nav_responses)
        def chat(system, user):
            i = calls["i"]; calls["i"] += 1
            if i < len(navs):
                return navs[i]
            return json.dumps({"ozon_title": "T", "description": "D", "attributes": []})
        return chat

    def test_no_fallback_when_navigation_picks_valid_index(self):
        """每层都返回有效 index → category_fallback 为 False。"""
        chat = self._make_chat('{"index":0}', '{"index":0}')
        r = generate_card(
            {"title": "T", "params": [], "description_text": "D"},
            chat=chat,
            category_roots=self.ROOTS,
            fetch_required_attrs=lambda c, t: [],
            resolve_values=lambda c, t, aid, texts, coll: [],
        )
        self.assertTrue(r.get("ok"))
        self.assertFalse(r["category_fallback"],
                         "下钻命中有效 index 时 category_fallback 应为 False")
        self.assertEqual(r["category_id"], "17028922")
        self.assertEqual(r["type_id"], "94307")

    def test_fallback_true_when_navigation_index_unparseable(self):
        """某层 AI 返回无法解析的 index（重试后仍坏）→ 退到 index 0，category_fallback 为 True。"""
        # 第一层返回坏 JSON（navigate 会重试一次，仍坏 → idx=0,fallback=True），第二层正常
        chat = self._make_chat('not-json', 'not-json', '{"index":0}')
        r = generate_card(
            {"title": "T", "params": [], "description_text": "D"},
            chat=chat,
            category_roots=self.ROOTS,
            fetch_required_attrs=lambda c, t: [],
            resolve_values=lambda c, t, aid, texts, coll: [],
        )
        self.assertTrue(r.get("ok"))
        self.assertTrue(r["category_fallback"],
                        "下钻退到 index 0 时 category_fallback 应为 True")
        # 仍下钻到唯一末级类型
        self.assertEqual(r["category_id"], "17028922")
        self.assertEqual(r["type_id"], "94307")


class GenerateCardTest(unittest.TestCase):
    def test_full_flow_injected(self):
        calls = []
        def chat(system, user):
            calls.append(user)
            if len(calls) == 1:
                return '{"index":0}'                     # 第一层(根)下钻
            if len(calls) == 2:
                return '{"index":0}'                      # 第二层(末级类型)下钻
            if len(calls) == 3:
                return json.dumps({"ozon_title": "Автодержатель", "description": "Описание",
                                   "hashtags": []})       # 文案
            return json.dumps({"attributes": [{"id": 4180, "value": "металл"}],
                               "weight_g": 600, "length_cm": 20, "width_cm": 15, "height_cm": 10})  # 属性
        roots = [{"description_category_id": 17028922, "category_name": "Авто", "children": [
            {"type_id": 94307, "type_name": "Держатель", "description_category_id": 17028922}]}]
        attrs = lambda c, t: [{"id": 4180, "name": "Материал", "is_required": True,
                               "dictionary_id": 100, "is_collection": False}]
        resolve = lambda c, t, aid, texts, coll: [{"dictionary_value_id": 555, "value": "металл"}]
        r = generate_card({"title": "车载支架", "params": [], "description_text": "铝"},
                          chat=chat, category_roots=roots,
                          fetch_required_attrs=attrs, resolve_values=resolve)
        self.assertEqual(r["category_id"], "17028922")
        self.assertEqual(r["type_id"], "94307")
        self.assertEqual(r["ozon_title"], "Автодержатель")
        self.assertEqual(r["brand_name"], "Нет бренда")
        # 字典属性解析成上架格式
        a4180 = next(a for a in r["attributes"] if a["id"] == 4180)
        self.assertEqual(a4180["values"][0]["dictionary_value_id"], 555)
        # AI 从参数解析的毛重(g)/尺寸(cm) → ×10 存毫米 length_mm
        self.assertEqual(r["weight_g"], 600)
        self.assertEqual(r["length_mm"], 200)
        self.assertEqual(r["width_mm"], 150)
        self.assertEqual(r["height_mm"], 100)
        self.assertEqual(len(calls), 4)  # 2 类目下钻 + 文案 + 属性
        # Fix 2: AI 类目在候选中时 category_fallback 为 False
        self.assertFalse(r["category_fallback"])


class AiGenerateEndpointTest(unittest.TestCase):
    def test_ai_generate_endpoint(self):
        """ai_generate 应返回 mode/proposal（含 fields.category_id/ozon_title/brand_name），且不持久化主字段。"""
        import importlib, tempfile, json as J
        from pathlib import Path
        from fastapi.testclient import TestClient
        import backend.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.DEFAULT_DB = Path(tmp) / "ai.db"
            import backend.app_service as svc; importlib.reload(svc)
            import backend.main as main_mod; importlib.reload(main_mod)
            app = main_mod.APP
            from backend.drafts import create_draft_from_url
            d = app.store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/123456789012.html"))
            app.store.update_draft(d["id"], {"source_raw": {"title": "车载支架", "params": [], "description_text": "铝"}})
            # 记录调用前草稿的类目（应为空）
            draft_before = app.store.get_draft(d["id"])
            self.assertEqual(str(draft_before.get("category_id") or "").strip(), "",
                             "前置条件：草稿 category_id 应为空")
            # 打桩：AI 三次、catalog、属性、resolve
            import backend.ai_card as aic
            seq = ['{"index":0}', '{"index":0}',
                   J.dumps({"ozon_title": "Держатель", "description": "Опис", "hashtags": []}),
                   J.dumps({"attributes": [{"id": 4180, "value": "металл"}]})]
            calls = {"i": 0}
            def fake_chat(settings, s, u, images=None):
                v = seq[calls["i"]]; calls["i"] += 1; return v
            _orig_dc = aic.deepseek_chat
            aic.deepseek_chat = fake_chat
            # ai_generate 走 _category_roots_zh(→中文树)，直接打桩这个 seam（离线、无 key）
            app._category_roots_zh = lambda settings: [
                {"description_category_id": 1, "category_name": "A", "children": [
                    {"type_id": 2, "type_name": "B", "description_category_id": 1}]}]
            app._category_attrs = lambda c, t: [{"id": 4180, "name": "Материал", "is_required": True, "dictionary_id": 1, "is_collection": False},
                                                {"id": 85, "name": "Бренд", "is_required": True, "dictionary_id": 1, "is_collection": False}]
            app._resolve_values = lambda c, t, aid, texts, coll: [{"dictionary_value_id": 9, "value": texts[0]}]
            try:
                r = TestClient(main_mod.app).post(f"/api/drafts/{d['id']}/ai-generate")
                self.assertEqual(r.status_code, 200)
                body = r.json()
                self.assertTrue(body["ok"])
                # mode 为 draft（默认 ai_auto_apply=False）
                self.assertEqual(body.get("mode"), "draft")
                # proposal 为 draft_json，生成内容在 fields 子键中
                proposal = body.get("proposal") or {}
                fields = proposal.get("fields") or {}
                self.assertEqual(str(fields.get("category_id")), "1")
                self.assertEqual(fields.get("ozon_title"), "Держатель")
                # 无品牌解析：fake resolve 回显 texts[0]=NO_BRAND → brand_name 即 "Нет бренда"
                self.assertEqual(fields.get("brand_name"), "Нет бренда")
                # report 字段应存在
                self.assertIn("report", body)
                # 关键验证：草稿主字段在 DB 中未被修改（category_id 仍为空）
                draft_after = app.store.get_draft(d["id"])
                self.assertEqual(str(draft_after.get("category_id") or "").strip(), "",
                                 "ai_generate 不应持久化主字段：category_id 应仍为空")
                self.assertEqual(draft_after.get("ozon_title") or "", draft_before.get("ozon_title") or "",
                                 "ai_generate 不应持久化主字段：ozon_title 不应改变")
            finally:
                aic.deepseek_chat = _orig_dc   # 复原模块级打桩，避免污染后续测试(test_deepseek_images 等)
                app.store.close()
                import gc; gc.collect()  # 释放 TestClient/连接句柄，否则 Windows 删不掉临时库
                # 复原模块级 APP（指回原库），避免污染后续不 reload 的测试（test_api 等）
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)
                importlib.reload(main_mod)

    def test_brand_warning_when_no_brand_resolve_fails(self):
        """当无品牌(Нет бренда)字典值解析失败时，report.brand_warning 应非空，report.unmapped 应含品牌条目。"""
        import importlib, tempfile, json as J
        from pathlib import Path
        from fastapi.testclient import TestClient
        import backend.store as store_mod
        orig_db = store_mod.DEFAULT_DB
        with tempfile.TemporaryDirectory() as tmp:
            store_mod.DEFAULT_DB = Path(tmp) / "brand_warn.db"
            import backend.app_service as svc; importlib.reload(svc)
            import backend.main as main_mod; importlib.reload(main_mod)
            app = main_mod.APP
            from backend.drafts import create_draft_from_url
            d = app.store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/987654321012.html"))
            app.store.update_draft(d["id"], {"source_raw": {"title": "测试品", "params": [], "description_text": "无"}})
            import backend.ai_card as aic
            seq = ['{"index":0}', '{"index":0}',
                   J.dumps({"ozon_title": "Держатель", "description": "Опис", "hashtags": []}),
                   J.dumps({"attributes": []})]
            calls = {"i": 0}
            def fake_chat2(settings, s, u, images=None):
                v = seq[calls["i"]]; calls["i"] += 1; return v
            _orig_dc2 = aic.deepseek_chat
            aic.deepseek_chat = fake_chat2
            app._category_roots_zh = lambda settings: [
                {"description_category_id": 1, "category_name": "A", "children": [
                    {"type_id": 2, "type_name": "B", "description_category_id": 1}]}]
            app._category_attrs = lambda c, t: [{"id": 85, "name": "Бренд", "is_required": True, "dictionary_id": 1, "is_collection": False}]
            # 无品牌解析失败：resolve 对 attr 85 返回空列表
            def no_brand_fails(c, t, aid, texts, coll):
                if aid == 85:
                    return []
                return [{"dictionary_value_id": 9, "value": texts[0]}]
            app._resolve_values = no_brand_fails
            try:
                r = TestClient(main_mod.app).post(f"/api/drafts/{d['id']}/ai-generate")
                self.assertEqual(r.status_code, 200)
                body = r.json()
                self.assertTrue(body["ok"])
                # brand_warning 在 report 里
                report = body.get("report") or {}
                self.assertIn("brand_warning", report)
                self.assertIsNotNone(report["brand_warning"])
                self.assertIn("Нет бренда", report["brand_warning"])
                # unmapped 列表里也应包含品牌警告条目
                unmapped = report.get("unmapped") or []
                unmapped_names = [u.get("name") or "" for u in unmapped]
                unmapped_values = [u.get("value") or "" for u in unmapped]
                has_brand_in_unmapped = any("Бренд" in n or "Нет бренда" in v
                                            for n, v in zip(unmapped_names, unmapped_values))
                self.assertTrue(has_brand_in_unmapped,
                                f"report.unmapped 应包含品牌警告, 实际: {unmapped}")
            finally:
                aic.deepseek_chat = _orig_dc2   # 复原模块级打桩，避免污染后续测试
                app.store.close()
                import gc; gc.collect()
                store_mod.DEFAULT_DB = orig_db
                importlib.reload(svc)
                importlib.reload(main_mod)
