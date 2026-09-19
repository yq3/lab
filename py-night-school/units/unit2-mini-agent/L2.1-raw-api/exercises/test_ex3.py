"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

import pytest

import ex3_tool_roundtrip as ex3


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([1200, 3500, 2400], "PASS"),
        ([-500], "REJECT:INVALID_AMOUNT"),
        ([8800], "REJECT:ITEM_OVER_LIMIT"),
        ([4000] * 126, "REJECT:TOTAL_OVER_LIMIT"),  # 合计 504000 分
        ([5000], "PASS"),  # 边界：恰好等于单笔上限，不超
        ([5000] * 100, "PASS"),  # 边界：合计恰好 500000 分（每笔都合法），不超
    ],
)
def test_preapprove_four_states_and_boundaries(items: list[int], expected: str) -> None:
    assert ex3.preapprove(items) == expected


def test_handle_tool_calls_returns_paired_tool_messages() -> None:
    results = ex3.handle_tool_calls(ex3.TOOL_CALL_ASSISTANT)
    assert results == [
        {"role": "tool", "tool_call_id": "call_001", "content": "PASS"},
        {"role": "tool", "tool_call_id": "call_002", "content": "REJECT:ITEM_OVER_LIMIT"},
    ]
    # id 与 content 必须一一对应——串位回喂会被端点 400 拒收
    assert results[0]["tool_call_id"] == ex3.TOOL_CALL_ASSISTANT["tool_calls"][0]["id"]
    assert results[1]["tool_call_id"] == ex3.TOOL_CALL_ASSISTANT["tool_calls"][1]["id"]


def test_handle_tool_calls_skips_unknown_tool() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_x", "type": "function", "function": {"name": "unknown_tool", "arguments": '{"x": 1}'}},
            {
                "id": "call_y",
                "type": "function",
                "function": {"name": "preapprove", "arguments": '{"items_cents": [100]}'},
            },
        ],
    }
    results = ex3.handle_tool_calls(message)
    assert len(results) == 1
    assert results[0]["tool_call_id"] == "call_y"
    assert results[0]["content"] == "PASS"
