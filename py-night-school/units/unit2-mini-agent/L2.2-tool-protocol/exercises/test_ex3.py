"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import json

import ex3_dispatch as ex3


def test_happy_path_string_result_as_is() -> None:
    assert ex3.run_tool("preapprove", '{"items_cents": [1200, 3500]}') == "PASS"
    # 校验分层：负数过 schema、被业务规则拒——INVALID_AMOUNT 是合法输出，不能在门口拦
    assert ex3.run_tool("preapprove", '{"items_cents": [-500]}') == "REJECT:INVALID_AMOUNT"


def test_happy_path_non_string_result_serialized() -> None:
    result = ex3.run_tool("claim_count", "{}")  # 无参工具：空 JSON 对象
    assert isinstance(result, str)  # 回喂给模型的 content 必须是 str
    assert json.loads(result) == 3  # budget_mock.json 里有 3 张单


def test_unknown_tool_returns_feedable_error() -> None:
    error = json.loads(ex3.run_tool("no_such_tool", "{}"))
    assert error["error"].startswith("unknown_tool")
    assert "preapprove" in error["error"]  # 带上可用工具清单，给模型修复提示


def test_invalid_arguments_returns_feedable_error() -> None:
    empty = json.loads(ex3.run_tool("preapprove", '{"items_cents": []}'))  # min_length=1 违规
    assert empty["error"].startswith("invalid_arguments")
    broken = json.loads(ex3.run_tool("preapprove", "不是 JSON"))
    assert broken["error"].startswith("invalid_arguments")  # loc 为空也不许 IndexError


def test_tool_internal_error_returns_feedable_error() -> None:
    error = json.loads(ex3.run_tool("always_boom", "{}"))
    assert error["error"].startswith("tool_error")
    assert "ValueError" in error["error"]
