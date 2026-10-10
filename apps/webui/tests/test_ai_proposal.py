from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

import webui.store as store_mod
from webui.ai_card import build_proposal_draft
from webui.store import Store

# Capture the original DEFAULT_DB before any test mutates it, so tearDownModule can restore it.
_ORIG_DEFAULT_DB = store_mod.DEFAULT_DB


def tearDownModule():
    """Restore global singletons mutated by reload-based tests so later test modules are not polluted."""
    import importlib
    store_mod.DEFAULT_DB = _ORIG_DEFAULT_DB
    import webui.app_service as _svc; importlib.reload(_svc)
    import webui.main as _main; importlib.reload(_main)


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u", "source_offer_id": "1",
        "source_title": "t", "ozon_title": "T", "description": "d",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["x"], "attributes": {}, "status": "draft", "publish_response": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over); return d


class TestAiProposalColumn(unittest.TestCase):
    def test_column_exists_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            with store._session_engine.begin() as c:
                cols = {r[1] for r in c.execute(text("PRAGMA table_info(drafts)"))}
            self.assertIn("ai_proposal_json", cols)
            d = store.insert_draft(_draft())
            self.assertIsNone(store.get_draft(d["id"])["ai_proposal"])
            store.set_ai_proposal(d["id"], {"fields": {"ozon_title": "RU"}, "attributes": []})
            got = store.get_draft(d["id"])["ai_proposal"]
            self.assertEqual(got["fields"]["ozon_title"], "RU")
            store.set_ai_proposal(d["id"], None)
            self.assertIsNone(store.get_draft(d["id"])["ai_proposal"])
            store.close()

    def test_corrupt_proposal_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "t.db")
            d = store.insert_draft(_draft())
            with store._session_engine.begin() as c:
                c.execute(
                    text("UPDATE drafts SET ai_proposal_json=:v WHERE id=:id"),
                    {"v": "{bad json", "id": d["id"]},
                )
            self.assertIsNone(store.get_draft(d["id"])["ai_proposal"])
            store.close()


class TestBuildProposalDraft(unittest.TestCase):
    def test_assembles_fields_and_missing_attrs(self):
        proposal = {
            "category_id": "10", "type_id": "20", "ozon_title": "RU title",
            "description": "RU desc", "brand_name": "Нет бренда",
            "weight_g": 50, "length_mm": 3, "width_mm": 2, "height_mm": 1,
            "attributes": [{"id": 9048, "values": [{"value": "ModelX"}]}],
        }
        report = {
            "category_path": "A / B", "keywords": ["k1"],
            "mapped": [{"id": 9048, "name": "Название модели", "value": "ModelX"}],
            "unmapped": [],
        }
        required = [{"id": 9048, "name": "Название модели", "is_required": True},
                    {"id": 4194, "name": "Тип", "is_required": True}]
        optional = [{"id": 10096, "name": "Цвет", "is_required": False}]
        draft = build_proposal_draft(proposal, report, required, optional, ts="2026-06-01T00:00:00+00:00")

        self.assertEqual(draft["fields"]["ozon_title"], "RU title")
        self.assertEqual(draft["fields"]["weight_g"], 50)
        self.assertEqual(draft["fields"]["brand_name"], "Нет бренда")
        self.assertEqual(draft["keywords"], ["k1"])
        by_id = {a["id"]: a for a in draft["attributes"]}
        self.assertEqual(by_id[9048]["source"], "ai")
        self.assertEqual(by_id[9048]["value"], "ModelX")
        self.assertEqual(by_id[4194]["source"], "missing")
        self.assertTrue(by_id[4194]["required"])
        self.assertEqual(by_id[10096]["source"], "missing")
        self.assertFalse(by_id[10096]["required"])

    def test_brand_not_in_attributes(self):
        proposal = {"category_id": "1", "type_id": "2", "ozon_title": "", "description": "",
                    "brand_name": "Нет бренда", "attributes": []}
        report = {"mapped": [], "unmapped": [], "keywords": []}
        required = [{"id": 85, "name": "Бренд", "is_required": True}]
        draft = build_proposal_draft(proposal, report, required, [], ts="t")
        self.assertFalse(any(a["id"] == 85 for a in draft["attributes"]))

    def test_brand_id_carried_when_present(self):
        proposal = {"category_id": "1", "type_id": "2", "ozon_title": "", "description": "",
                    "brand_name": "Нет бренда", "brand_id": 999, "attributes": []}
        report = {"mapped": [], "unmapped": [], "keywords": []}
        draft = build_proposal_draft(proposal, report, [], [], ts="t")
        self.assertEqual(draft["fields"]["brand_id"], 999)

    def test_brand_id_absent_when_missing(self):
        proposal = {"category_id": "1", "type_id": "2", "ozon_title": "", "description": "",
                    "brand_name": "Нет бренда", "attributes": []}
        report = {"mapped": [], "unmapped": [], "keywords": []}
        draft = build_proposal_draft(proposal, report, [], [], ts="t")
        self.assertNotIn("brand_id", draft["fields"])


