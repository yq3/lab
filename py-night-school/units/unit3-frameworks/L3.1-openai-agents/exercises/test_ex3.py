"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import asyncio

import pytest
from agents.exceptions import MaxTurnsExceeded

import ex3_budget as ex3
import mock_tools


def test_max_turns_three_stops_exactly_at_three() -> None:
    with pytest.raises(MaxTurnsExceeded, match=r"Max turns \(3\) exceeded"):
        asyncio.run(ex3.run_observed(max_turns=3))
    assert ex3.REQUESTS[-1] == 3  # 预算 3：第 3 轮停，模型一次不多调


def test_max_turns_five_stops_exactly_at_five() -> None:
    with pytest.raises(MaxTurnsExceeded, match=r"Max turns \(5\) exceeded"):
        asyncio.run(ex3.run_observed(max_turns=5))
    assert ex3.REQUESTS[-1] == 5  # 预算 5：同样的执念剧本，换预算换刻度


def test_obsessed_tool_really_runs_each_turn() -> None:
    mock_tools.CALL_LOG.clear()
    with pytest.raises(MaxTurnsExceeded):
        asyncio.run(ex3.run_observed(max_turns=3))
    assert mock_tools.CALL_LOG.count("check_budget") == 3  # 每轮的工具都真实执行了
