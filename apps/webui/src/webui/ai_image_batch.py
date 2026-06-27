"""Agnes 批量商品图后台任务：多角度图生图 → 候选区。

范本 ai_video：模块级状态机 + 锁 + stop 事件 + 守护线程；
gen_fn/on_candidate/_sleep 全部可注入单测（无网络）。
全局单批任务（同一时间只跑一批；批量生成可能数分钟，串行够用）。
"""
from __future__ import annotations

import threading
from typing import Callable

_lock = threading.Lock()
_stop = threading.Event()
_state: dict = {
    "status": "idle",
    "draft_id": 0,
    "total": 0,
    "done": 0,
    "failed": 0,
    "last_error": "",
}


def _sleep(seconds: float) -> None:   # 可注入单测（no-op）
    import time  # noqa: PLC0415
    time.sleep(seconds)


def _set(**kw) -> None:
    with _lock:
        _state.update(kw)


def batch_status() -> dict:
    with _lock:
        return dict(_state)


def request_stop() -> dict:
    _stop.set()
    return batch_status()


def _run(
    gen_fn: Callable[[str], str],
    on_candidate: Callable[[int, str, str], None],
    plan: list[dict],
    draft_id: int,
) -> None:
    total = len(plan)
    _set(total=total, done=0, failed=0, last_error="")
    for item in plan:
        if _stop.is_set():
            _set(status="stopped")
            return
        angle = str(item.get("angle") or item.get("prompt") or "")
        prompt = str(item.get("prompt") or angle)
        try:
            url = gen_fn(prompt)
            on_candidate(draft_id, angle, url)
            with _lock:
                _state["done"] += 1
        except Exception as exc:  # noqa: BLE001
            with _lock:
                _state["failed"] += 1
                _state["last_error"] = str(exc)
    _set(status="done")


def start_batch(
    gen_fn: Callable[[str], str],
    on_candidate: Callable[[int, str, str], None],
    plan: list[dict],
    draft_id: int,
) -> dict:
    with _lock:
        if _state["status"] == "running":
            return dict(_state)
        _stop.clear()
        _state.update({
            "status": "running",
            "draft_id": int(draft_id),
            "total": len(plan),
            "done": 0,
            "failed": 0,
            "last_error": "",
        })
    threading.Thread(
        target=_run,
        args=(gen_fn, on_candidate, plan, draft_id),
        daemon=True,
    ).start()
    return batch_status()