class TestAutoApplySetting(unittest.TestCase):
    def test_default_false_and_saveable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.db")
            self.assertNotIn("ai_auto_apply", store.get_settings())
            store.save_settings({"ai_auto_apply": True})
            self.assertTrue(store.get_settings()["ai_auto_apply"])
            store.close()

    def test_state_exposes_ai_auto_apply(self):
        # 设置页 backfill 需要 state() 回传 ai_auto_apply，否则刷新后开关回显丢失
        with tempfile.TemporaryDirectory() as tmp:
            import importlib
            store_mod.DEFAULT_DB = Path(tmp) / "st.db"
            import webui.app_service as svc; importlib.reload(svc)
            app = svc.App()
            try:
                self.assertFalse(app.state()["settings"]["ai_auto_apply"])   # 默认 false
                app.store.save_settings({"ai_auto_apply": True})
                self.assertTrue(app.state()["settings"]["ai_auto_apply"])
            finally:
                app.store.close()


class TestApplyAiProposal(unittest.TestCase):
    def _app(self, tmp):
        import importlib
        store_mod.DEFAULT_DB = Path(tmp) / "a.db"
        import webui.app_service as svc
        importlib.reload(svc)
        app = svc.App()
        app._resolve_values = lambda cat, typ, aid, texts, is_coll: [{"value": t} for t in texts]
        return app

    def test_apply_merges_fields_and_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft(ozon_title="OLD", category_id="1", type_id="2"))
                app.store.set_ai_proposal(d["id"], {
                    "fields": {"ozon_title": "NEW RU", "category_id": "10", "type_id": "20",
                               "brand_name": "Нет бренда"},
                    "attributes": [{"id": 9048, "name": "M", "value": "ModelX", "source": "ai"},
                                   {"id": 4194, "name": "T", "value": "", "source": "missing"}],
                    "keywords": [],
                })
                r = app.apply_ai_proposal(d["id"])
                self.assertTrue(r["ok"])
                got = app.store.get_draft(d["id"])
                self.assertEqual(got["ozon_title"], "NEW RU")
                self.assertEqual(got["category_id"], "10")
                self.assertIsNone(got["ai_proposal"])
                ids = {a["id"] for a in got["attributes"] if isinstance(a, dict) and "id" in a}
                self.assertIn(9048, ids)
                self.assertNotIn(4194, ids)
            finally:
                app.store.close()

    def test_deleted_field_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft(ozon_title="KEEP"))
                app.store.set_ai_proposal(d["id"], {"fields": {"description": "NEW"}, "attributes": []})
                app.apply_ai_proposal(d["id"])
                got = app.store.get_draft(d["id"])
                self.assertEqual(got["ozon_title"], "KEEP")
                self.assertEqual(got["description"], "NEW")
            finally:
                app.store.close()

    def test_apply_no_proposal_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                with self.assertRaises(ValueError):
                    app.apply_ai_proposal(d["id"])
            finally:
                app.store.close()

    def test_passthrough_attrs_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft(category_id="1", type_id="2"))
                # 草稿已有：1 个采集 passthrough(无 values) + 1 个上架格式
                app.store.update_draft(d["id"], {"attributes": [
                    {"name": "采集色", "value": "красный"},          # passthrough
                    {"id": 5000, "values": [{"value": "old"}]},      # publish-format
                ]})
                app.store.set_ai_proposal(d["id"], {
                    "fields": {}, "attributes": [
                        {"id": 9048, "name": "M", "value": "X", "source": "ai"}], "keywords": []})
                app.apply_ai_proposal(d["id"])
                attrs = app.store.get_draft(d["id"])["attributes"]
                # passthrough 仍在
                self.assertTrue(any(a.get("name") == "采集色" for a in attrs))
                # 旧上架项 5000 仍在
                ids = {a["id"] for a in attrs if "id" in a and "values" in a}
                self.assertIn(5000, ids)
                self.assertIn(9048, ids)
            finally:
                app.store.close()

    def test_apply_carries_brand_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                app.store.set_ai_proposal(d["id"], {
                    "fields": {"brand_name": "Нет бренда", "brand_id": 777}, "attributes": []})
                app.apply_ai_proposal(d["id"])
                got = app.store.get_draft(d["id"])
                self.assertEqual(got["brand_id"], 777)
                self.assertEqual(got["brand_name"], "Нет бренда")
            finally:
                app.store.close()

    def test_bad_attr_id_skipped_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft(category_id="1", type_id="2"))
                app.store.set_ai_proposal(d["id"], {
                    "fields": {"ozon_title": "OK"}, "attributes": [
                        {"id": None, "name": "坏", "value": "x", "source": "ai"},
                        {"id": 9048, "name": "好", "value": "y", "source": "ai"}], "keywords": []})
                r = app.apply_ai_proposal(d["id"])   # 不应抛
                self.assertTrue(r["ok"])
                got = app.store.get_draft(d["id"])
                self.assertEqual(got["ozon_title"], "OK")
                self.assertIsNone(got["ai_proposal"])   # 草案已清空
                ids = {a["id"] for a in got["attributes"] if "id" in a and "values" in a}
                self.assertIn(9048, ids)
            finally:
                app.store.close()


