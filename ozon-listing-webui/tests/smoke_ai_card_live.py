"""联网 smoke（手动跑）：对一个真实草稿跑 AI 生成卡片（真 DeepSeek + 本地类目树）。
前提：设置里 translate_engine=remote + base/key/model 已配；类目缓存在；草稿有内容。

    PYTHONIOENCODING=utf-8 PYTHONPATH=tools/ozon-listing-webui \
        python tools/ozon-listing-webui/tests/smoke_ai_card_live.py [draft_id]
"""
from __future__ import annotations

import sys

from backend.app_service import App


def main() -> int:
    app = App()
    try:
        drafts = app.store.list_drafts()
        if not drafts:
            print("ABORT: 没有草稿，先采集一个 1688 商品")
            return 2
        did = int(sys.argv[1]) if len(sys.argv) > 1 else drafts[0]["id"]
        print("draft:", did)
        r = app.ai_generate(did)
        if not r.get("ok"):
            print("FAIL:", r.get("error"))
            return 1
        d = r["draft"]
        print("类目:", r.get("category_path"), f"({d['category_id']}/{d['type_id']})")
        print("标题:", d["ozon_title"][:60])
        print("描述:", (d["description"] or "")[:80])
        print("品牌:", d.get("brand_name"))
        print("已填属性:", len(r["mapped"]), "| 没对上:", len(r["unmapped"]))
        print("关键词:", r.get("keywords"))
        print("SMOKE PASS")
        return 0
    finally:
        app.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
