from __future__ import annotations

import unittest

from ozon_api import copy_flow


class FakeClient:
    """模拟 OzonSellerClient 的 import_by_sku / get_import_info。"""

    def __init__(self, import_response: dict, poll_responses: list[dict] | None = None) -> None:
        self._import = import_response
        self._polls = list(poll_responses or [])
        self.import_calls: list[list[dict]] = []
        self.poll_calls: list[int] = []

    def import_by_sku(self, items: list[dict]) -> dict:
        self.import_calls.append(items)
        return self._import

    def get_import_info(self, task_id: int) -> dict:
        self.poll_calls.append(int(task_id))
        if self._polls:
            return self._polls.pop(0)
        return {"result": {"items": [{"status": "pending"}]}}


def _imp(task_id=None, unmatched=None) -> dict:
    return {"result": {"task_id": task_id, "unmatched_sku_list": unmatched or []}}


def _poll(*statuses, errors=None) -> dict:
    items = [{"status": s} for s in statuses]
    if errors is not None:
        items = [{"status": statuses[0] if statuses else "failed", "errors": errors}]
    return {"result": {"items": items}}


class BuildCopyItemTest(unittest.TestCase):
    def test_includes_required_omits_empty_optionals(self) -> None:
        item = copy_flow.build_copy_item(sku=123, offer_id="A1")
        self.assertEqual(item, {"sku": 123, "offer_id": "A1"})

    def test_includes_provided_optionals_as_strings(self) -> None:
        item = copy_flow.build_copy_item(
            sku="123", offer_id="A1", name="Тест", price=2300, old_price=2590,
            currency_code="CNY", vat="0.1")
        self.assertEqual(item, {
            "sku": 123, "offer_id": "A1", "name": "Тест",
            "price": "2300", "old_price": "2590", "currency_code": "CNY", "vat": "0.1"})


class ImportVerdictTest(unittest.TestCase):
    def test_task_id_and_not_unmatched_is_copyable(self) -> None:
        v = copy_flow.import_verdict(123, _imp(task_id=999))
        self.assertTrue(v["copyable"])
        self.assertEqual(v["task_id"], 999)

    def test_sku_in_unmatched_not_copyable(self) -> None:
        v = copy_flow.import_verdict(123, _imp(task_id=999, unmatched=[123]))
        self.assertFalse(v["copyable"])

    def test_no_task_id_not_copyable(self) -> None:
        self.assertFalse(copy_flow.import_verdict(123, _imp(task_id=None))["copyable"])


class PollVerdictTest(unittest.TestCase):
    def test_imported_is_created_copyable(self) -> None:
        v = copy_flow.poll_verdict(_poll("imported"))
        self.assertEqual(v["status"], "created")
        self.assertTrue(v["settled"] and v["copyable"])

    def test_moderating_counts_as_created(self) -> None:
        self.assertEqual(copy_flow.poll_verdict(_poll("moderating"))["status"], "created")

    def test_pending_not_settled(self) -> None:
        v = copy_flow.poll_verdict(_poll("pending"))
        self.assertFalse(v["settled"])

    def test_copying_prohibited_error_not_copyable(self) -> None:
        v = copy_flow.poll_verdict(_poll("failed", errors=[{"message": "Copying of this PDP is prohibited"}]))
        self.assertEqual(v["status"], "prohibited")
        self.assertFalse(v["copyable"])

    def test_plain_failed_not_copyable(self) -> None:
        v = copy_flow.poll_verdict(_poll("failed", errors=[{"message": "some other error"}]))
        self.assertEqual(v["status"], "failed")
        self.assertFalse(v["copyable"])


class CopyBySkuTest(unittest.TestCase):
    def _no_sleep(self, _seconds: float) -> None:
        return None

    def test_prohibited_at_import_skips_polling(self) -> None:
        client = FakeClient(_imp(task_id=999, unmatched=[123]))
        out = copy_flow.copy_by_sku(client, sku=123, offer_id="A1", price="2300", sleep=self._no_sleep)
        self.assertFalse(out["copyable"])
        self.assertEqual(out["status"], "not_copyable")
        self.assertEqual(client.poll_calls, [])  # 没轮询

    def test_success_imported(self) -> None:
        client = FakeClient(_imp(task_id=999), [_poll("imported")])
        out = copy_flow.copy_by_sku(client, sku=123, offer_id="A1", price="2300", sleep=self._no_sleep)
        self.assertTrue(out["copyable"])
        self.assertEqual(out["status"], "created")
        self.assertEqual(out["task_id"], 999)
        self.assertEqual(client.import_calls[0][0]["sku"], 123)

    def test_prohibited_at_poll(self) -> None:
        client = FakeClient(_imp(task_id=999),
                            [_poll("failed", errors=[{"code": "COPY_PROHIBITED"}])])
        out = copy_flow.copy_by_sku(client, sku=123, offer_id="A1", sleep=self._no_sleep)
        self.assertFalse(out["copyable"])
        self.assertEqual(out["status"], "prohibited")

    def test_timeout_stays_pending_copyable(self) -> None:
        client = FakeClient(_imp(task_id=999), [_poll("pending"), _poll("pending")])
        out = copy_flow.copy_by_sku(client, sku=123, offer_id="A1", poll_times=2, sleep=self._no_sleep)
        self.assertEqual(out["status"], "pending")
        self.assertTrue(out["copyable"])
        self.assertEqual(len(client.poll_calls), 2)


if __name__ == "__main__":
    unittest.main()
