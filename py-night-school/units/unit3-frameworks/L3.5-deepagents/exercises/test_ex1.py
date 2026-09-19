"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import ToolMessage

import ex1_custom_tool as ex1
import mock_tools


def test_policy_tool_executed_by_framework() -> None:
    """命中关键词：新工具被框架真实执行（日志 + 回喂内容取证），原工具照常，建议单成立。"""
    advice, state = asyncio.run(ex1.run_with_policy("CLM-2026-0002", "宴请"))
    assert ex1.POLICY_LOG == ["lookup_policy"]  # 框架真的调了它，不是剧本自说自话
    policy_msg = next(m for m in state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "call_policy")
    assert "人均不超过 150 元" in str(policy_msg.content)  # 回喂的是执行结果（政策行）
    assert "check_budget" in mock_tools.CALL_LOG  # 原有工具照常执行
    assert (advice.decision, advice.reason) == ("REJECT", "REJECT:ITEM_OVER_LIMIT")


def test_policy_miss_returns_error_row_not_raise() -> None:
    """未命中关键词：回喂错误行、管道不炸、不记执行日志——错误是数据不是异常。"""
    advice, state = asyncio.run(ex1.run_with_policy("CLM-2026-0003", "打车"))
    policy_msg = next(m for m in state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "call_policy")
    assert "policy_not_found" in str(policy_msg.content)
    assert ex1.POLICY_LOG == []  # 查无与 check_budget 的 unknown_dept 分支同口径：不记日志
    assert (advice.decision, advice.reason) == ("ESCALATE", "REJECT:INVALID_AMOUNT")
