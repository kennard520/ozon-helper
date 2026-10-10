"""Agnes 视频生成后台任务：创建任务 → 每 5s 轮询 → 完成回写草稿（回调注入）。

范本 batch_collect：模块级状态机 + 锁 + stop 事件 + 守护线程；
create_fn/query_fn/on_done/_sleep 全部可注入单测（无网络）。
全局单任务（同一时间只跑一个视频；视频生成几十秒到几分钟，串行够用）。
"""
from __future__ import annotations

import threading
from typing import Callable

POLL_INTERVAL = 5.0
TIMEOUT_S = 1800.0   # 30 分钟没完成按超时处理

_lock = threading.Lock()
_stop = threading.Event()
_state: dict = {
    "status": "idle", "draft_id": 0, "video_id": "",
    "progress": 0, "url": "", "last_error": "",
}


def _sleep(seconds: float) -> None:   # 可注入单测（no-op）
    import time  # noqa: PLC0415
    time.sleep(seconds)


def _now() -> float:   # 可注入单测；超时用单调钟（查询本身的耗时也要计入）
    import time  # noqa: PLC0415
    return time.monotonic()


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def video_status() -> dict:
    with _lock:
        return dict(_state)


def request_stop() -> dict:
    _stop.set()
    return video_status()


def _run(create_fn: Callable[[], dict], query_fn: Callable[[str], dict],
         on_done: Callable[[int, str], None], draft_id: int) -> None:
    try:
        task = create_fn()
        vid = str(task.get("video_id") or "").strip()
        if not vid:
            _set(status="error", last_error="视频任务创建未返回 video_id")
            return
        _set(video_id=vid)
        deadline = _now() + TIMEOUT_S
        while True:
            if _stop.is_set():
                _set(status="stopped")
                return
            if _now() > deadline:
                _set(status="error", last_error="视频生成超时（30 分钟）")
                return
            q = query_fn(vid)
            _set(progress=int(q.get("progress") or 0))
            st = str(q.get("status") or "")
            if st == "completed":
                url = str(q.get("url") or "")
                if not url:
                    _set(status="error", last_error="任务完成但未返回视频 URL")
                    return
                on_done(draft_id, url)   # 回写草稿（video_url + 本地预览副本）
                _set(status="done", url=url, progress=100)
                return
            if st == "failed":
                _set(status="error", last_error=str(q.get("error") or "视频生成失败"))
                return
            _sleep(POLL_INTERVAL)
    except Exception as exc:  # noqa: BLE001
        _set(status="error", last_error=str(exc))


def start_video(create_fn: Callable[[], dict], query_fn: Callable[[str], dict],
                on_done: Callable[[int, str], None], draft_id: int) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _stop.clear()
        _state.update({"status": "running", "draft_id": int(draft_id), "video_id": "",
                       "progress": 0, "url": "", "last_error": ""})
    threading.Thread(target=_run, args=(create_fn, query_fn, on_done, draft_id),
                     daemon=True).start()
    return video_status()
