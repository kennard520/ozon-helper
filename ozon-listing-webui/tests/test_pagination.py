from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import backend.store as store_mod
from backend.store import Store


def _draft(**over):
    d = {
        "source_platform": "1688", "source_url": "u", "source_offer_id": "1",
        "source_title": "t", "ozon_title": "T", "description": "d",
        "category_id": "1", "type_id": "2", "price": "100", "old_price": "100",
        "stock": 1, "weight_g": 100, "length_mm": 10, "width_mm": 10, "height_mm": 10,
        "images": ["x"], "attributes": {}, "status": "draft",
        "publish_response": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    d.update(over)
    return d


class TestPagination(unittest.TestCase):
    def test_page_and_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "p.db")
            for i in range(25):
                store.insert_draft(_draft(source_url=f"u{i}", source_offer_id=str(i)))
            rows, total = store.list_drafts_page(page=1, page_size=20)
            self.assertEqual(total, 25)
            self.assertEqual(len(rows), 20)
            rows2, total2 = store.list_drafts_page(page=2, page_size=20)
            self.assertEqual(total2, 25)
            self.assertEqual(len(rows2), 5)
            # 第 2 页不与第 1 页重叠
            ids1 = {r["id"] for r in rows}
            ids2 = {r["id"] for r in rows2}
            self.assertFalse(ids1 & ids2)
            store.close()

    def test_status_filter_paging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "p.db")
            a = store.insert_draft(_draft(source_url="a", source_offer_id="1"))
            store.insert_draft(_draft(source_url="b", source_offer_id="2"))
            store.update_draft(a["id"], {"status": "published"})
            rows, total = store.list_drafts_page(status="published", page=1, page_size=20)
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["id"], a["id"])
            store.close()

    def test_count_by_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "p.db")
            a = store.insert_draft(_draft(source_url="a", source_offer_id="1"))
            store.insert_draft(_draft(source_url="b", source_offer_id="2"))
            store.update_draft(a["id"], {"status": "published"})
            c = store.count_by_status()
            self.assertEqual(c["all"], 2)
            self.assertEqual(c["published"], 1)
            store.close()

    def test_page_size_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "p.db")
            store.insert_draft(_draft(source_url="a", source_offer_id="1"))
            rows, total = store.list_drafts_page(page=1, page_size=99999)
            self.assertEqual(total, 1)  # 不报错，page_size 被夹到上限
            store.close()


if __name__ == "__main__":
    unittest.main()
