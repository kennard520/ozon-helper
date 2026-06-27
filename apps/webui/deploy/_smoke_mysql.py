# -*- coding: utf-8 -*-
"""MySQL 适配层冒烟测试：跑一遍覆盖 upsert/条件更新/lastrowid/LIKE 等翻译路径。
用法（容器内，设好 OZON_MYSQL_*，建议用独立库 OZON_MYSQL_DB=ozon_smoke）：
    python deploy/_smoke_mysql.py
全过打印 SMOKE_OK，否则 AssertionError。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
WEBUI = HERE.parents[1]
sys.path.insert(0, str(WEBUI))
from backend.store import Store  # noqa: E402


def main() -> None:
    assert os.environ.get("OZON_MYSQL_HOST"), "需要 OZON_MYSQL_* 环境变量"
    s = Store()  # 触发 init_mysql 建表

    # settings：ON CONFLICT upsert + SELECT ... WHERE user_id IN (0,?)
    s.save_settings({"rub_cny": 12.5, "jwt_secret": "smoke-secret"})
    g = s.get_settings()
    assert g.get("rub_cny") == 12.5, g.get("rub_cny")
    assert g.get("jwt_secret") == "smoke-secret"
    s.save_settings({"rub_cny": 9.9})                       # 同键再写 -> 走 DUPLICATE KEY UPDATE
    assert s.get_settings().get("rub_cny") == 9.9

    # 钱包：insert + update + 条件UPDATE(rowcount) + txn lastrowid
    s.get_account(1)
    s.recharge(100.0, user_id=1)
    assert s.get_account(1)["balance"] >= 100.0
    assert s.deduct(30.0, user_id=1) is True
    assert s.deduct(10 ** 9, user_id=1) is False           # 余额不足 -> rowcount!=1
    assert len(s.list_txns(1)) >= 2

    # 类目缓存：ON CONFLICT(language) upsert + 覆盖
    s.save_catalog_leaves("ZH_HANS", [{"id": 1, "name": "x"}])
    assert s.load_catalog_leaves("ZH_HANS")[0]["id"] == 1
    s.save_catalog_leaves("ZH_HANS", [{"id": 2}])
    assert s.load_catalog_leaves("ZH_HANS")[0]["id"] == 2

    # 仓库：ON CONFLICT(warehouse_id) upsert + bool 强转
    s.upsert_warehouses(
        [{"warehouse_id": 111, "name": "WH", "is_rfbs": True, "status": "ok"}],
        store_client_id="sc1")
    whs = s.list_warehouses("sc1")
    assert any(w["warehouse_id"] == 111 and w["is_rfbs"] is True for w in whs), whs

    # 跟卖快照：insert lastrowid + latest
    r = s.add_offer_snapshot(
        {"product_id": "P1", "follow_count": 3, "price_min": 1.0, "price_max": 2.0})
    assert r["id"] > 0
    assert s.latest_offer_snapshot("P1")["follow_count"] == 3

    # 属性值缓存：5列 ON CONFLICT upsert + LIKE(去掉 COLLATE NOCASE 后大小写不敏感)
    s.save_attribute_values(1, 2, 3, [{"id": 10, "value": "RedColor"}], "ZH_HANS")
    found = s.find_attribute_values(1, 2, 3, "redcolor", "ZH_HANS")
    assert any(x["id"] == 10 for x in found), found

    # 草稿计数（空）
    assert isinstance(s.count_by_status(1), dict)

    print("SMOKE_OK")


if __name__ == "__main__":
    main()
