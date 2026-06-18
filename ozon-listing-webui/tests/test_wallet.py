import importlib
import tempfile
import unittest
from pathlib import Path

from backend.store import Store


class WalletStoreTest(unittest.TestCase):
    def _store(self, tmp):
        return Store(Path(tmp) / "w.db")

    def test_recharge_and_balance(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                acc = s.recharge(100, remark="test", user_id=1)
                self.assertEqual(acc["balance"], 100)
                self.assertEqual(acc["total_recharge"], 100)
                self.assertEqual(len(s.list_txns(1)), 1)
            finally:
                s.close()

    def test_deduct_atomic(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.recharge(50, user_id=1)
                self.assertTrue(s.deduct(30, biz_no="x", user_id=1))
                self.assertEqual(s.get_account(1)["balance"], 20)
                self.assertFalse(s.deduct(30, user_id=1))  # 余额不足
                self.assertEqual(s.get_account(1)["balance"], 20)  # 不变
                self.assertEqual(s.get_account(1)["total_consume"], 30)
            finally:
                s.close()

    def test_refund(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.recharge(50, user_id=1)
                s.deduct(20, user_id=1)
                s.refund(20, biz_no="r", user_id=1)
                self.assertEqual(s.get_account(1)["balance"], 50)
            finally:
                s.close()

    def test_wallet_isolated_by_user(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            s = self._store(tmp)
            try:
                s.recharge(100, user_id=1)
                s.recharge(7, user_id=2)
                self.assertEqual(s.get_account(1)["balance"], 100)
                self.assertEqual(s.get_account(2)["balance"], 7)
                self.assertEqual(len(s.list_txns(1)), 1)
                self.assertEqual(len(s.list_txns(2)), 1)
            finally:
                s.close()


class WalletPublishFeeTest(unittest.TestCase):
    def _app(self, tmp):
        import backend.store as store_mod
        store_mod.DEFAULT_DB = Path(tmp) / "wf.db"
        import backend.app_service as svc
        importlib.reload(svc)
        return svc

    def _ready_draft(self, app):
        from backend.drafts import create_draft_from_url
        d = app.store.insert_draft(create_draft_from_url("https://detail.1688.com/offer/777.html"))
        app.store.update_draft(d["id"], {
            "ozon_title": "Тест", "description": "D", "category_id": "1", "type_id": "2",
            "price": "100", "images": ["https://ir.ozone.ru/a.jpg"],
            "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        })
        return d["id"]

    def test_publish_blocked_when_balance_insufficient(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k",
                                         "rub_cny": 0.1, "contract_currency": "CNY", "publish_fee": 5})
                app._category_attrs = lambda c, t: []
                did = self._ready_draft(app)
                r = app.publish(did)
                self.assertFalse(r["published"])
                self.assertTrue(any("余额" in e for e in r["errors"]))
            finally:
                app.store.close()

    def test_publish_deducts_fee_on_success(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            svc = self._app(tmp); app = svc.App()
            try:
                app.store.save_settings({"ozon_client_id": "1", "ozon_api_key": "k",
                                         "rub_cny": 0.1, "contract_currency": "CNY", "publish_fee": 5})
                app._category_attrs = lambda c, t: []
                svc.publish_items = lambda settings, items: {"result": {"task_id": 0}}
                app.store.recharge(100, user_id=1)
                did = self._ready_draft(app)
                app.publish(did)
                self.assertEqual(app.store.get_account(1)["balance"], 95)  # 扣了 5
            finally:
                app.store.close()


if __name__ == "__main__":
    unittest.main()
