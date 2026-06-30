# -*- coding: utf-8 -*-
"""一次性：抓 Ozon 商品页 widgetStates，从图廊里找视频 URL。"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.collector import _JSONLD, PROFILE, _expand_page, launch_persistent_context  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else ""
OUT = str(ROOT / "_ozon_states.json")


def main():
    states = {}

    def on_resp(resp):
        try:
            u = resp.url
            if ("entrypoint-api.bx/page/json" in u) or ("composer-api.bx/widget/json" in u):
                d = json.loads(resp.text())
                ws = d.get("widgetStates")
                if isinstance(ws, dict):
                    states.update(ws)
        except Exception:
            pass

    PROFILE.mkdir(parents=True, exist_ok=True)
    ctx = launch_persistent_context(str(PROFILE), headless=False, locale="ru-RU", timezone="Europe/Moscow")
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_resp)
        page.goto(URL, wait_until="domcontentloaded", timeout=40000)
        try:
            page.wait_for_selector(_JSONLD, timeout=15000, state="attached")
        except Exception:
            pass
        _expand_page(page)
        time.sleep(1.5)
        html = page.content()
        Path(str(ROOT / "_ozon_page.html")).write_text(html, encoding="utf-8")
    finally:
        try:
            ctx.close()
        except Exception:
            pass

    Path(OUT).write_text(json.dumps(states, ensure_ascii=False), encoding="utf-8")
    blob = json.dumps(states, ensure_ascii=False)
    # 视频 URL 候选
    mp4 = sorted(set(re.findall(r'https?:\\?/\\?/[^"\\ ]+?\.(?:mp4|m3u8)', blob)))
    vod = sorted(set(re.findall(r'https?:\\?/\\?/[a-z0-9.-]*ozone?\.ru/[^"\\ ]*?(?:vod|video)[^"\\ ]*', blob)))
    # 图廊 widget
    gal = [k for k in states if "gallery" in k.lower() or "ozon.ru/video" in str(states[k]).lower()]
    print("widgets:", len(states))
    print("gallery widget keys:", gal[:5])
    print("mp4/m3u8:", [m.replace("\\/", "/") for m in mp4][:8])
    print("vod/video ozone:", [v.replace("\\/", "/") for v in vod][:8])


if __name__ == "__main__":
    main()
