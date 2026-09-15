"""里程碑验收（不要改本文件——它就是你的判卷老师）。

三个 TODO 各有自己的红；给定模块（client/tools/finance/structured 的解析部分）必须全绿。
stdio 用例拉起 mcp_server.py 子进程（秒级）——真协议的验收价值配得上这几秒。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

import finance  # noqa: F401 —— import 即注册
from agent import AgentBudgetExceeded, AgentResult, ReActAgent
from client import SSEDecoder
from mcp_bridge import McpToolError, mcp_tools_payload, run_mcp_tool
from model import ScriptedModel
from structured import PreapprovalDecision, StructuredOutputError, ask_structured, extract_json
from tools import TOOL_REGISTRY, run_tool

MCP_SERVER = Path(__file__).resolve().parents[1] / "mcp_server.py"

SCRIPT = [
    {"tool_calls": [{"id": "call_001", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0002"}}]},
    {"tool_calls": [{"id": "call_002", "name": "preapprove", "arguments": {"items_cents": [8800]}}]},
    {
        "content": '结论如下：{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", '
        '"reason": "单笔 8800 分超过 5000 分上限"}'
    },
]

OBSESSED = [
    {"tool_calls": [{"id": f"call_{i:03d}", "name": "get_claim", "arguments": {"claim_id": "CLM-2026-0001"}}]}
    for i in range(20)
]


# ---- 给定模块必须全绿（发货态） ----


def test_given_sse_decoder_reassembles() -> None:
    decoder = SSEDecoder()
    first = decoder.feed(b'data: {"delta": "reimbur')
    assert first == []
    second = decoder.feed(b'sement"}\n\ndata: [DONE]\n\n')
    assert '"reimbursement"' in second[0]


def test_given_registry_and_dispatch() -> None:
    assert set(TOOL_REGISTRY) == {"preapprove", "get_claim"}
    assert run_tool("preapprove", '{"items_cents": [-500]}') == "REJECT:INVALID_AMOUNT"
    assert json.loads(run_tool("get_claim", '{"claim_id": "CLM-2026-0003"}'))["items_cents"] == [-500]


def test_given_extract_json_three_layers() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('夹在散文里 {"b": 2} 的 JSON') == {"b": 2}


# ---- T1：agent 循环 ----


def test_t1_full_run_local_tools() -> None:
    model = ScriptedModel(SCRIPT)
    agent = ReActAgent(model, max_turns=6)

    async def scenario() -> AgentResult:
        return await agent.run("请审查报销单 CLM-2026-0002。")

    result = asyncio.run(scenario())
    assert result.turns == 3
    assert [m["role"] for m in result.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert result.messages[3]["tool_call_id"] == result.messages[2]["tool_calls"][0]["id"]
    assert result.messages[3]["content"].startswith('{"id": "CLM-2026-0002"')  # 工具真实执行
    assert result.messages[5]["content"] == "REJECT:ITEM_OVER_LIMIT"
    assert "REJECT:ITEM_OVER_LIMIT" in result.final_text


def test_t1_budget_exceeded() -> None:
    model = ScriptedModel(OBSESSED)
    agent = ReActAgent(model, max_turns=4)

    async def scenario() -> str:
        with pytest.raises(AgentBudgetExceeded) as excinfo:
            await agent.run("查一下")
        return str(excinfo.value)

    message = asyncio.run(scenario())
    assert "4 轮" in message
    assert len(model.calls) == 4  # 恰好预算轮数，一次不多


def test_t1_executor_seam() -> None:
    executed: list[tuple[str, str]] = []

    async def counting_execute(name: str, arguments_json: str) -> str:
        executed.append((name, arguments_json))
        return "REJECT:TOTAL_OVER_LIMIT"

    model = ScriptedModel(
        [{"tool_calls": [{"id": "c1", "name": "preapprove", "arguments": {"items_cents": [1]}}]}, {"content": "done"}]
    )
    agent = ReActAgent(model, registry={}, max_turns=4)  # registry 空：执行全走接缝

    async def scenario() -> AgentResult:
        return await agent.run("查一下", execute=counting_execute)

    result = asyncio.run(scenario())
    assert executed == [("preapprove", '{"items_cents": [1]}')]  # 接缝拿到了原始 arguments 字符串
    assert result.messages[3]["content"] == "REJECT:TOTAL_OVER_LIMIT"


# ---- T2：结构化修复回路 ----


def test_t2_structured_repairs() -> None:
    fixed = '修正：{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT", "reason": "单笔超限"}'
    model = ScriptedModel(
        [
            {"content": '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:OVER"}\n```'},
            {"content": fixed},
        ]
    )

    async def scenario() -> tuple[PreapprovalDecision, list[dict]]:
        return await ask_structured(model, "问一下")

    decision, messages = asyncio.run(scenario())
    assert decision.verdict == "REJECT:ITEM_OVER_LIMIT"
    assert len(model.calls) == 2
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user", "assistant"]


def test_t2_structured_exhausted() -> None:
    model = ScriptedModel([{"content": "我就是不输出 JSON。"}] * 3)

    async def scenario() -> str:
        with pytest.raises(StructuredOutputError) as excinfo:
            await ask_structured(model, "问一下", attempts=3)
        return str(excinfo.value)

    assert "3 次" in asyncio.run(scenario())
    assert len(model.calls) == 3


# ---- T3：MCP 桥接 ----


def test_t3_payload_passthrough() -> None:
    from mcp.types import Tool

    tools = [
        Tool(
            name="preapprove", description="预审。", input_schema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(name="bare", description=None, input_schema={"type": "object", "properties": {}}),
    ]
    payload = mcp_tools_payload(tools)
    assert payload[0]["function"]["parameters"] == tools[0].input_schema  # 原样透传
    assert payload[1]["function"]["description"] == ""  # None 归一


def test_t3_stdio_roundtrip() -> None:
    async def scenario() -> list[str]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        outcomes: list[str] = []
        params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                outcomes.append(await run_mcp_tool(session, "preapprove", '{"items_cents": [1200, 3500, 2400]}'))
                outcomes.append(await run_mcp_tool(session, "preapprove", '{"items_cents": [8800]}'))
                outcomes.append(await run_mcp_tool(session, "preapprove", '{"items_cents": [-500]}'))
                outcomes.append(await run_mcp_tool(session, "preapprove", json.dumps({"items_cents": [4000] * 126})))
                try:
                    await run_mcp_tool(session, "no_such_tool", "{}")
                except McpToolError as exc:
                    outcomes.append(f"McpToolError: {exc}")
        return outcomes

    outcomes = asyncio.run(scenario())
    assert outcomes[:4] == [  # 预审四态全走一遍（真协议）
        "PASS",
        "REJECT:ITEM_OVER_LIMIT",
        "REJECT:INVALID_AMOUNT",
        "REJECT:TOTAL_OVER_LIMIT",
    ]
    assert outcomes[4].startswith("McpToolError")  # 未知工具走有名异常


# ---- 端到端：循环 × 工具 × 结构化（T1 + 给定件的合体） ----


def test_end_to_end_offline_decision() -> None:
    model = ScriptedModel(SCRIPT)
    agent = ReActAgent(model, max_turns=6)

    async def scenario() -> PreapprovalDecision:
        result = await agent.run("请审查报销单 CLM-2026-0002。")
        return PreapprovalDecision.model_validate(extract_json(result.final_text))

    decision = asyncio.run(scenario())
    assert decision.claim_id == "CLM-2026-0002"
    assert decision.verdict == "REJECT:ITEM_OVER_LIMIT"  # 与 data/expense 的 expect 字段一致
