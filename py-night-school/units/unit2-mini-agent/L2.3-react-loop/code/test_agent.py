"""讲义代码验收（发货态必须全绿；练习区的红在 exercises/）。"""

from __future__ import annotations

import asyncio

import pytest

import finance  # noqa: F401 —— import 即注册
from agent import AgentBudgetExceeded, AgentResult, ReActAgent
from context_budget import estimate_chars, trim_messages
from model import ScriptedModel, ScriptExhausted

REVIEW_SCRIPT = [
    {"tool_calls": [{"id": "call_001", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0002"}}]},
    {"tool_calls": [{"id": "call_002", "name": "preapprove", "arguments": {"items_cents": [8800]}}]},
    {"content": "REJECT:ITEM_OVER_LIMIT"},
]


def test_agent_runs_two_tool_rounds_and_finishes() -> None:
    model = ScriptedModel(REVIEW_SCRIPT)
    agent = ReActAgent(model)

    async def scenario() -> AgentResult:
        return await agent.run("请审查报销单 CLM-2026-0002。")

    result = asyncio.run(scenario())
    assert result.final_text == "REJECT:ITEM_OVER_LIMIT"
    assert result.turns == 3  # 两次工具轮 + 一次回答轮
    roles = [m["role"] for m in result.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant"]
    # tool_call_id 一一配对（协议纪律）
    assert result.messages[3]["tool_call_id"] == result.messages[2]["tool_calls"][0]["id"]
    assert result.messages[5]["tool_call_id"] == result.messages[4]["tool_calls"][0]["id"]
    # 工具真实执行过：回喂内容是注册表结果，不是脚本原文
    assert result.messages[3]["content"].startswith('{"id": "CLM-2026-0002"')
    assert result.messages[5]["content"] == "REJECT:ITEM_OVER_LIMIT"


def test_agent_sends_tools_payload_every_round() -> None:
    model = ScriptedModel(REVIEW_SCRIPT)
    agent = ReActAgent(model)

    async def scenario() -> None:
        await agent.run("请审查报销单 CLM-2026-0002。")

    asyncio.run(scenario())
    assert len(model.calls) == 3  # 每轮一次模型调用，每次都带契约
    for call in model.calls:
        names = {tool["function"]["name"] for tool in call["tools"]}
        assert names == {"preapprove", "get_claim"}
    # 第 2 轮请求带着第 1 轮的工具结果（无状态协议：历史全量重发）
    second_round_messages = model.calls[1]["messages"]
    assert second_round_messages[-1]["role"] == "tool"


def test_budget_exceeded_raises_with_history_shape() -> None:
    always_tool = [
        {"tool_calls": [{"id": f"call_{i}", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0001"}}]}
        for i in range(9)
    ]
    model = ScriptedModel(always_tool)
    agent = ReActAgent(model, max_turns=4)

    async def scenario() -> AgentBudgetExceeded:
        with pytest.raises(AgentBudgetExceeded) as excinfo:
            await agent.run("审查一下")
        return excinfo.value

    error = asyncio.run(scenario())
    assert "4 轮预算耗尽" in str(error)
    assert len(model.calls) == 4  # 恰好 4 轮，不多不少——硬预算的确定性


def test_scripted_model_exhaustion_is_loud() -> None:
    model = ScriptedModel([{"content": "done"}])

    async def scenario() -> None:
        await model.complete([], [])

    asyncio.run(scenario())
    with pytest.raises(ScriptExhausted):
        asyncio.run(scenario())  # 剧本演完再要——测试替身也要有契约


def test_trim_keeps_system_and_never_leads_with_orphan_tool() -> None:
    messages = [
        {"role": "system", "content": "S" * 50},
        {"role": "user", "content": "U" * 100},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "R" * 100},
        {"role": "assistant", "content": "A" * 100},
        {"role": "user", "content": "U2" * 60},
        {"role": "assistant", "content": "final"},
    ]
    budget = estimate_chars(messages) - 260  # 强制裁掉最老的两条
    trimmed = trim_messages(messages, budget)
    assert trimmed[0]["role"] == "system"  # 纪律 1
    assert trimmed[1]["role"] != "tool"  # 纪律 2：孤儿 tool 不当排头
    assert trimmed[-1]["content"] == "final"  # 最新消息保留
    assert estimate_chars(trimmed) <= budget
    assert len(messages) == 7  # 原历史不动——裁剪只影响发给模型的视图


def test_trim_returns_original_when_within_budget() -> None:
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    assert trim_messages(messages, estimate_chars(messages)) == messages
