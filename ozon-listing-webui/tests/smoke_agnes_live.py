"""Agnes AI 真网冒烟（手动跑，不进 unittest discover）：
PYTHONIOENCODING=utf-8 python tools/ozon-listing-webui/tests/smoke_agnes_live.py [chat|image|video|all]
读 data/products.db 里的 agnes_api_key（先在设置页配好）。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.store import Store  # noqa: E402
from backend import agnes  # noqa: E402


def smoke_chat(s: dict) -> None:
    out = agnes.agnes_chat(s, "You are a helpful assistant.", "Reply with exactly one word: PONG")
    print("CHAT OK:", out[:60])


def smoke_image(s: dict) -> str:
    url = agnes.generate_image(
        s, "A minimal product photo of a red coffee mug on a clean white studio background, soft shadow",
        size="1024x768")
    print("IMAGE OK:", url[:110])
    return url


def smoke_video(s: dict, image_url: str | None = None) -> None:
    t = agnes.create_video_task(
        s, "Slow cinematic camera orbit around the product, soft studio lighting, "
           "the product stays centered and visually identical to the reference image",
        image=image_url, num_frames=81, frame_rate=24)   # 81帧≈3s，冒烟用最短
    print("VIDEO TASK:", t)
    for i in range(120):   # 最多等 10 分钟
        q = agnes.query_video(s, t["video_id"])
        print(f"  poll#{i}: status={q['status']} progress={q['progress']}")
        if q["status"] == "completed":
            print("VIDEO OK:", q["url"][:110])
            return
        if q["status"] == "failed":
            print("VIDEO FAILED:", q["error"])
            return
        time.sleep(5)
    print("VIDEO TIMEOUT (10min)")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    settings = Store().get_settings()
    if which in ("chat", "all"):
        smoke_chat(settings)
    img = sys.argv[2] if len(sys.argv) > 2 else None   # video 可单独给参考图 URL
    if which in ("image", "all"):
        img = smoke_image(settings)
    if which in ("video", "all"):
        smoke_video(settings, image_url=img)
