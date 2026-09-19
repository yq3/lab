"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

import pytest
from langgraph.errors import GraphRecursionError

import ex2_budget as ex2

INITIAL: dict = {"messages": [], "debate": {"count": 0, "current_speaker": ""}}


def _scripts() -> list[str]:
    return ["申辩：连号重开支出真实", "质证：单据链不完整", "裁决台词"]


def test_cap_exactly_enough_completes_full_graph() -> None:
    budget = ex2.LLMCallBudget(ex2.FakeChatModel(_scripts()), limit=3)
    result = asyncio.run(ex2.build(budget).ainvoke(INITIAL))
    assert result["ruling"] == "裁决：裁决台词"
    assert result["settlement"]  # 整理节点照常执行
    assert budget.used == 3  # 恰好烧满，不超卖也不预留


def test_cap_burns_midway_raises_with_exact_used() -> None:
    inner = ex2.FakeChatModel(_scripts())
    budget = ex2.LLMCallBudget(inner, limit=2)
    with pytest.raises(ex2.BudgetExceeded) as excinfo:
        asyncio.run(ex2.build(budget).ainvoke(INITIAL))
    assert excinfo.value.args  # 异常信息非空（响亮拒绝，不是静默）
    assert budget.used == 2  # 已调用次数恰好 = cap
    assert inner.request_count == 2  # 被拒的第 3 次没有打到模型（不超卖）


def test_recursion_limit_is_a_different_axis() -> None:
    """superstep 预算 ≠ 模型调用预算：limit=3 烧到「整理」就停，模型只被调 2 次。"""
    inner = ex2.FakeChatModel(_scripts())
    budget = ex2.LLMCallBudget(inner, limit=None)  # 模型调用不限
    with pytest.raises(GraphRecursionError):  # 不是 BudgetExceeded——另一条轴
        asyncio.run(ex2.build(budget).ainvoke(INITIAL, config={"recursion_limit": 3}))
    assert inner.request_count == 2  # 申辩人 + 合规官各 1 次；「整理」烧 superstep 不烧模型
    assert budget.used == 2
