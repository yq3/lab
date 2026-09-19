"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

from ex3_registry import TOOLS, run_tool


def test_ex3_both_tools_registered() -> None:
    # import 的瞬间 @register 就该把两个工具登记进 TOOLS
    assert set(TOOLS) == {"check_item_limit", "check_total_limit"}


def test_ex3_registered_tool_results() -> None:
    assert TOOLS["check_item_limit"]([1200, 8800]) == "REJECT:ITEM_OVER_LIMIT"
    assert TOOLS["check_item_limit"]([1200, 3500]) == "PASS"
    assert TOOLS["check_total_limit"]([4000] * 126) == "REJECT:TOTAL_OVER_LIMIT"
    assert TOOLS["check_total_limit"]([5000] * 100) == "PASS"  # 边界：恰好 500000 分


def test_ex3_run_tool_dispatches_by_name() -> None:
    assert run_tool("check_item_limit", [8800]) == "REJECT:ITEM_OVER_LIMIT"
    assert run_tool("check_total_limit", [1200, 3500, 2400]) == "PASS"


def test_ex3_unknown_tool_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        run_tool("query_budget", [100])
