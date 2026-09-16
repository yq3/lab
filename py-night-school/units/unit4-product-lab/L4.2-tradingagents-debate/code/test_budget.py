"""讲义区验收 3/4：模型调用预算——计数、共享计数器、超限异常（ex2 的讲义区对版）。"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.messages import AIMessage

from budget import BudgetExceeded, LLMCallBudget


class _ScriptModel:
    """最小模型替身：数调用、按剧本回 AIMessage。"""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, messages: object) -> AIMessage:
        self.calls += 1
        return AIMessage(content=f"第 {self.calls} 次调用")


def test_unlimited_budget_passes_all_calls() -> None:
    model = _ScriptModel()
    budget = LLMCallBudget(None)
    wrapped = budget.wrap(model)

    async def run() -> None:
        for _ in range(5):
            await wrapped.ainvoke([{"role": "user", "content": "hi"}])

    asyncio.run(run())
    assert budget.used == 5  # None = 不限：计数照走，永不拒绝


def test_shared_counter_across_wrapped_models() -> None:
    """quick/deep 各 wrap 一次，计数共享——一个预算罩住整张图（demo.run_appeal 的用法）。"""
    quick, deep = _ScriptModel(), _ScriptModel()
    budget = LLMCallBudget(limit=4)
    w_quick, w_deep = budget.wrap(quick), budget.wrap(deep)

    async def run() -> None:
        await w_quick.ainvoke([])
        await w_deep.ainvoke([])
        await w_quick.ainvoke([])
        await w_deep.ainvoke([])

    asyncio.run(run())
    assert (quick.calls, deep.calls) == (2, 2)
    assert budget.used == 4


def test_exceeded_raises_with_exact_used_and_no_oversell() -> None:
    model = _ScriptModel()
    budget = LLMCallBudget(limit=2)
    wrapped = budget.wrap(model)

    async def run() -> None:
        await wrapped.ainvoke([])
        await wrapped.ainvoke([])
        await wrapped.ainvoke([])  # 第 3 次：超限

    with pytest.raises(BudgetExceeded) as excinfo:
        asyncio.run(run())
    assert excinfo.value.limit == 2
    assert excinfo.value.used == 2  # 已调用次数恰好 = cap：第 3 次在放行前被拒
    assert model.calls == 2  # 不超卖：被拒的调用没有打到模型


def test_limit_zero_rejects_everything() -> None:
    budget = LLMCallBudget(limit=0)
    wrapped = budget.wrap(_ScriptModel())

    async def run() -> None:
        await wrapped.ainvoke([])

    with pytest.raises(BudgetExceeded):
        asyncio.run(run())
    assert budget.used == 0
