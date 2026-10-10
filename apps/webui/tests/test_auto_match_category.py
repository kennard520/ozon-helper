import importlib
import tempfile
import unittest
from pathlib import Path


class AutoMatchCategoryTest(unittest.TestCase):
    def _app(self, tmp):
        import webui.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "amc.db"
        import webui.app_service as svc
        importlib.reload(svc)
        app = svc.App()
        app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k"})
        return app

    def test_disambiguates_naushniki_to_electronics(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                # 叶子 "Наушники" 两个义项：服装毛皮耳罩 vs 电子耳机
                app.catalog_ru.search = lambda client, seg, limit=30: [
                    {"description_category_id": 200, "type_id": 11, "path": "Одежда/Аксессуары/Меховые наушники"},
                    {"description_category_id": 100, "type_id": 22, "path": "Электроника/Аудиотехника/Наушники"},
                ]
                scraped = {"category_path": "Электроника/Наушники и аудиотехника/Наушники"}
                app._auto_match_category(scraped)
                # 面包屑含 Электроника → 选电子耳机(100)，不是服装耳罩(200)
                self.assertEqual(scraped["category_id"], "100")
                self.assertEqual(scraped["type_id"], "22")
            finally:
                app.store.close()

    def test_clothing_breadcrumb_picks_clothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                app.catalog_ru.search = lambda client, seg, limit=30: [
                    {"description_category_id": 200, "type_id": 11, "path": "Одежда/Аксессуары/Меховые наушники"},
                    {"description_category_id": 100, "type_id": 22, "path": "Электроника/Аудиотехника/Наушники"},
                ]
                # 面包屑是服装 → 选服装耳罩(200)
                scraped = {"category_path": "Одежда/Аксессуары/Наушники"}
                app._auto_match_category(scraped)
                self.assertEqual(scraped["category_id"], "200")
            finally:
                app.store.close()

    def test_uses_tip_attribute_value_first(self):
        # 商品声明的 Тип 值优先当搜索种子（最精准），而非只用面包屑叶子
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                seeds_seen = []

                def fake_search(client, seg, limit=30):
                    seeds_seen.append(seg)
                    if seg == "Спрей для полости рта":
                        return [{"description_category_id": 777, "type_id": 33,
                                 "path": "Красота и здоровье/Уход за полостью рта/Спрей"}]
                    return []

                app.catalog_ru.search = fake_search
                scraped = {
                    "category_path": "Красота/Гигиена/Спреи",
                    "attributes": [
                        {"name": "Тип", "value": "Спрей для полости рта"},
                        {"name": "Аромат", "value": "Свежий"},
                    ],
                }
                app._auto_match_category(scraped)
                self.assertEqual(seeds_seen[0], "Спрей для полости рта")  # Тип 值排第一个搜
                self.assertEqual(scraped["category_id"], "777")
                self.assertEqual(scraped["type_id"], "33")
            finally:
                app.store.close()

    def test_no_path_no_change(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = self._app(tmp)
            try:
                scraped = {}
                app._auto_match_category(scraped)
                self.assertNotIn("category_id", scraped)
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