class TestPatchAiProposal(unittest.TestCase):
    def _app(self, tmp):
        import importlib
        store_mod.DEFAULT_DB = Path(tmp) / "p.db"
        import webui.app_service as svc
        importlib.reload(svc)
        return svc.App()

    def _seed(self, app):
        d = app.store.insert_draft(_draft())
        app.store.set_ai_proposal(d["id"], {
            "fields": {"ozon_title": "T", "description": "D"},
            "attributes": [{"id": 9048, "name": "M", "value": "X", "source": "ai"},
                           {"id": 4194, "name": "T", "value": "", "source": "missing"}],
            "keywords": [],
        })
        return d

    def test_edit_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = self._seed(app)
                app.patch_ai_proposal(d["id"], {"op": "edit_field", "key": "ozon_title", "value": "T2"})
                self.assertEqual(app.store.get_draft(d["id"])["ai_proposal"]["fields"]["ozon_title"], "T2")
            finally:
                app.store.close()

    def test_delete_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = self._seed(app)
                app.patch_ai_proposal(d["id"], {"op": "delete_field", "key": "description"})
                self.assertNotIn("description", app.store.get_draft(d["id"])["ai_proposal"]["fields"])
            finally:
                app.store.close()

    def test_edit_attr_marks_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = self._seed(app)
                app.patch_ai_proposal(d["id"], {"op": "edit_attr", "id": 4194, "value": "Гель"})
                attrs = {a["id"]: a for a in app.store.get_draft(d["id"])["ai_proposal"]["attributes"]}
                self.assertEqual(attrs[4194]["value"], "Гель")
            finally:
                app.store.close()

    def test_delete_attr(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = self._seed(app)
                app.patch_ai_proposal(d["id"], {"op": "delete_attr", "id": 9048})
                ids = {a["id"] for a in app.store.get_draft(d["id"])["ai_proposal"]["attributes"]}
                self.assertNotIn(9048, ids)
            finally:
                app.store.close()

    def test_discard_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = self._seed(app)
                app.patch_ai_proposal(d["id"], {"op": "discard"})
                self.assertIsNone(app.store.get_draft(d["id"])["ai_proposal"])
            finally:
                app.store.close()

    def test_unknown_op_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = self._seed(app)
                with self.assertRaises(ValueError):
                    app.patch_ai_proposal(d["id"], {"op": "bogus"})
            finally:
                app.store.close()

    def test_no_proposal_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            try:
                d = app.store.insert_draft(_draft())
                with self.assertRaises(ValueError):
                    app.patch_ai_proposal(d["id"], {"op": "edit_field", "key": "x", "value": "y"})
            finally:
                app.store.close()


class TestAiGenerateModes(unittest.TestCase):
    def _app(self, tmp, auto):
        import importlib
        store_mod.DEFAULT_DB = Path(tmp) / "g.db"
        import webui.app_service as svc
        importlib.reload(svc)
        app = svc.App()
        app.store.save_settings({"ai_auto_apply": auto})
        app._resolve_values = lambda *a, **k: ([{"value": a[3][0]}] if a[3] else [])
        app._no_brand_value = lambda cat, typ: None
        app._category_roots_zh = lambda settings: []   # generate_card 已被打桩，类目树不参与
        app._category_attrs = lambda cat, typ: [
            {"id": 9048, "name": "M", "is_required": True},
            {"id": 4194, "name": "T", "is_required": True},
        ]
        import webui.ai_card as aic
        self._orig_gen = aic.generate_card
        aic.generate_card = lambda raw, **kw: {
            "ok": True, "category_id": "10", "type_id": "20", "category_path": "A/B",
            "ozon_title": "RU", "description": "DESC", "attributes": [{"id": 9048, "values": [{"value": "X"}]}],
            "weight_g": 0, "length_mm": 0, "width_mm": 0, "height_mm": 0,
            "mapped": [{"id": 9048, "name": "M", "value": "X"}], "unmapped": [],
            "keywords": ["k"], "category_fallback": False,
        }
        return app, aic

    def test_manual_mode_writes_draft_not_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, aic = self._app(tmp, auto=False)
            try:
                d = app.store.insert_draft(_draft(ozon_title="ORIG"))
                r = app.ai_generate(d["id"])
                self.assertEqual(r["mode"], "draft")
                got = app.store.get_draft(d["id"])
                self.assertEqual(got["ozon_title"], "ORIG")
                self.assertIsNotNone(got["ai_proposal"])
                self.assertEqual(got["ai_proposal"]["fields"]["ozon_title"], "RU")
            finally:
                aic.generate_card = self._orig_gen; app.store.close()

    def test_auto_mode_merges_no_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, aic = self._app(tmp, auto=True)
            try:
                d = app.store.insert_draft(_draft(ozon_title="ORIG"))
                r = app.ai_generate(d["id"])
                self.assertEqual(r["mode"], "applied")
                got = app.store.get_draft(d["id"])
                self.assertEqual(got["ozon_title"], "RU")
                self.assertIsNone(got["ai_proposal"])
            finally:
                aic.generate_card = self._orig_gen; app.store.close()


class TestAiProposalRoutes(unittest.TestCase):
    def _client(self, tmp):
        import importlib
        from pathlib import Path as P

        from fastapi.testclient import TestClient
        store_mod.DEFAULT_DB = P(tmp) / "r.db"
        import webui.app_service as svc; importlib.reload(svc)
        import webui.main as main_mod; importlib.reload(main_mod)
        return TestClient(main_mod.app), main_mod

    def test_patch_and_apply_routes(self):
        tmp = tempfile.mkdtemp()
        client, main_mod = self._client(tmp)
        try:
            d = main_mod.APP.store.insert_draft(_draft(category_id="1", type_id="2"))
            main_mod.APP.store.set_ai_proposal(d["id"], {
                "fields": {"ozon_title": "T"}, "attributes": [], "keywords": []})
            rp = client.patch(f"/api/drafts/{d['id']}/ai-proposal",
                              json={"op": "edit_field", "key": "ozon_title", "value": "T2"})
            self.assertEqual(rp.status_code, 200)
            ra = client.post(f"/api/drafts/{d['id']}/ai-proposal/apply")
            self.assertEqual(ra.status_code, 200)
            self.assertEqual(ra.json()["draft"]["ozon_title"], "T2")
        finally:
            main_mod.APP.store.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_apply_without_proposal_400(self):
        tmp = tempfile.mkdtemp()
        client, main_mod = self._client(tmp)
        try:
            d = main_mod.APP.store.insert_draft(_draft())
            ra = client.post(f"/api/drafts/{d['id']}/ai-proposal/apply")
            self.assertEqual(ra.status_code, 400)
        finally:
            main_mod.APP.store.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
