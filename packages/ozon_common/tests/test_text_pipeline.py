"""run_text_pipeline 串行编排入口单测。

覆盖场景：
1. 正常串行执行——四步都被调用一次、返回结构正确。
2. on_step 回调——每步完成后以步骤名调用，顺序正确。
3. 某步失败抛异常时中止——后续步骤不被调用，异常向上传。
4. draft_id 正确传入各步——每个 fn 收到的 draft_id 一致。
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from ozon_common.text_pipeline.pipeline import STEPS, run_text_pipeline


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make_fns(draft_id: int = 42) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """返回四个 mock，每个调用时返回包含自身步骤名的 dict。"""
    fns = []
    for name in STEPS:
        m = MagicMock(return_value={"step": name, "data": "ok"})
        m.__name__ = name  # 便于调试
        fns.append(m)
    return tuple(fns)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 测试 1：正常串行执行
# ---------------------------------------------------------------------------

def test_run_text_pipeline_happy_path():
    """四步都被调用一次，返回 {"ok": True, "steps": {...}}。"""
    understand, category, copy_, attrs = _make_fns()

    result = run_text_pipeline(
        42,
        run_understand=understand,
        run_category=category,
        run_copy=copy_,
        run_attrs=attrs,
    )

    # 返回结构
    assert result["ok"] is True
    assert set(result["steps"].keys()) == {"understand", "category", "copy", "attrs"}

    # 每步都被调用一次
    understand.assert_called_once()
    category.assert_called_once()
    copy_.assert_called_once()
    attrs.assert_called_once()

    # 步骤结果保留在 steps 字典中
    assert result["steps"]["understand"] == {"step": "understand", "data": "ok"}
    assert result["steps"]["attrs"] == {"step": "attrs", "data": "ok"}


# ---------------------------------------------------------------------------
# 测试 2：on_step 回调顺序正确
# ---------------------------------------------------------------------------

def test_on_step_callback_order():
    """每步完成后 on_step 被调用，顺序是 understand→category→copy→attrs。"""
    understand, category, copy_, attrs = _make_fns()
    on_step = MagicMock()

    run_text_pipeline(
        7,
        run_understand=understand,
        run_category=category,
        run_copy=copy_,
        run_attrs=attrs,
        on_step=on_step,
    )

    assert on_step.call_count == 4
    assert on_step.call_args_list == [
        call("understand"),
        call("category"),
        call("copy"),
        call("attrs"),
    ]


def test_on_step_none_does_not_raise():
    """on_step=None（默认）时不抛异常。"""
    understand, category, copy_, attrs = _make_fns()

    result = run_text_pipeline(
        1,
        run_understand=understand,
        run_category=category,
        run_copy=copy_,
        run_attrs=attrs,
        on_step=None,
    )
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# 测试 3：某步抛异常时中止，后续步骤不被调用
# ---------------------------------------------------------------------------

def test_exception_in_category_stops_pipeline():
    """category 步抛 RuntimeError 时，copy 和 attrs 不被调用，异常向上传。"""
    understand = MagicMock(return_value={"step": "understand"})
    category = MagicMock(side_effect=RuntimeError("category failed"))
    copy_ = MagicMock(return_value={"step": "copy"})
    attrs = MagicMock(return_value={"step": "attrs"})
    on_step = MagicMock()

    with pytest.raises(RuntimeError, match="category failed"):
        run_text_pipeline(
            99,
            run_understand=understand,
            run_category=category,
            run_copy=copy_,
            run_attrs=attrs,
            on_step=on_step,
        )

    understand.assert_called_once()
    category.assert_called_once()
    copy_.assert_not_called()
    attrs.assert_not_called()

    # on_step 只在 understand 完成后调了一次
    assert on_step.call_args_list == [call("understand")]


def test_exception_in_first_step_stops_all():
    """understand 步抛异常时，后三步均不被调用。"""
    understand = MagicMock(side_effect=ValueError("bad understand"))
    category = MagicMock(return_value={})
    copy_ = MagicMock(return_value={})
    attrs = MagicMock(return_value={})
    on_step = MagicMock()

    with pytest.raises(ValueError, match="bad understand"):
        run_text_pipeline(
            5,
            run_understand=understand,
            run_category=category,
            run_copy=copy_,
            run_attrs=attrs,
            on_step=on_step,
        )

    category.assert_not_called()
    copy_.assert_not_called()
    attrs.assert_not_called()
    on_step.assert_not_called()


# ---------------------------------------------------------------------------
# 测试 4：draft_id 正确传入各步
# ---------------------------------------------------------------------------

def test_draft_id_passed_to_all_steps():
    """每个 callable 收到的第一个位置参数是 draft_id。"""
    understand, category, copy_, attrs = _make_fns(draft_id=123)

    run_text_pipeline(
        123,
        run_understand=understand,
        run_category=category,
        run_copy=copy_,
        run_attrs=attrs,
    )

    for fn in (understand, category, copy_, attrs):
        args, _ = fn.call_args
        assert args[0] == 123


def test_draft_id_zero_is_valid():
    """draft_id=0 也能正常传入（边界值）。"""
    understand, category, copy_, attrs = _make_fns()

    run_text_pipeline(
        0,
        run_understand=understand,
        run_category=category,
        run_copy=copy_,
        run_attrs=attrs,
    )

    for fn in (understand, category, copy_, attrs):
        args, _ = fn.call_args
        assert args[0] == 0


# ---------------------------------------------------------------------------
# 测试 5：STEPS 常量内容正确（便于 worker 迭代）
# ---------------------------------------------------------------------------

def test_steps_constant():
    """STEPS 按顺序包含四个步骤名。"""
    assert STEPS == ["understand", "category", "copy", "attrs"]
