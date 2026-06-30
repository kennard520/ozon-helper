"""文本生成 MQ 任务编排：understand → category → copy → attrs 串行执行。

设计原则：纯编排，不持有任何 webui/DB/AI 依赖；所有步骤以 callable 注入。
"""
from __future__ import annotations

from typing import Callable

STEPS = ["understand", "category", "copy", "attrs"]


def run_text_pipeline(
    draft_id: int,
    *,
    run_understand: Callable[[int], dict],
    run_category: Callable[[int], dict],
    run_copy: Callable[[int], dict],
    run_attrs: Callable[[int], dict],
    on_step: Callable[[str], None] | None = None,
) -> dict:
    """串行跑四步，每步完成后调 on_step(step_name)。

    返回 {"ok": True, "steps": {"understand": ..., "category": ..., "copy": ..., "attrs": ...}}。
    任一步失败（抛出异常）即停止并向上传递异常。
    """
    results: dict[str, dict] = {}
    for step, fn in [
        ("understand", run_understand),
        ("category", run_category),
        ("copy", run_copy),
        ("attrs", run_attrs),
    ]:
        result = fn(draft_id)
        results[step] = result
        if on_step:
            on_step(step)
    return {"ok": True, "steps": results}
