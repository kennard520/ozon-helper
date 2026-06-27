# -*- coding: utf-8 -*-
"""把真实 SQLite 库的数据迁到 MySQL（一次性）。

用法（容器内，已设 OZON_MYSQL_* 环境变量）：
    python deploy/migrate_sqlite_to_mysql.py /src.db

行为：先按最终形态在 MySQL 建表，再逐表 DELETE 后导入（幂等，可重跑），最后打印行数校验。
只迁应用表，按 (源列 ∩ 目标列) 取交集，列名全反引号（避开 key 等保留字）。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
WEBUI = HERE.parents[1]                      # deploy -> ozon-listing-webui
sys.path.insert(0, str(WEBUI))
from backend import db  # noqa: E402

TABLES = [
    "settings", "users", "accounts", "account_txns", "drafts", "commission_map",
    "catalog_cache", "catalog_tree_cache", "attribute_values_cache",
    "category_attr_cache", "warehouses", "postings", "procurement", "offer_snapshots",
]


def sqlite_tables(scon) -> set[str]:
    return {r[0] for r in scon.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def sqlite_cols(scon, t) -> list[str]:
    return [r[1] for r in scon.execute(f'PRAGMA table_info("{t}")').fetchall()]


def main() -> int:
    if not db.mysql_enabled():
        print("!! 未设置 OZON_MYSQL_HOST，拒绝运行")
        return 2
    src = sys.argv[1] if len(sys.argv) > 1 else str(WEBUI / "data" / "products.db")
    if not os.path.exists(src):
        print("!! 源 SQLite 不存在:", src)
        return 1

    import pymysql
    cfg = db.mysql_config()

    # 1) 建表（最终形态）
    conn = db.make_mysql_conn()
    db.init_mysql(conn)
    conn.close()

    scon = sqlite3.connect(src)
    scon.row_factory = sqlite3.Row
    stables = sqlite_tables(scon)

    m = pymysql.connect(charset="utf8mb4", autocommit=False, **cfg)
    mc = m.cursor()

    def mysql_cols(t) -> list[str]:
        mc.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (cfg["database"], t))
        return [r[0] for r in mc.fetchall()]

    mc.execute("SET FOREIGN_KEY_CHECKS=0")
    copied = {}
    for t in TABLES:
        if t not in stables:
            continue
        scols = sqlite_cols(scon, t)
        tcols = set(mysql_cols(t))
        cols = [c for c in scols if c in tcols]
        if not cols:
            continue
        sel = ", ".join(f'"{c}"' for c in cols)
        rows = scon.execute(f'SELECT {sel} FROM "{t}"').fetchall()
        mc.execute(f"DELETE FROM `{t}`")
        if rows:
            collist = ", ".join(f"`{c}`" for c in cols)
            ph = ", ".join(["%s"] * len(cols))
            data = [tuple(r[c] for c in cols) for r in rows]
            mc.executemany(f"INSERT INTO `{t}` ({collist}) VALUES ({ph})", data)
        copied[t] = len(rows)
    mc.execute("SET FOREIGN_KEY_CHECKS=1")
    m.commit()

    print("=== 迁移完成，MySQL 各表行数 ===")
    ok = True
    for t in TABLES:
        try:
            mc.execute(f"SELECT COUNT(*) FROM `{t}`")
            n = mc.fetchone()[0]
            src_n = copied.get(t, "-")
            flag = "" if (src_n == "-" or src_n == n) else "  <<< 行数不符!"
            if flag:
                ok = False
            print(f"  {t:<26} mysql={n:<7} src={src_n}{flag}")
        except Exception as e:
            print(f"  {t:<26} ERR {e}")
            ok = False
    scon.close()
    m.close()
    print("RESULT:", "OK" if ok else "MISMATCH")
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
