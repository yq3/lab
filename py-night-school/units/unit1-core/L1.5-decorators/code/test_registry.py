"""讲义示例测试：registry 装饰器（@tool 的秘密）。"""

import pytest

from registry import TOOLS, check_item_limit, check_total_limit, run_tool, tool


def test_tools_registered_at_import() -> None:
    # import registry 的瞬间，两个 @tool 函数就已在注册表里
    assert set(TOOLS) == {"check_item_limit", "check_total_limit"}


def test_registered_functions_still_callable_directly() -> None:
    assert check_item_limit([8800]) == "REJECT:ITEM_OVER_LIMIT"
    assert check_total_limit([4000] * 126) == "REJECT:TOTAL_OVER_LIMIT"


def test_run_tool_by_name() -> None:
    assert run_tool("check_item_limit", [1200, 8800]) == "REJECT:ITEM_OVER_LIMIT"
    assert run_tool("check_total_limit", [1200, 3500, 2400]) == "PASS"


def test_run_tool_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        run_tool("query_budget", [100])


def test_tool_decorator_registers_more() -> None:
    @tool
    def check_negative(items_cents: list[int]) -> str:
        """脏数据检查。"""
        if any(c <= 0 for c in items_cents):
            return "REJECT:INVALID_AMOUNT"
        return "PASS"

    try:
        assert "check_negative" in TOOLS
        assert TOOLS["check_negative"]([-100]) == "REJECT:INVALID_AMOUNT"
    finally:
        del TOOLS["check_negative"]  # 测试收尾：别污染注册表
