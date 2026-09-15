"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

import pytest

import ex2_budget as ex2


def test_budget_raises_exactly_at_max_turns() -> None:
    model = ex2.ObsessedModel()

    async def scenario() -> str:
        with pytest.raises(ex2.BudgetExceeded) as excinfo:
            await ex2.run_with_budget(model, "审查一下", max_turns=3)
        return str(excinfo.value)

    message = asyncio.run(scenario())
    assert "3" in message  # 异常信息带轮数——运维第一眼要知道烧了几轮
    assert model.request_count == 3  # 恰好 3 轮，一次不多（确定性护栏）


def test_budget_history_shape() -> None:
    model = ex2.ObsessedModel()

    async def scenario() -> None:
        with pytest.raises(ex2.BudgetExceeded):
            await ex2.run_with_budget(model, "审查一下", max_turns=3)

    asyncio.run(scenario())
    # 执念模型每轮 assistant(tool_calls) + tool 各一条：3 轮共 6 条，加 system/user 共 8 条
    # 这里不直接断言历史长度（run 不返回历史），改为从模型侧取证：
    assert model.request_count == 3


def test_budget_one_round_is_enough_to_raise() -> None:
    model = ex2.ObsessedModel()

    async def scenario() -> None:
        with pytest.raises(ex2.BudgetExceeded):
            await ex2.run_with_budget(model, "审查一下", max_turns=1)

    asyncio.run(scenario())
    assert model.request_count == 1  # 预算 1：一轮工具轮就触发——护栏粒度是「轮」不是「次工具」
